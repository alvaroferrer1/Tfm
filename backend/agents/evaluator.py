"""
Evaluator Agent — análisis profundo de riesgo con extended thinking.
Razona sobre múltiples factores: días, valor, categoría, historial.
"""
from __future__ import annotations
from datetime import date
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
            budget_tokens=5000,
            max_tokens=8000,
        )

        # Parsear el JSON de la respuesta final
        import json as json_mod
        import re as re_mod
        # Extraer JSON del texto (puede venir con texto extra)
        json_match = re_mod.search(r'\{.*\}', response_text, re_mod.DOTALL)
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

def evaluate(
    product: dict,
    batches: list[dict],
    historical_context: str = "",
    warehouse_qty: int = 0,
) -> dict:
    """
    Evaluación completa de riesgo usando extended thinking de Claude.
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

    soonest = min(batches, key=lambda b: b["expiry_date"])
    try:
        days_left = (date.fromisoformat(soonest["expiry_date"]) - date.today()).days
    except (ValueError, KeyError):
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

    raw_score = base * multiplier * value_factor * warehouse_factor * mb_factor
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
        return reach_consensus(
            product=product,
            days_left=days_left,
            qty=qty,
            warehouse_qty=warehouse_qty,
            heuristic_score=heuristic_score,
        )

    # Extended thinking para CRÍTICO y ALTO (score >= 65) sin umbral de valor
    use_thinking = heuristic_score >= 65

    if use_thinking:
        return _evaluate_with_thinking(
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
        )

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
    return {
        "risk_level": heuristic_level,
        "score": heuristic_score,
        "action": action,
        "price_adjustment_pct": discount_map.get(heuristic_level, 0),
        "reasoning": (
            f"{days_left} días hasta caducidad, {qty} unidades en tienda, "
            f"valor en riesgo {total_value_at_risk} euros."
            + (f" ({critical_batches} lotes críticos simultáneos)" if critical_batches > 1 else "")
        ),
        "thinking_summary": "",
        "days_left": days_left,
        "total_value_at_risk": total_value_at_risk,
        "critical_batches_count": critical_batches,
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
