"""
Episodic memory system — el Supervisor aprende patrones a lo largo del tiempo.
Los patrones se persisten en agent_memory (Supabase) y se recuperan en cada ciclo.

Incluye:
- Memoria clave-valor (patrones de velocidad, merma, proveedores)
- Episode summaries: resumen compacto de cada ciclo de Kuine
- Outcome tracking: seguimiento de si las decisiones funcionaron
"""
from __future__ import annotations
import json
import logging
from datetime import date, datetime, timezone
from backend.core import database

logger = logging.getLogger("mermaops.memory")


# ── Claves de memoria estándar ───────────────────────────────────────────────

KEY_CATEGORY_VELOCITY = "categoria_{category}_velocidad"
KEY_WEEKLY_MERMA = "merma_semana_{week}"
KEY_PEAK_HOURS = "horas_pico_venta"
KEY_SUPPLIER_QUALITY = "proveedor_{supplier}_calidad"
KEY_PRODUCT_PATTERN = "producto_{product_id}_patron"
KEY_DAILY_STATS = "stats_dia_{date}"


def recall(store_id: str, key: str) -> str | None:
    """Recupera un patrón de la memoria episódica. None si no existe."""
    try:
        return database.get_memory(store_id, key)
    except Exception:
        return None


def remember(store_id: str, key: str, value: str) -> None:
    """Persiste un patrón en la memoria episódica."""
    try:
        database.set_memory(store_id, key, value)
    except Exception as e:
        logger.warning(f"[memory] Error guardando patrón {key}: {e}")


def recall_category_velocity(store_id: str, category: str) -> str | None:
    key = KEY_CATEGORY_VELOCITY.format(category=category)
    return recall(store_id, key)


def remember_category_velocity(store_id: str, category: str, pattern: str) -> None:
    key = KEY_CATEGORY_VELOCITY.format(category=category)
    remember(store_id, key, pattern)


def recall_product_pattern(store_id: str, product_id: str) -> str | None:
    key = KEY_PRODUCT_PATTERN.format(product_id=product_id)
    return recall(store_id, key)


def remember_product_pattern(store_id: str, product_id: str, pattern: str) -> None:
    key = KEY_PRODUCT_PATTERN.format(product_id=product_id)
    remember(store_id, key, pattern)


def build_memory_context(store_id: str, categories: list[str] | None = None) -> str:
    """
    Construye un bloque de contexto histórico para incluir en el prompt del Supervisor.
    Recupera los patrones más relevantes y los formatea como texto.
    """
    lines = []

    # Patrones de categorías que interesan hoy
    if categories:
        for cat in categories[:5]:
            pattern = recall_category_velocity(store_id, cat)
            if pattern:
                lines.append(f"Velocidad de venta {cat}: {pattern}")

    # Estadísticas de merma recientes
    today = date.today()
    for days_back in [1, 7]:
        past = date.fromordinal(today.toordinal() - days_back)
        key = KEY_DAILY_STATS.format(date=past.isoformat())
        stat = recall(store_id, key)
        if stat:
            label = "ayer" if days_back == 1 else "hace 7 días"
            lines.append(f"Merma {label}: {stat}")

    # Horas pico
    peak = recall(store_id, KEY_PEAK_HOURS)
    if peak:
        lines.append(f"Horas pico de venta: {peak}")

    if not lines:
        return "Sin patrones históricos disponibles aún."
    return "\n".join(lines)


def record_daily_stats(store_id: str, value_lost: float, items_discarded: int) -> None:
    """Guarda estadísticas del día de cierre para memoria futura."""
    key = KEY_DAILY_STATS.format(date=date.today().isoformat())
    value = f"valor perdido {value_lost:.2f} euros, {items_discarded} productos retirados"
    remember(store_id, key, value)


def get_all_recent_patterns(store_id: str) -> dict[str, str]:
    """Devuelve todos los patrones disponibles para debug/reporting."""
    categories = ["panaderia", "lacteos", "carne", "pescado", "fruta", "verdura"]
    patterns = {}
    for cat in categories:
        v = recall_category_velocity(store_id, cat)
        if v:
            patterns[f"velocidad_{cat}"] = v
    today = date.today()
    for i in range(7):
        d = date.fromordinal(today.toordinal() - i)
        key = KEY_DAILY_STATS.format(date=d.isoformat())
        v = recall(store_id, key)
        if v:
            patterns[key] = v
    return patterns


# ── Episode summaries — resumen compacto de cada ciclo de Kuine ─────────────

KEY_EPISODE_SUMMARY = "episode_{date}_{hour}"
KEY_OUTCOME_TRACKING = "outcome_decision_{action_id}"
KEY_DECISION_FEEDBACK = "feedback_daily_{date}"


def create_episode_summary(
    store_id: str,
    actions_created: list[dict],
    actions_completed: list[dict],
    critical_count: int,
    value_at_risk: float,
    tools_used: list[str],
) -> None:
    """
    Guarda un resumen compacto de lo que ocurrió en un ciclo de Kuine.
    Estos summaries se recuperan para dar contexto histórico a futuros ciclos.
    """
    now = datetime.now(timezone.utc)
    key = KEY_EPISODE_SUMMARY.format(
        date=now.strftime("%Y-%m-%d"),
        hour=now.strftime("%H"),
    )
    summary = {
        "timestamp": now.isoformat(),
        "critical_count": critical_count,
        "value_at_risk_eur": round(value_at_risk, 2),
        "actions_created": len(actions_created),
        "actions_completed": len(actions_completed),
        "top_actions": [
            {
                "product": a.get("product_name", "?"),
                "type": a.get("action_type", "?"),
                "score": a.get("score", 0),
            }
            for a in (actions_created or [])[:5]
        ],
        "tools_used": tools_used[:10] if tools_used else [],
    }
    remember(store_id, key, json.dumps(summary, ensure_ascii=False))
    logger.debug(f"[memory] Episode summary guardado: {key}")


def get_recent_episodes(store_id: str, last_n_hours: int = 24) -> list[dict]:
    """Recupera los últimos N episodios de Kuine para contexto histórico."""
    now = datetime.now(timezone.utc)
    episodes = []
    for h in range(last_n_hours):
        hour_offset = now.hour - h
        day_offset = 0
        if hour_offset < 0:
            hour_offset += 24
            day_offset = 1
        from datetime import timedelta
        d = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        key = KEY_EPISODE_SUMMARY.format(date=d, hour=str(hour_offset).zfill(2))
        raw = recall(store_id, key)
        if raw:
            try:
                episodes.append(json.loads(raw))
            except Exception:
                episodes.append({"raw": raw})
    return episodes


def record_decision_outcome(
    store_id: str,
    action_id: str,
    action_type: str,
    product_name: str,
    recommended_score: int,
    actual_result: str,
    value_recovered_eur: float = 0.0,
) -> None:
    """
    Registra el resultado de una decisión: si funcionó o no.
    actual_result: 'vendido', 'donado', 'retirado', 'sin_efecto', 'no_completado'
    Estos outcomes se usan para calibrar el Evaluador con el tiempo.
    """
    key = KEY_OUTCOME_TRACKING.format(action_id=action_id)
    outcome = {
        "action_id": action_id,
        "action_type": action_type,
        "product": product_name,
        "score": recommended_score,
        "result": actual_result,
        "value_recovered_eur": round(value_recovered_eur, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    remember(store_id, key, json.dumps(outcome, ensure_ascii=False))

    # Acumular feedback diario para el resumen de rendimiento
    today = date.today().isoformat()
    fb_key = KEY_DECISION_FEEDBACK.format(date=today)
    existing_raw = recall(store_id, fb_key)
    try:
        existing = json.loads(existing_raw) if existing_raw else {"outcomes": [], "date": today}
    except Exception:
        existing = {"outcomes": [], "date": today}
    existing["outcomes"].append(outcome)
    remember(store_id, fb_key, json.dumps(existing, ensure_ascii=False))


def get_daily_decision_feedback(store_id: str, days_back: int = 1) -> dict:
    """
    Recupera el resumen de rendimiento de decisiones de los últimos N días.
    Úsalo en Chuwi para responder 'ayer apliqué X, resultado: Y'.
    """
    from datetime import timedelta
    results = []
    today = date.today()
    for i in range(1, days_back + 2):
        d = (today - timedelta(days=i)).isoformat()
        key = KEY_DECISION_FEEDBACK.format(date=d)
        raw = recall(store_id, key)
        if raw:
            try:
                data = json.loads(raw)
                results.append(data)
            except Exception:
                pass

    if not results:
        return {"message": "Sin datos de seguimiento de decisiones aún.", "outcomes": []}

    # Agregar todos los outcomes
    all_outcomes = []
    for r in results:
        all_outcomes.extend(r.get("outcomes", []))

    if not all_outcomes:
        return {"message": "Sin resultados de acciones registrados.", "outcomes": []}

    total = len(all_outcomes)
    sold = sum(1 for o in all_outcomes if o.get("result") == "vendido")
    donated = sum(1 for o in all_outcomes if o.get("result") == "donado")
    discarded = sum(1 for o in all_outcomes if o.get("result") == "retirado")
    value_recovered = sum(o.get("value_recovered_eur", 0) for o in all_outcomes)

    return {
        "period_days": days_back,
        "total_decisions": total,
        "sold": sold,
        "donated": donated,
        "discarded": discarded,
        "value_recovered_eur": round(value_recovered, 2),
        "effectiveness_pct": round((sold + donated) / total * 100) if total > 0 else 0,
        "top_outcomes": all_outcomes[:5],
    }


def build_rich_memory_context(store_id: str, categories: list[str] | None = None) -> str:
    """
    Contexto histórico enriquecido para el Supervisor: patrones + episodes recientes + feedback.
    Más informativo que build_memory_context básico.
    """
    lines = ["=== CONTEXTO HISTÓRICO ==="]

    # Patrones de velocidad de venta por categoría
    if categories:
        for cat in categories[:4]:
            pattern = recall_category_velocity(store_id, cat)
            if pattern:
                lines.append(f"Velocidad {cat}: {pattern}")

    # Merma reciente
    today = date.today()
    for days_back, label in [(1, "ayer"), (7, "hace 7 días")]:
        from datetime import timedelta
        d = (today - timedelta(days=days_back)).isoformat()
        key = KEY_DAILY_STATS.format(date=d)
        stat = recall(store_id, key)
        if stat:
            lines.append(f"Merma {label}: {stat}")

    # Episodios recientes de Kuine (últimas 8h)
    episodes = get_recent_episodes(store_id, last_n_hours=8)
    if episodes:
        lines.append(f"\nÚltimos {len(episodes)} ciclos de análisis:")
        for ep in episodes[-3:]:
            ts = ep.get("timestamp", "?")[:16]
            crit = ep.get("critical_count", 0)
            var = ep.get("value_at_risk_eur", 0)
            lines.append(f"  [{ts}] {crit} críticos, {var}€ en riesgo")

    # Feedback de decisiones recientes
    feedback = get_daily_decision_feedback(store_id, days_back=1)
    if feedback.get("total_decisions", 0) > 0:
        eff = feedback.get("effectiveness_pct", 0)
        val = feedback.get("value_recovered_eur", 0)
        lines.append(f"\nEfectividad ayer: {eff}% ({val}€ recuperados)")

    if len(lines) <= 1:
        return "Sin patrones históricos disponibles aún."
    return "\n".join(lines)
