"""
Episodic memory system — el Supervisor aprende patrones a lo largo del tiempo.
Los patrones se persisten en agent_memory (Supabase) y se recuperan en cada ciclo.
"""
from __future__ import annotations
from datetime import date
from backend.core import database


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
        print(f"[memory] Error guardando patrón {key}: {e}")


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
