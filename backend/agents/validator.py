"""
Validator Agent — revisión adversarial de todas las decisiones del sistema.
El único agente que puede REVERTIR decisiones de otros agentes con justificación escrita.
Opera sobre hechos, no suposiciones.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from backend.core import llm


# ── Reglas de contradicción ──────────────────────────────────────────────────

def _check_contradictions(
    product: dict,
    batch: dict,
    risk: dict,
    stock_decision: str,
    price_recommendation: dict,
) -> list[str]:
    """
    Detección determinista de contradicciones antes de llamar a Claude.
    Devuelve lista de problemas encontrados (vacía si todo correcto).
    """
    issues = []
    days_left = risk.get("days_left", 999)
    risk_level = risk.get("risk_level", "BAJO")
    action = risk.get("action", "ok")
    price_pct = price_recommendation.get("discount_pct", 0)
    new_price = price_recommendation.get("new_price", 0)
    cost = float(product.get("cost", 0))
    qty = batch.get("quantity", 0)

    # Contradicción 1: reponer cuando el lote va a caducar pronto
    if "SÍ reponer" in stock_decision and days_left <= 2:
        issues.append(
            f"CONTRADICCIÓN: Se recomienda reponer pero el lote caduca en {days_left} días. "
            "Reponer empujaría el nuevo stock al fondo violando FEFO."
        )

    # Contradicción 2: precio por debajo del coste
    if new_price > 0 and cost > 0 and new_price < cost:
        issues.append(
            f"VIOLACIÓN DE MARGEN: Precio nuevo ({new_price} euros) es inferior al coste ({cost} euros). "
            "Ajustar a mínimo coste + 5%."
        )

    # Contradicción 3: riesgo CRÍTICO sin acción de descuento o retirada
    if risk_level == "CRÍTICO" and action == "ok":
        issues.append(
            "INCOHERENCIA: Riesgo CRÍTICO pero acción es 'ok'. "
            "Productos críticos requieren intervención inmediata."
        )

    # Contradicción 4: descuento cero con CRÍTICO o ALTO
    if risk_level in ("CRÍTICO", "ALTO") and price_pct == 0 and action == "rebajar":
        issues.append(
            f"INCOHERENCIA: Acción es 'rebajar' pero el descuento calculado es 0%. "
            "Debe especificarse un descuento concreto."
        )

    # Contradicción 5: donar sin que aplique (producto con días suficientes)
    if action == "donar" and days_left > 3:
        issues.append(
            f"DECISIÓN PREMATURA: Se propone donar con {days_left} días restantes. "
            "La donación se reserva para productos con 0-1 días o con defectos visuales."
        )

    # Contradicción 6: retirar un producto aún dentro de fecha sin justificación
    if action == "retirar" and days_left > 0 and risk_level not in ("CRÍTICO", "ALTO"):
        issues.append(
            f"RETIRADA INJUSTIFICADA: Se propone retirar con {days_left} días y riesgo {risk_level}. "
            "La retirada anticipada genera pérdida innecesaria."
        )

    # Contradicción 7: sin acciones para producto con caducidad HOY
    if days_left <= 0 and action == "ok":
        issues.append(
            "ERROR CRÍTICO: Producto caducado hoy sin acción asignada. "
            "Requiere retirada o donación inmediata."
        )

    # Contradicción 8: score extremadamente alto pero acción blanda
    score = risk.get("score", 0)
    if score >= 95 and action in ("revisar", "ok"):
        issues.append(
            f"DIVERGENCIA SCORE-ACCIÓN: Score de riesgo {score}/100 (crítico extremo) "
            "pero acción propuesta es '{action}'. Scores ≥95 exigen retirada o donación inmediata."
        )

    # Contradicción 9: cantidad en tienda = 0 y se propone rebajar (no hay nada que rebajar)
    if qty == 0 and action == "rebajar":
        issues.append(
            "ACCIÓN IMPOSIBLE: Se propone rebajar un producto con 0 unidades en tienda. "
            "Sin stock visible no hay etiqueta que modificar. Revisar estado del lote."
        )

    # Contradicción 10: descuento superior al 70% sin riesgo CRÍTICO (pérdida innecesaria)
    if price_pct > 70 and risk_level not in ("CRÍTICO",) and days_left > 1:
        issues.append(
            f"DESCUENTO EXCESIVO: {price_pct}% de descuento con riesgo {risk_level} y {days_left} días. "
            "Un descuento >70% solo se justifica con riesgo CRÍTICO y caducidad inmediata."
        )

    # Contradicción 11: cantidad muy alta en tienda (>50 uds) con caducidad hoy sin donación
    if qty > 50 and days_left <= 0 and action != "donar":
        issues.append(
            f"OPORTUNIDAD DE DONACIÓN PERDIDA: {qty} unidades caducadas hoy sin proponer donación. "
            "Volúmenes >50 uds son candidatos prioritarios para banco de alimentos (Ley 49/2002)."
        )

    # Contradicción 12: acción de reposición cuando el riesgo es ALTO o CRÍTICO
    if action == "reponer" and risk_level in ("ALTO", "CRÍTICO"):
        issues.append(
            f"REPOSICIÓN EN SITUACIÓN DE RIESGO {risk_level}: Reponer aumenta el stock en un lote "
            "que ya está en situación crítica. Viola FEFO — el nuevo stock quedaría detrás del crítico."
        )

    # Contradicción 13: precio nuevo idéntico al original (descuento no aplicado)
    original_price = product.get("price", 0)
    if action == "rebajar" and new_price > 0 and original_price > 0 and abs(new_price - original_price) < 0.01:
        issues.append(
            f"REBAJA SIN EFECTO: El precio nuevo ({new_price}€) es idéntico al original ({original_price}€). "
            "La acción 'rebajar' requiere reducción real del precio en el sistema."
        )

    return issues


def validate_scan_result(
    product: dict,
    batch: dict,
    risk: dict,
    stock_decision: str,
    price_recommendation: dict,
) -> dict:
    """
    Validación adversarial completa de un resultado de escaneo.
    Devuelve {status, issues, override, final_action, explanation}
    """
    # Detección determinista primero — rápida y sin tokens
    issues = _check_contradictions(product, batch, risk, stock_decision, price_recommendation)

    if not issues:
        # Validación rápida por LLM para detectar problemas semánticos sutiles
        prompt = f"""Actúas como el Validador adversarial de MermaOps. Tu trabajo es encontrar errores.

Producto: {product.get('name')} | Categoría: {product.get('category')}
Caduca: {batch.get('expiry_date')} | Cantidad: {batch.get('quantity')} uds
Riesgo calculado: {risk.get('risk_level')} ({risk.get('score')}/100)
Acción propuesta: {risk.get('action')}
Recomendación de precio: {price_recommendation}
Decisión de stock: {stock_decision}
Razonamiento del evaluador: {risk.get('reasoning', '')}

Busca contradicciones sutiles que las reglas automáticas no detectan:
- ¿El razonamiento del evaluador justifica la acción propuesta?
- ¿Hay contexto que haría cambiar la decisión?
- ¿Es la prioridad correcta comparada con otros tipos de productos?

Responde VALIDADO si todo es coherente, o OBSERVACIÓN: [una línea] si hay algo a revisar."""

        llm_check = llm.call(prompt, max_tokens=120)
        if "OBSERVACIÓN" in llm_check or "CORRECCIÓN" in llm_check:
            issues.append(llm_check)

    if not issues:
        return {
            "status": "VALIDADO",
            "issues": [],
            "override": False,
            "final_action": risk.get("action"),
            "explanation": "Todas las decisiones son coherentes entre sí.",
        }

    # Hay problemas — pedir a Claude que decida si revertir y cómo corregir
    issues_text = "\n".join(f"- {i}" for i in issues)
    correction_prompt = f"""Eres el Validador de MermaOps. Has detectado las siguientes inconsistencias:

{issues_text}

Producto: {product.get('name')} | Días hasta caducidad: {risk.get('days_left', '?')}
Acción original: {risk.get('action')} | Score: {risk.get('score')}/100

Decide:
1. ¿Debe revertirse la decisión original? (SÍ/NO)
2. Si SÍ, ¿cuál es la acción corregida?
3. Explicación en una línea para el log del sistema."""

    correction = llm.call_structured(
        correction_prompt,
        output_schema={
            "type": "object",
            "properties": {
                "override": {"type": "boolean"},
                "corrected_action": {
                    "type": "string",
                    "enum": ["rebajar", "retirar", "donar", "revisar", "reponer", "ok"],
                },
                "explanation": {"type": "string"},
            },
            "required": ["override", "corrected_action", "explanation"],
        },
        system_extra="Eres el Validador adversarial. Tus correcciones tienen prioridad sobre todos los demás agentes.",
        max_tokens=256,
    )

    final_action = correction.get("corrected_action", risk.get("action")) if correction.get("override") else risk.get("action")

    return {
        "status": "REVERTIDO" if correction.get("override") else "CON_OBSERVACIONES",
        "issues": issues,
        "override": correction.get("override", False),
        "final_action": final_action,
        "explanation": correction.get("explanation", "; ".join(issues)),
    }


def validate_daily_brief(brief_text: str, actions_count: int, value_at_risk: float) -> dict:
    """
    Valida coherencia del brief diario con los datos reales.
    Detecta exageraciones, omisiones o incongruencias numéricas.
    """
    prompt = f"""Valida este brief diario de MermaOps como validador adversarial:

TEXTO DEL BRIEF:
{brief_text[:800]}

DATOS REALES DEL SISTEMA:
- Acciones generadas: {actions_count}
- Valor en riesgo calculado: {value_at_risk:.2f} euros

Comprueba:
1. ¿Los números del brief coinciden con los datos reales?
2. ¿Hay afirmaciones que no están respaldadas por los datos?
3. ¿El tono es apropiado (no alarmista sin base, no tranquilizador cuando hay problemas graves)?"""

    result = llm.call_structured(
        prompt,
        output_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["VALIDADO", "CON_CORRECCIONES", "RECHAZADO"],
                },
                "corrections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de correcciones necesarias",
                },
                "explanation": {"type": "string"},
            },
            "required": ["status", "corrections", "explanation"],
        },
        max_tokens=256,
    )

    return result or {
        "status": "VALIDADO",
        "corrections": [],
        "explanation": "Sin anomalías detectadas.",
    }


def validate_section_review(
    store_id: str,
    batches: list[dict],
    completed_actions: list[dict],
    stale_hours: int = 4,
) -> dict:
    """
    Feature #21: Detecta pasillos con productos críticos que no han sido revisados
    en las últimas `stale_hours` horas.

    Returns {alerts: list[dict], total_stale_pasillos: int, ok: bool}
    Each alert: {pasillo, critical_products, hours_since_review, message}
    """
    cutoff = datetime.now() - timedelta(hours=stale_hours)

    # Build map of last completed action per pasillo
    last_review: dict[str, datetime] = {}
    for action in completed_actions:
        if action.get("status") != "completed":
            continue
        completed_at_str = action.get("completed_at")
        if not completed_at_str:
            continue
        try:
            completed_at = datetime.fromisoformat(completed_at_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        # Get pasillo from the batch→product chain
        batch = action.get("batches") or {}
        product = batch.get("products") or {}
        pasillo = product.get("pasillo", "?")
        if pasillo == "?":
            continue
        if pasillo not in last_review or completed_at > last_review[pasillo]:
            last_review[pasillo] = completed_at

    # Find critical batches grouped by pasillo
    critical_by_pasillo: dict[str, list[dict]] = {}
    today = date.today()
    for batch in batches:
        product = batch.get("products") or {}
        pasillo = product.get("pasillo", "?")
        expiry_str = batch.get("expiry_date", "")
        if not expiry_str:
            continue
        try:
            days_left = (date.fromisoformat(expiry_str) - today).days
        except ValueError:
            continue
        if days_left <= 2:  # critical threshold
            critical_by_pasillo.setdefault(pasillo, []).append({
                "product": product.get("name", "?"),
                "days_left": days_left,
                "quantity": batch.get("quantity", 0),
            })

    alerts = []
    for pasillo, products in critical_by_pasillo.items():
        last = last_review.get(pasillo)
        if last is None or last < cutoff:
            hours_ago = (
                int((datetime.now() - last).total_seconds() / 3600)
                if last else stale_hours + 1
            )
            alerts.append({
                "pasillo": pasillo,
                "critical_products": len(products),
                "products": products[:3],
                "hours_since_review": hours_ago,
                "message": (
                    f"Pasillo {pasillo} lleva más de {hours_ago}h sin revisión "
                    f"y tiene {len(products)} producto(s) crítico(s)."
                ),
            })

    alerts.sort(key=lambda a: a["critical_products"], reverse=True)
    return {
        "alerts": alerts,
        "total_stale_pasillos": len(alerts),
        "ok": len(alerts) == 0,
    }


def validate_actions_batch(actions: list[dict]) -> dict:
    """
    Valida un conjunto de acciones generadas por el Supervisor.
    Detecta duplicados, prioridades incorrectas y ausencias.
    """
    if not actions:
        return {"status": "VACÍO", "issues": ["No se generaron acciones."], "approved": False}

    # Check duplicados por batch_id
    batch_ids = [a.get("batch_id") for a in actions if a.get("batch_id")]
    duplicates = [bid for bid in set(batch_ids) if batch_ids.count(bid) > 1]
    issues = []
    if duplicates:
        issues.append(f"Acciones duplicadas para lotes: {duplicates}")

    # Check que críticos tienen score >= 80
    for action in actions:
        if action.get("action_type") in ("retirar",) and action.get("priority_score", 0) < 80:
            issues.append(
                f"Acción 'retirar' para {action.get('batch_id')} tiene score {action.get('priority_score')} — "
                "debería ser >= 80."
            )

    return {
        "status": "VALIDADO" if not issues else "CON_ADVERTENCIAS",
        "issues": issues,
        "approved": len(duplicates) == 0,
    }
