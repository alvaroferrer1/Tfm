"""
Evaluator Agent — análisis profundo de riesgo con extended thinking.
Razona sobre múltiples factores: días, valor, categoría, historial, día semana, hora.
"""
from __future__ import annotations
from datetime import date, datetime
from backend.core import llm, knowledge

# Umbral de activación del consenso: solo casos extremos justifican 3× tokens
_CONSENSUS_SCORE_THRESHOLD = 90
_CONSENSUS_VALUE_THRESHOLD = 30.0  # euros en riesgo


# ── Scoring heurístico base ──────────────────────────────────────────────────

_URGENCY_BY_DAYS: list[tuple[int, int]] = [
    (0, 100), (1, 92), (2, 78), (3, 62), (4, 50), (5, 38), (7, 22), (999, 8)
]

_CATEGORY_MULTIPLIER: dict[str, float] = {
    "carne": 1.25,
    "pescado": 1.30,
    "lacteos": 1.10,
    "panaderia": 1.15,
    "fruta": 1.05,
    "verdura": 1.05,
}

# Índice de tráfico por día de semana (0=lunes … 6=domingo).
# Basado en patrones reales de supermercados españoles:
# viernes/sábado pico, lunes/martes mínimo, domingo cierre temprano.
_DAILY_TRAFFIC_INDEX: dict[int, float] = {
    0: 0.65,  # lunes — menor tráfico de la semana
    1: 0.72,  # martes
    2: 0.80,  # miércoles
    3: 0.88,  # jueves — sube para el fin de semana
    4: 1.10,  # viernes — pico entre semana
    5: 1.30,  # sábado — máximo tráfico
    6: 0.85,  # domingo — cierra a las 15h, tráfico matinal
}

# Índice de urgencia por hora del día.
# Tarde-noche: queda poco tiempo para vender → urgencia mayor.
_HOUR_URGENCY_INDEX: dict[int, float] = {
    **{h: 0.90 for h in range(8, 12)},   # 8–11h: mañana, tiempo de sobra
    **{h: 1.00 for h in range(12, 16)},  # 12–15h: mediodía, tráfico pico
    **{h: 1.10 for h in range(16, 20)},  # 16–19h: tarde, urgencia creciente
    **{h: 1.25 for h in range(20, 24)},  # 20–23h: casi cierre, urgencia alta
    **{h: 1.30 for h in range(0, 8)},    # 0–7h: madrugada/apertura, sin clientes
}


def _temporal_factor(days_left: int) -> float:
    """
    Factor de urgencia temporal basado en tráfico previsto y hora actual.

    Para productos que caducan en ≤3 días el timing importa: si quedan 2 días
    pero mañana es sábado (tráfico 1.30), la oportunidad de venta es alta →
    reduce urgencia. Si es domingo por la noche y caduca mañana lunes (tráfico 0.65),
    la urgencia es máxima.

    Para días > 3, el factor es neutro (1.0) porque el timing exacto no importa tanto.
    """
    if days_left > 3:
        return 1.0

    now = datetime.now()
    today_wd = now.weekday()
    hour_factor = _HOUR_URGENCY_INDEX.get(now.hour, 1.0)

    # Tráfico acumulado en los días restantes hasta caducidad
    traffic_days = max(1, days_left)
    avg_traffic = sum(
        _DAILY_TRAFFIC_INDEX.get((today_wd + d) % 7, 0.80)
        for d in range(traffic_days)
    ) / traffic_days

    # Normalizar: tráfico medio esperado (0.90) → factor 1.0
    # Alto tráfico (sábado) → oportunidad de venta → urgencia algo menor
    # Bajo tráfico (lunes) → difícil vender → urgencia mayor
    traffic_factor = 0.90 / avg_traffic

    return round(hour_factor * traffic_factor, 3)


def _confidence_pct(score: int, days_left: int, qty: int, value_at_risk: float) -> int:
    """
    Confianza en la decisión (0-100%).
    Alta confianza: producto muy próximo a caducar con valor alto claro.
    Baja confianza: score borderline (60-75) o datos incompletos.
    """
    # Caso claro: > 7 días o caducado → máxima confianza
    if days_left > 7 or days_left <= 0:
        return 95
    # Zona borderline: 60–80 → confianza media
    if 60 <= score <= 80:
        confidence = 60 + int((score - 60) / 20 * 20)  # 60-80
    elif score > 80:
        confidence = 80 + min(15, int(value_at_risk / 10))
    else:
        confidence = 70

    # Volumen conocido mejora confianza
    if qty > 0:
        confidence = min(99, confidence + 5)

    return confidence


def _base_score(days_left: int) -> int:
    for threshold, score in _URGENCY_BY_DAYS:
        if days_left <= threshold:
            return score
    return 5


def _safe_days_left(expiry_str: str) -> int:
    """Returns days until expiry, or 999 on parse error."""
    try:
        return (date.fromisoformat(expiry_str) - date.today()).days
    except (ValueError, TypeError):
        return 999


def _multi_batch_factor(batches: list[dict], critical_window_days: int = 3) -> float:
    """
    Amplification factor when multiple batches of the same product expire soon.
    Each additional batch expiring within critical_window_days adds 15% more risk,
    capped at 1.60 (4 or more batches simultaneously critical).
    Economic intuition: if you have 3 batches of carne all expiring in 2 days,
    it's not just 1× harder to clear — it's geometrically harder.
    """
    critical_count = sum(
        1 for b in batches
        if _safe_days_left(b.get("expiry_date", "")) <= critical_window_days
    )
    return min(1.60, 1.0 + 0.15 * max(0, critical_count - 1))


def _risk_level(score: int) -> str:
    if score >= 85:
        return "CRÍTICO"
    if score >= 65:
        return "ALTO"
    if score >= 40:
        return "MEDIO"
    return "BAJO"


def _action_from_risk(risk_level: str, days_left: int, category: str) -> str:
    """
    Acción operativa basada en nivel de riesgo, días restantes y categoría.
    La categoría es relevante para caducidades ≤0: el pan caducado se dona,
    la carne/pescado se retira (no es seguro donar producto cárnico expirado).
    """
    _DONATABLE_EXPIRED = {"panaderia", "bolleria", "fruta", "verdura", "legumbres"}
    _cat = category.lower() if category else ""

    if days_left <= 0:
        # Normativa: pan y frescos vegetales se pueden donar si caducan hoy
        # Carne, pescado, lácteos: retirar siempre por seguridad alimentaria (CE 178/2002)
        return "donar" if _cat in _DONATABLE_EXPIRED else "retirar"

    if risk_level == "CRÍTICO":
        return "rebajar"
    if risk_level == "ALTO":
        return "rebajar"
    if risk_level == "MEDIO":
        return "revisar"
    return "ok"


# ── Núcleo con extended thinking para productos críticos/altos ───────────────

def _evaluate_with_thinking(
    product: dict,
    soonest: dict,
    days_left: int,
    qty: int,
    price: float,
    cost: float,
    category: str,
    name: str,
    total_value_at_risk: float,
    warehouse_qty: int,
    heuristic_score: int,
    heuristic_level: str,
    regulation_context: str,
    historical_context: str,
    fast: bool = False,
) -> dict:
    """
    Evaluación con extended thinking REAL — Claude activa el modo thinking
    para razonar internamente antes de producir la respuesta.
    Solo se llama para productos CRÍTICO y ALTO.
    """
    prompt = f"""Debes decidir la acción operativa óptima para este producto de alto riesgo.

PRODUCTO:
- Nombre: {name}
- Categoría: {category}
- Precio: {price} euros | Coste: {cost} euros | Margen mínimo: {round(cost * 1.05, 2)} euros
- Días hasta caducidad: {days_left}
- Cantidad en tienda: {qty} unidades
- Stock en almacén: {warehouse_qty} unidades
- Valor total en riesgo: {total_value_at_risk} euros

ANÁLISIS HEURÍSTICO PREVIO: Score {heuristic_score}/100 — Nivel {heuristic_level}

NORMATIVA APLICABLE:
{regulation_context}

CONTEXTO HISTÓRICO (patrones anteriores):
{historical_context or "Sin datos históricos disponibles."}

Razona internamente sobre:
1. ¿El score heurístico es correcto o hay factores que lo ajustan?
2. ¿Cuál es la acción más rentable: rebajar, retirar, donar, mover?
3. ¿Qué descuento exacto (0-70%) maximiza ingresos sin romper el margen mínimo?
4. ¿La normativa alimentaria cambia la decisión?
5. ¿Qué instrucción específica de 1 línea necesita el empleado?

Responde con un JSON que contenga: score (int 0-100), risk_level (CRÍTICO/ALTO/MEDIO/BAJO),
action (rebajar/retirar/donar/revisar/reponer/ok), price_adjustment_pct (int 0-70),
reasoning (string corto para el empleado), thinking_summary (resumen interno)."""

    # Thinking budget dinámico: más presupuesto cuando la decisión importa más.
    # Casos borderline (score 65-79) necesitan razonamiento más profundo que casos obvios (90+).
    # Valor alto en riesgo justifica más tokens de razonamiento.
    if fast:
        # Scans interactivos: balance entre velocidad y calidad
        if total_value_at_risk > 100 or (65 <= heuristic_score <= 79):
            _thinking_budget = 2500  # borderline o alta valor → más razonamiento
        else:
            _thinking_budget = 1200  # caso claro → rápido
        _fast_mode = True
    else:
        # Briefs: razonamiento sin restricción de tiempo
        if total_value_at_risk > 200 or heuristic_score >= 90:
            _thinking_budget = 8000  # alto impacto → máximo razonamiento
        elif 65 <= heuristic_score <= 79:
            _thinking_budget = 6000  # borderline → razonamiento profundo
        else:
            _thinking_budget = 4000  # estándar
        _fast_mode = False

    # Extended thinking REAL — Claude razona antes de responder
    try:
        response_text, thinking_block = llm.call_with_thinking(
            prompt,
            system_extra=(
                "Eres el Evaluador de MermaOps. Analizas productos de alto riesgo alimentario. "
                "Razona en profundidad — tienes acceso al bloque de thinking para deliberar. "
                "Prioriza la rentabilidad dentro de los límites de seguridad alimentaria. "
                "Tu respuesta final debe ser un JSON válido sin markdown."
            ),
            budget_tokens=_thinking_budget,
            max_tokens=8000,
            fast=_fast_mode,
        )

        # Parsear el JSON de la respuesta final
        import json as json_mod
        import re as re_mod
        # Extraer JSON del texto (puede venir con texto extra)
        json_match = re_mod.search(r'\{.*?\}', response_text, re_mod.DOTALL)
        if json_match:
            result = json_mod.loads(json_match.group())
            if result.get("score") is not None:
                return {
                    "risk_level": result.get("risk_level", heuristic_level),
                    "score": int(result.get("score", heuristic_score)),
                    "action": result.get("action", "revisar"),
                    "price_adjustment_pct": int(result.get("price_adjustment_pct", 0)),
                    "reasoning": result.get("reasoning", ""),
                    "thinking_summary": thinking_block[:500] if thinking_block else "",
                    "days_left": days_left,
                    "total_value_at_risk": total_value_at_risk,
                }
    except Exception as e:
        import logging
        logging.getLogger("mermaops.evaluator").warning(
            f"Extended thinking falló para {name}: {e}. Usando structured output."
        )

    # Fallback: structured output si el thinking falla (ej. modelo no soporta thinking)
    result = llm.call_structured(
        prompt,
        output_schema={
            "type": "object",
            "properties": {
                "score": {"type": "integer", "description": "Score 0-100"},
                "risk_level": {"type": "string", "enum": ["CRÍTICO", "ALTO", "MEDIO", "BAJO"]},
                "action": {"type": "string", "enum": ["rebajar", "retirar", "donar", "revisar", "reponer", "ok"]},
                "price_adjustment_pct": {"type": "integer", "description": "Descuento % 0-70"},
                "reasoning": {"type": "string", "description": "Instrucción para el empleado"},
                "thinking_summary": {"type": "string"},
            },
            "required": ["score", "risk_level", "action", "price_adjustment_pct", "reasoning"],
        },
        system_extra=(
            "Eres el Evaluador de MermaOps. Analiza productos de alto riesgo alimentario. "
            "Prioriza rentabilidad dentro de los límites de seguridad alimentaria."
        ),
        max_tokens=1500,
    )

    if result and result.get("score") is not None:
        return {
            "risk_level": result.get("risk_level", heuristic_level),
            "score": result.get("score", heuristic_score),
            "action": result.get("action", "revisar"),
            "price_adjustment_pct": result.get("price_adjustment_pct", 0),
            "reasoning": result.get("reasoning", ""),
            "thinking_summary": result.get("thinking_summary", ""),
            "days_left": days_left,
            "total_value_at_risk": total_value_at_risk,
        }

    # Último fallback: heurístico puro
    action = _action_from_risk(heuristic_level, days_left, category)
    return {
        "risk_level": heuristic_level,
        "score": heuristic_score,
        "action": action,
        "price_adjustment_pct": 50 if days_left <= 1 else 40 if days_left <= 2 else 30,
        "reasoning": f"{days_left} días, {qty} uds, {total_value_at_risk} euros en riesgo.",
        "thinking_summary": "",
        "days_left": days_left,
        "total_value_at_risk": total_value_at_risk,
    }


# ── Evaluate con extended thinking ──────────────────────────────────────────

def _estimate_effort_minutes(action: str, qty: int) -> int:
    """
    Estima los minutos de trabajo que requiere ejecutar la acción.
    Útil para que el encargado planifique el turno y no se lleve sorpresas.
    Basado en tiempos reales de operación en supermercados españoles:
      - Rebajar: cambiar etiqueta de precio (~15s/ud para pegatina manual)
      - Retirar: sacar de estantería y llevar a almacén (~10s/ud)
      - Donar: preparar cajas, documentar albarán (~30s/ud)
      - Mover: llevar de almacén a lineal y colocar (~20s/ud)
    """
    secs_per_unit = {
        "rebajar": 15,
        "retirar": 10,
        "donar": 30,
        "mover": 20,
        "revisar": 5,
    }.get(action, 10)
    total_secs = qty * secs_per_unit
    return max(1, round(total_secs / 60))


def evaluate(
    product: dict,
    batches: list[dict],
    historical_context: str = "",
    warehouse_qty: int = 0,
    fast: bool = False,
) -> dict:
    """
    Evaluación completa de riesgo usando extended thinking de Claude.
    fast=True: usa thinking acotado (1500 tokens) para scans interactivos — responde en <10s.
    fast=False: usa adaptive thinking para análisis profundos en briefs.
    Devuelve un dict estructurado con todos los campos necesarios para el Supervisor.
    """
    if not batches:
        return {
            "risk_level": "BAJO",
            "score": 0,
            "action": "ok",
            "reasoning": "Sin lotes activos.",
            "price_adjustment_pct": 0,
            "thinking_summary": "",
        }

    soonest = min(batches, key=lambda b: b.get("expiry_date") or "9999-99-99")
    try:
        days_left = (date.fromisoformat(soonest["expiry_date"]) - date.today()).days
    except (ValueError, KeyError, TypeError):
        days_left = 999

    qty = soonest.get("quantity", 0)
    price = float(product.get("price", 0))
    cost = float(product.get("cost", 0))
    category = product.get("category", "general").lower()
    name = product.get("name", "desconocido")

    # Valor económico real en riesgo: todos los lotes que caducan en ≤7 días,
    # no solo el lote más próximo. El valor total determinará si se activa consenso.
    near_expiry_qty = sum(
        b.get("quantity", 0) for b in batches
        if _safe_days_left(b.get("expiry_date", "")) <= 7
    )
    total_value_at_risk = round(near_expiry_qty * price, 2)

    # Puntuación heurística base
    base = _base_score(days_left)
    multiplier = _CATEGORY_MULTIPLIER.get(category, 1.0)

    # Volumen amplifica el riesgo económico
    value_factor = min(1.3, 1.0 + (total_value_at_risk / 100) * 0.1)

    # Almacén lleno + poco tiempo = doble problema
    warehouse_factor = 1.1 if warehouse_qty > 0 and days_left <= 3 else 1.0

    # Múltiples lotes críticos simultáneos — el riesgo se amplifica geométricamente
    # porque cada lote adicional exige tiempo de gestión y espacio en tienda
    mb_factor = _multi_batch_factor(batches)

    # Factor temporal: día de semana + hora. Un producto que caduca mañana sábado
    # (tráfico 1.30) tiene más oportunidad de venta que el mismo caducando el lunes.
    temporal = _temporal_factor(days_left)

    # Factor de esfuerzo operativo: tareas de alto volumen necesitan más tiempo de personal.
    # No es lo mismo rebajar 3 ensaladas (1 min) que reeetiquetar 80 yogures (20 min).
    # Para alertar al encargado, aumentamos el score cuando el volumen es alto Y el tiempo escaso.
    # Umbral operativo: >30 unidades en <3 días = esfuerzo significativo de reposición/etiquetado.
    _effort_factor = 1.0
    if days_left <= 3 and qty > 30:
        _effort_factor = min(1.15, 1.0 + (qty - 30) / 200)  # +1% por cada 2 uds sobre 30, máx +15%

    raw_score = base * multiplier * value_factor * warehouse_factor * mb_factor * temporal * _effort_factor
    heuristic_score = min(100, int(raw_score))
    heuristic_level = _risk_level(heuristic_score)

    # Normativa aplicable
    regulation_context = knowledge.get_context_for_decision(
        category, days_left, _action_from_risk(heuristic_level, days_left, category)
    )

    # Consenso: tres agentes en paralelo para casos extremos de alto impacto económico.
    # Activación doble: score muy alto Y valor real en riesgo.
    use_consensus = (
        heuristic_score >= _CONSENSUS_SCORE_THRESHOLD
        and total_value_at_risk >= _CONSENSUS_VALUE_THRESHOLD
    )

    if use_consensus:
        from backend.agents.consensus import reach_consensus
        result = reach_consensus(
            product=product,
            days_left=days_left,
            qty=qty,
            warehouse_qty=warehouse_qty,
            heuristic_score=heuristic_score,
        )
        result.setdefault("confidence_pct", _confidence_pct(result.get("score", heuristic_score), days_left, qty, total_value_at_risk))
        result.setdefault("temporal_factor", temporal)
        return result

    # Extended thinking para CRÍTICO y ALTO (score >= 65) sin umbral de valor
    use_thinking = heuristic_score >= 65

    if use_thinking:
        result = _evaluate_with_thinking(
            product=product,
            soonest=soonest,
            days_left=days_left,
            qty=qty,
            price=price,
            cost=cost,
            category=category,
            name=name,
            total_value_at_risk=total_value_at_risk,
            warehouse_qty=warehouse_qty,
            heuristic_score=heuristic_score,
            heuristic_level=heuristic_level,
            regulation_context=regulation_context,
            historical_context=historical_context,
            fast=fast,
        )
        result.setdefault("confidence_pct", _confidence_pct(result.get("score", heuristic_score), days_left, qty, total_value_at_risk))
        result.setdefault("temporal_factor", temporal)
        return result

    # Extended thinking para casos no triviales (score >= 30 o hay historial)
    if heuristic_score >= 30 or historical_context:
        prompt = f"""Analiza el riesgo de merma de este producto y decide la acción óptima.

DATOS DEL PRODUCTO:
- Nombre: {name}
- Categoría: {category}
- Precio de venta: {price} euros
- Coste: {cost} euros
- Días hasta caducidad: {days_left}
- Cantidad en tienda: {qty} unidades
- Stock en almacén: {warehouse_qty} unidades
- Valor total en riesgo: {total_value_at_risk} euros
- Lotes activos totales: {len(batches)}

CONTEXTO HISTÓRICO:
{historical_context or "Sin patrones históricos disponibles."}

NORMATIVA APLICABLE:
{regulation_context}

ANÁLISIS HEURÍSTICO PREVIO:
Puntuación base: {heuristic_score}/100 — Nivel: {heuristic_level}

Razona profundamente sobre:
1. ¿Es el score heurístico correcto o hay factores que lo ajustan?
2. ¿Cuál es la acción más rentable (rebajar, retirar, donar, revisar, reponer)?
3. ¿Qué porcentaje de descuento exacto maximiza la probabilidad de venta sin perder margen?
4. ¿Hay contraindicaciones según la normativa?
5. ¿Qué instrucción específica debe recibir el empleado?

Responde con el JSON de la herramienta structured_output."""

        result = llm.call_structured(
            prompt,
            output_schema={
                "type": "object",
                "properties": {
                    "score": {
                        "type": "integer",
                        "description": "Puntuación final de riesgo 0-100",
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["CRÍTICO", "ALTO", "MEDIO", "BAJO"],
                    },
                    "action": {
                        "type": "string",
                        "enum": ["rebajar", "retirar", "donar", "revisar", "reponer", "ok"],
                    },
                    "price_adjustment_pct": {
                        "type": "integer",
                        "description": "Porcentaje de descuento recomendado (0-70)",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Explicación del razonamiento en una línea para el empleado",
                    },
                    "thinking_summary": {
                        "type": "string",
                        "description": "Resumen interno del análisis profundo",
                    },
                },
                "required": ["score", "risk_level", "action", "price_adjustment_pct", "reasoning"],
            },
            system_extra=(
                "Eres el Evaluador de MermaOps. Tu análisis determina las decisiones operativas. "
                "Sé riguroso con la normativa alimentaria. Prioriza la rentabilidad dentro de la seguridad."
            ),
            max_tokens=1024,
        )

        if result and result.get("score") is not None:
            score_out = result.get("score", heuristic_score)
            return {
                "risk_level": result.get("risk_level", heuristic_level),
                "score": score_out,
                "action": result.get("action", "revisar"),
                "price_adjustment_pct": result.get("price_adjustment_pct", 0),
                "reasoning": result.get("reasoning", ""),
                "thinking_summary": result.get("thinking_summary", ""),
                "days_left": days_left,
                "total_value_at_risk": total_value_at_risk,
                "confidence_pct": _confidence_pct(score_out, days_left, qty, total_value_at_risk),
                "temporal_factor": temporal,
            }

    # Respuesta heurística rápida para riesgo bajo
    action = _action_from_risk(heuristic_level, days_left, category)
    discount_map = {
        "CRÍTICO": 50 if days_left <= 1 else 40,
        "ALTO": 30,
        "MEDIO": 20,
        "BAJO": 0,
    }
    critical_batches = sum(
        1 for b in batches
        if _safe_days_left(b.get("expiry_date", "")) <= 3
    )
    temporal_note = ""
    if days_left <= 3 and temporal != 1.0:
        if temporal < 1.0:
            temporal_note = " (tráfico alto este fin de semana — oportunidad de venta)"
        else:
            temporal_note = " (tráfico bajo próximos días — actuar cuanto antes)"

    return {
        "risk_level": heuristic_level,
        "score": heuristic_score,
        "action": action,
        "price_adjustment_pct": discount_map.get(heuristic_level, 0),
        "reasoning": (
            f"{days_left} días hasta caducidad, {qty} unidades en tienda, "
            f"valor en riesgo {total_value_at_risk} euros."
            + (f" ({critical_batches} lotes críticos simultáneos)" if critical_batches > 1 else "")
            + temporal_note
        ),
        "thinking_summary": "",
        "days_left": days_left,
        "total_value_at_risk": total_value_at_risk,
        "critical_batches_count": critical_batches,
        "confidence_pct": _confidence_pct(heuristic_score, days_left, qty, total_value_at_risk),
        "temporal_factor": temporal,
        "effort_minutes": _estimate_effort_minutes(action, qty),
    }


def evaluate_batch(
    product: dict,
    batches: list[dict],
    historical_context: str = "",
    warehouse_qty: int = 0,
) -> str:
    """Versión que devuelve texto — para compatibilidad con reporter."""
    result = evaluate(product, batches, historical_context, warehouse_qty)
    return (
        f"{result['risk_level']} ({result['score']}/100) — "
        f"Acción: {result['action'].upper()} — {result['reasoning']}"
    )


# ── Auto-calibración mensual de multiplicadores ───────────────────────────────
# El Evaluador ajusta sus propios umbrales basándose en outcomes reales.
# Pattern: Afresh AI simulation — offline counterfactual evaluation.
# Llama esto desde el scheduler mensual para que el modelo mejore con el tiempo.

def auto_calibrate_from_outcomes(store_id: str) -> dict:
    """
    Recalibra _URGENCY_BY_DAYS y _CATEGORY_MULTIPLIER basándose en outcomes reales.

    Lógica: si en el historial de un mes, las rebajas de carne al 30% vendieron el 95%
    del stock pero las rebajas de pan al mismo descuento solo vendieron el 40%,
    el multiplicador de pan debe subir (necesita descuentos más agresivos).

    Returns dict con ajustes aplicados y métricas de calibración.
    """
    import json
    import logging as _log
    from backend.core import memory as _mem, llm as _llm

    logger = _log.getLogger("mermaops.evaluator")

    try:
        # Recuperar feedback acumulado de los últimos 30 días
        from backend.core.memory import get_daily_decision_feedback
        feedback = get_daily_decision_feedback(store_id, days_back=30)
        outcomes = feedback.get("top_outcomes", [])

        if len(outcomes) < 10:
            logger.info(f"[calibrate] Insuficientes outcomes ({len(outcomes)}) — calibración omitida")
            return {"calibrated": False, "reason": "Pocos datos"}

        # Calcular efectividad por categoría
        by_category: dict[str, list[str]] = {}
        for o in outcomes:
            cat = o.get("action_type", "general")
            result = o.get("result", "")
            by_category.setdefault(cat, []).append(result)

        adjustments = {}
        for cat, results in by_category.items():
            total = len(results)
            successful = sum(1 for r in results if r in ("vendido", "donado"))
            rate = successful / total if total > 0 else 0

            # Si efectividad < 60%: el multiplicador actual es insuficiente → subir
            if rate < 0.60 and cat in _CATEGORY_MULTIPLIER:
                old = _CATEGORY_MULTIPLIER[cat]
                _CATEGORY_MULTIPLIER[cat] = round(min(1.5, old * 1.05), 2)  # +5%, max 1.5
                adjustments[cat] = f"{old} → {_CATEGORY_MULTIPLIER[cat]} (+5%)"
            # Si efectividad > 90%: posiblemente descuentos demasiado agresivos → bajar
            elif rate > 0.90 and cat in _CATEGORY_MULTIPLIER:
                old = _CATEGORY_MULTIPLIER[cat]
                _CATEGORY_MULTIPLIER[cat] = round(max(0.8, old * 0.97), 2)  # -3%, min 0.8
                adjustments[cat] = f"{old} → {_CATEGORY_MULTIPLIER[cat]} (-3%)"

        if adjustments:
            # Persistir los nuevos multiplicadores en memoria para que sobrevivan reinicios
            _mem.remember(store_id, "evaluator_multipliers", json.dumps(_CATEGORY_MULTIPLIER))
            logger.info(f"[calibrate] Multiplicadores ajustados: {adjustments}")

        return {
            "calibrated": True,
            "adjustments": adjustments,
            "outcomes_analyzed": len(outcomes),
            "effectiveness_pct": feedback.get("effectiveness_pct", 0),
        }

    except Exception as e:
        logger.warning(f"[calibrate] Error en calibración: {e}")
        return {"calibrated": False, "reason": str(e)}


def load_calibrated_multipliers(store_id: str) -> None:
    """Carga multiplicadores calibrados desde memoria al arrancar. Llama al inicio."""
    try:
        import json
        from backend.core import memory as _mem
        raw = _mem.recall(store_id, "evaluator_multipliers")
        if raw:
            saved = json.loads(raw)
            for cat, val in saved.items():
                if cat in _CATEGORY_MULTIPLIER:
                    _CATEGORY_MULTIPLIER[cat] = float(val)
    except Exception:
        pass  # falla silenciosamente — usar defaults hardcoded
