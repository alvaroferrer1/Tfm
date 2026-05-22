"""
Consensus Engine — agentes razonan en paralelo (y secuencialmente) sobre decisiones de alto impacto.

Cuándo se activa: score heurístico >= 90 Y valor_en_riesgo >= 30 euros.
Son los casos donde el coste de equivocarse (pérdida económica real + riesgo
de seguridad alimentaria) justifica gastar tokens extra para ganar certeza.

Dos modos:
  1. CONSENSO PARALELO (score >= 90, value >= 30€):
     Tres perspectivas en paralelo con Haiku (rápido y barato).
     Mayoría 2/3 → resultado directo. Empate → árbitro Opus.

  2. DEBATE JEFFREY (score >= 95, value >= 50€):
     Cuatro roles razonan secuencialmente, cada uno ve el debate previo.
     Opus sintetiza la decisión final. Para casos donde el coste de error
     es máximo y la calidad de razonamiento supera la velocidad.

Cada resultado es compatible con el formato de evaluator.evaluate().
"""
from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor

from backend.core import llm

logger = logging.getLogger("mermaops.consensus")

_ACTION_ENUM = ["rebajar", "retirar", "donar", "revisar", "reponer", "ok"]

# Categorías donde la perspectiva de seguridad alimentaria pesa más.
# En carne/pescado un error cuesta salud — el voto de seguridad se amplifica.
_SAFETY_DOMINANT = {"carne", "pescado", "marisco", "lacteos"}
# Categorías donde el riesgo sanitario es bajo — rentabilidad pesa más.
_PROFIT_DOMINANT = {"conservas", "bebidas", "legumbres", "congelados"}

# Roles del debate Jeffrey — razonamiento secuencial, cada uno ve el debate previo
_DEBATE_ROLES = [
    {
        "name": "Pragmático",
        "persona": (
            "Eres el encargado de turno del súper. Piensas en qué puede ejecutar "
            "un empleado YA MISMO sin papeleos ni coordinación extra. "
            "Cuestiona cualquier acción que lleve más de 5 minutos."
        ),
    },
    {
        "name": "Crítico",
        "persona": (
            "Eres el inspector de sanidad del establecimiento. Buscas activamente "
            "razones para retirar. Ante cualquier duda de seguridad alimentaria "
            "exiges la opción más conservadora. Aplicas el Reglamento CE 178/2002."
        ),
    },
    {
        "name": "Visionario",
        "persona": (
            "Eres el director comercial. Ves el impacto a largo plazo: margen, reputación, "
            "fidelización. Propones opciones creativas: descuento flash, donación estratégica, "
            "bundle con productos próximos a caducar. El dinero perdido por tirar género "
            "es dinero que no se invierte en mejorar la tienda."
        ),
    },
    {
        "name": "Implementador",
        "persona": (
            "Eres el coordinador de operaciones. Escuchas al Pragmático, al Crítico y al "
            "Visionario y propones la síntesis más ejecutable. No inventas, sintetizas. "
            "Termina siempre tu respuesta con [CONSENSO: SÍ] si todos apuntan al mismo camino "
            "o [CONSENSO: NO] si hay discrepancia real entre los anteriores."
        ),
    },
]

_ARBITER_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": _ACTION_ENUM},
        "price_adjustment_pct": {"type": "integer"},
        "reasoning": {"type": "string"},
        "deciding_factor": {
            "type": "string",
            "description": "Qué perspectiva o argumento fue decisivo y por qué",
        },
    },
    "required": ["action", "price_adjustment_pct", "reasoning", "deciding_factor"],
}

_VOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": _ACTION_ENUM,
        },
        "confidence": {
            "type": "integer",
            "description": "Confianza en la decisión 0-100",
        },
        "reasoning": {
            "type": "string",
            "description": "Justificación en una línea",
        },
        "price_adjustment_pct": {
            "type": "integer",
            "description": "Porcentaje de descuento sugerido (0-70)",
        },
    },
    "required": ["action", "confidence", "reasoning", "price_adjustment_pct"],
}


def _ctx(product: dict, days_left: int, qty: int, warehouse_qty: int) -> str:
    value = round(qty * float(product.get("price", 0)), 2)
    margin = round(float(product.get("price", 0)) - float(product.get("cost", 0)), 2)
    return (
        f"Producto: {product.get('name')} | Categoría: {product.get('category', '?')}\n"
        f"Días hasta caducidad: {days_left} | Cantidad en tienda: {qty} uds | "
        f"Stock almacén: {warehouse_qty} uds\n"
        f"Precio: {product.get('price', 0)} € | Coste: {product.get('cost', 0)} € | "
        f"Margen unitario: {margin} € | Valor en riesgo: {value} €"
    )


# ── Las tres perspectivas ────────────────────────────────────────────────────

def _vote_safety(product: dict, days_left: int, qty: int, warehouse_qty: int) -> dict:
    result = llm.call_structured_fast(
        f"""Evalúa desde la perspectiva de SEGURIDAD ALIMENTARIA:

{_ctx(product, days_left, qty, warehouse_qty)}

Decide la acción que protege al consumidor.
Con {days_left} días, ¿es seguro vender con descuento o debe retirarse/donarse?""",
        output_schema=_VOTE_SCHEMA,
        system_extra=(
            "Eres el especialista en seguridad alimentaria de MermaOps. "
            "Aplicas el Reglamento (CE) 178/2002 y las normas españolas de etiquetado. "
            "Si la duda es entre seguridad y rentabilidad, la seguridad gana siempre."
        ),
        max_tokens=150,
    ) or {}
    return {
        "perspective": "seguridad",
        "action": result.get("action", "revisar"),
        "confidence": result.get("confidence", 50),
        "reasoning": result.get("reasoning", ""),
        "price_adjustment_pct": result.get("price_adjustment_pct", 0),
    }


def _vote_profitability(product: dict, days_left: int, qty: int, warehouse_qty: int) -> dict:
    result = llm.call_structured_fast(
        f"""Evalúa desde la perspectiva de RENTABILIDAD:

{_ctx(product, days_left, qty, warehouse_qty)}

¿Qué acción recupera más valor económico?
Un descuento agresivo que vacía el lote es mejor que tirar el género.""",
        output_schema=_VOTE_SCHEMA,
        system_extra=(
            "Eres el analista financiero de MermaOps. "
            "El coste de tirar un producto es su precio de coste. "
            "Maximiza el ingreso recuperado dentro de los límites de seguridad."
        ),
        max_tokens=150,
    ) or {}
    return {
        "perspective": "rentabilidad",
        "action": result.get("action", "rebajar"),
        "confidence": result.get("confidence", 50),
        "reasoning": result.get("reasoning", ""),
        "price_adjustment_pct": result.get("price_adjustment_pct", 0),
    }


def _vote_operations(product: dict, days_left: int, qty: int, warehouse_qty: int) -> dict:
    result = llm.call_structured_fast(
        f"""Evalúa desde la perspectiva de OPERACIONES DE TIENDA:

{_ctx(product, days_left, qty, warehouse_qty)}

¿Qué acción puede ejecutar el empleado ahora mismo?
Considera el tiempo real de cada operación y la carga del turno.""",
        output_schema=_VOTE_SCHEMA,
        system_extra=(
            "Eres el jefe de operaciones de MermaOps. "
            "Una acción sencilla ejecutada es mejor que una perfecta que se pospone. "
            "Valora la rapidez y simplicidad para el empleado de tienda."
        ),
        max_tokens=150,
    ) or {}
    return {
        "perspective": "operaciones",
        "action": result.get("action", "revisar"),
        "confidence": result.get("confidence", 50),
        "reasoning": result.get("reasoning", ""),
        "price_adjustment_pct": result.get("price_adjustment_pct", 0),
    }


# ── Modo debate Jeffrey (casos extremos) ────────────────────────────────────

def _jeffrey_debate(
    product: dict,
    days_left: int,
    qty: int,
    warehouse_qty: int,
    heuristic_score: int,
) -> dict:
    """
    Cuatro agentes razonan secuencialmente sobre un caso de riesgo extremo.
    Cada agente ve el debate previo completo, generando razonamiento acumulativo.
    El Implementador señala si hay consenso. Opus sintetiza la decisión final.

    Activado cuando: score >= 95 Y valor en riesgo >= 50 euros.
    Usa Haiku para los 4 roles (rápido) y Opus para la síntesis (profundo).
    """
    name = product.get("name", "?")
    value_at_risk = round(qty * float(product.get("price", 0)), 2)
    ctx = _ctx(product, days_left, qty, warehouse_qty)

    logger.info(
        f"[consensus] DEBATE JEFFREY activado para '{name}' "
        f"— score={heuristic_score}, valor={value_at_risk}€"
    )

    transcript: list[str] = []
    consensus_reached = False

    for role in _DEBATE_ROLES:
        prev_text = (
            "\n\nDEBATE HASTA AHORA:\n" + "\n\n".join(transcript)
            if transcript else ""
        )
        response = llm.call_fast(
            f"CASO CRÍTICO — Análisis urgente requerido:\n\n{ctx}"
            f"{prev_text}\n\n"
            f"Como {role['name']}: tu posición en máximo 80 palabras.",
            system_extra=role["persona"],
            max_tokens=200,
        )
        transcript.append(f"[{role['name']}]: {response}")

        if role["name"] == "Implementador" and "[CONSENSO: SÍ]" in response.upper():
            consensus_reached = True
            logger.info(f"[consensus] Debate Jeffrey — consenso señalado por Implementador")

    debate_log = "\n\n".join(transcript)

    # Opus sintetiza el debate completo con output estructurado
    synthesis = llm.call_structured_deep(
        f"""Has supervisado este debate multi-agente sobre un producto de riesgo extremo.
Toma la decisión final integrando las cuatro perspectivas.

CONTEXTO DEL PRODUCTO:
{ctx}

DEBATE COMPLETO:
{debate_log}

{'NOTA: El Implementador ha señalado consenso entre los agentes.' if consensus_reached else 'NOTA: No hubo consenso claro — usa tu criterio como árbitro.'}""",
        output_schema=_ARBITER_SCHEMA,
        system_extra=(
            "Eres el árbitro final de MermaOps con visión completa del debate. "
            "Integra seguridad alimentaria, rentabilidad y ejecutabilidad. "
            "Tu deciding_factor debe citar qué argumento del debate fue determinante."
        ),
        max_tokens=500,
    ) or {}

    return _build_result(
        action=synthesis.get("action", "revisar"),
        confidence=97 if consensus_reached else 90,
        price_adjustment_pct=synthesis.get("price_adjustment_pct", 0),
        reasoning=synthesis.get("reasoning", "Debate Jeffrey — síntesis Opus"),
        thinking_summary=(
            f"Debate Jeffrey 4 agentes ({'consenso' if consensus_reached else 'árbitro Opus'}) — "
            f"{synthesis.get('deciding_factor', '')[:100]}"
        ),
        days_left=days_left,
        total_value_at_risk=value_at_risk,
        heuristic_score=heuristic_score,
    )


# ── Motor principal ──────────────────────────────────────────────────────────

def reach_consensus(
    product: dict,
    days_left: int,
    qty: int,
    warehouse_qty: int = 0,
    heuristic_score: int = 90,
) -> dict:
    """
    Tres perspectivas votan en paralelo. Mayoría → resultado directo.
    Empate (3 acciones distintas) → árbitro Claude sintetiza.

    Devuelve dict compatible con evaluator.evaluate():
      {risk_level, score, action, price_adjustment_pct, reasoning,
       thinking_summary, days_left, total_value_at_risk, consensus_used}
    """
    name = product.get("name", "?")
    value_at_risk = round(qty * float(product.get("price", 0)), 2)
    logger.info(f"[consensus] Iniciando para '{name}' — {days_left}d, score={heuristic_score}, valor={value_at_risk}€")

    # Debate Jeffrey para casos de riesgo máximo
    if heuristic_score >= 95 and value_at_risk >= 50:
        return _jeffrey_debate(product, days_left, qty, warehouse_qty, heuristic_score)

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="consensus") as pool:
        f_safety = pool.submit(_vote_safety, product, days_left, qty, warehouse_qty)
        f_profit = pool.submit(_vote_profitability, product, days_left, qty, warehouse_qty)
        f_ops = pool.submit(_vote_operations, product, days_left, qty, warehouse_qty)

        try:
            votes = [
                f_safety.result(timeout=25),
                f_profit.result(timeout=25),
                f_ops.result(timeout=25),
            ]
        except Exception as e:
            logger.error(f"[consensus] Timeout en perspectivas para '{name}': {e}")
            return _fallback(product, days_left, qty, heuristic_score)

    # ── Pesos por categoría — ajustar confianza antes de ponderar ────────────
    # Para carne/pescado la seguridad alimentaria tiene más peso que la rentabilidad.
    # Para conservas/bebidas la rentabilidad domina porque el riesgo sanitario es mínimo.
    category = product.get("category", "").lower()
    if category in _SAFETY_DOMINANT:
        votes = [
            {**v, "confidence": min(100, v["confidence"] + 20)}
            if v["perspective"] == "seguridad" else v
            for v in votes
        ]
        logger.debug(f"[consensus] '{name}': boost seguridad +20 (categoría {category})")
    elif category in _PROFIT_DOMINANT:
        votes = [
            {**v, "confidence": min(100, v["confidence"] + 15)}
            if v["perspective"] == "rentabilidad" else v
            for v in votes
        ]
        logger.debug(f"[consensus] '{name}': boost rentabilidad +15 (categoría {category})")

    # ── Contar votos ──────────────────────────────────────────────────────────

    buckets: dict[str, list[dict]] = {}
    for v in votes:
        buckets.setdefault(v["action"], []).append(v)

    winner_action = max(buckets, key=lambda a: len(buckets[a]))
    winner_count = len(buckets[winner_action])

    log_line = " | ".join(
        f"{v['perspective']}={v['action']}({v['confidence']}%)" for v in votes
    )
    logger.info(f"[consensus] '{name}': {log_line} → {winner_action} ({winner_count}/3)")

    # ── Unanimidad con alta confianza: fast-path sin arbiter ─────────────────
    # Si los 3 agentes coinciden Y todos tienen confianza ≥70, el resultado es claro.
    # Promedio ponderado por confianza en lugar de simple promedio.

    if winner_count >= 2:
        winning = buckets[winner_action]

        # Descuento ponderado por confianza — votos más seguros pesan más
        total_confidence = sum(v["confidence"] for v in winning)
        if total_confidence > 0:
            weighted_discount = int(
                sum(v["price_adjustment_pct"] * v["confidence"] for v in winning)
                / total_confidence
            )
        else:
            weighted_discount = sum(v["price_adjustment_pct"] for v in winning) // len(winning)

        avg_confidence = total_confidence // len(winning)

        # Boost de confianza cuando unanimidad (3/3) y todos seguros
        if winner_count == 3 and avg_confidence >= 70:
            avg_confidence = min(100, avg_confidence + 5)

        dissent = [v for v in votes if v["action"] != winner_action]
        dissent_note = ""
        if dissent:
            d = dissent[0]
            dissent_note = (
                f" (Disiente {d['perspective']} con confianza {d['confidence']}%: {d['reasoning'][:60]})"
            )

        vote_trace = " | ".join(
            f"{v['perspective']}→{v['action']}({v['confidence']}%)" for v in votes
        )

        return _build_result(
            action=winner_action,
            confidence=avg_confidence,
            price_adjustment_pct=weighted_discount,
            reasoning=winning[0]["reasoning"] + dissent_note,
            thinking_summary=(
                f"Consenso {winner_count}/3 ponderado por confianza — {vote_trace}"
            ),
            days_left=days_left,
            total_value_at_risk=round(qty * float(product.get("price", 0)), 2),
            heuristic_score=heuristic_score,
            vote_trace=votes,
        )

    # ── Empate: árbitro ───────────────────────────────────────────────────────

    logger.info(f"[consensus] '{name}': empate — activando árbitro")
    votes_text = "\n".join(
        f"- {v['perspective'].upper()}: {v['action']} "
        f"(confianza {v['confidence']}%, descuento {v['price_adjustment_pct']}%) — "
        f"{v['reasoning']}"
        for v in votes
    )

    arb = llm.call_structured_deep(
        f"""Tres especialistas discrepan sobre este producto de alto riesgo. Arbitra la decisión.

{_ctx(product, days_left, qty, warehouse_qty)}

VOTOS:
{votes_text}

Analiza las tres perspectivas. Decide la acción que mejor equilibra seguridad,
rentabilidad y ejecutabilidad. En caso de duda, prioriza la seguridad.""",
        output_schema=_ARBITER_SCHEMA,
        system_extra=(
            "Eres el árbitro final de MermaOps. Tu decisión es inapelable. "
            "Cuando hay empate, la seguridad alimentaria pesa más que la rentabilidad."
        ),
        max_tokens=400,
    ) or {}

    return _build_result(
        action=arb.get("action", "revisar"),
        confidence=80,
        price_adjustment_pct=arb.get("price_adjustment_pct", 0),
        reasoning=arb.get("reasoning", "Árbitro: decisión balanceada"),
        thinking_summary=f"Árbitro activado — {arb.get('deciding_factor', 'factor desconocido')}",
        days_left=days_left,
        total_value_at_risk=round(qty * float(product.get("price", 0)), 2),
        heuristic_score=heuristic_score,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_result(
    action: str,
    confidence: int,
    price_adjustment_pct: int,
    reasoning: str,
    thinking_summary: str,
    days_left: int,
    total_value_at_risk: float,
    heuristic_score: int,
    vote_trace: list | None = None,
) -> dict:
    # El score final combina el heurístico con la confianza del consenso
    adjusted_score = min(100, int(heuristic_score * 0.7 + confidence * 0.3))
    if adjusted_score >= 85:
        risk_level = "CRÍTICO"
    elif adjusted_score >= 65:
        risk_level = "ALTO"
    elif adjusted_score >= 40:
        risk_level = "MEDIO"
    else:
        risk_level = "BAJO"

    result = {
        "risk_level": risk_level,
        "score": adjusted_score,
        "action": action,
        "price_adjustment_pct": price_adjustment_pct,
        "reasoning": reasoning,
        "thinking_summary": thinking_summary,
        "days_left": days_left,
        "total_value_at_risk": total_value_at_risk,
        "consensus_used": True,
    }
    if vote_trace:
        result["vote_trace"] = [
            {
                "perspective": v["perspective"],
                "action": v["action"],
                "confidence": v["confidence"],
            }
            for v in vote_trace
        ]
    return result


def _fallback(product: dict, days_left: int, qty: int, heuristic_score: int) -> dict:
    """Fallback cuando el consenso falla — respuesta conservadora sin LLM."""
    action = "retirar" if days_left <= 0 else "rebajar" if days_left <= 2 else "revisar"
    return {
        "risk_level": "CRÍTICO" if heuristic_score >= 85 else "ALTO",
        "score": heuristic_score,
        "action": action,
        "price_adjustment_pct": 50 if days_left <= 1 else 40,
        "reasoning": f"Fallback (consenso no disponible): {days_left} días, {qty} uds.",
        "thinking_summary": "Consenso falló — heurístico aplicado como fallback",
        "days_left": days_left,
        "total_value_at_risk": round(qty * float(product.get("price", 0)), 2),
        "consensus_used": False,
    }
