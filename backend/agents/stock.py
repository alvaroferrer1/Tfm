"""
Stock Agent — decide si reponer considerando FEFO, categoría y velocidad de venta.
"""
from __future__ import annotations
from datetime import date


_CATEGORY_MIN_DISPLAY: dict[str, int] = {
    "panaderia": 3,
    "carne": 2,
    "pescado": 2,
    "lacteos": 4,
    "fruta": 5,
    "verdura": 5,
}

_RESTOCK_THRESHOLD_DAYS: dict[str, int] = {
    "panaderia": 1,
    "carne": 2,
    "pescado": 2,
    "lacteos": 3,
    "fruta": 2,
    "verdura": 3,
}


def decide_restocking(product: dict, batches: list[dict], warehouse_qty: int) -> dict:
    """
    Decide si reponer basándose en FEFO, stock actual, categoría y días restantes.
    Devuelve {should_restock, reason, urgency, display_qty, warehouse_qty}
    """
    if not batches:
        return {
            "should_restock": False,
            "reason": "Sin lotes activos — no aplica reposición.",
            "urgency": "none",
            "display_qty": 0,
            "warehouse_qty": warehouse_qty,
        }

    if warehouse_qty <= 0:
        return {
            "should_restock": False,
            "reason": "Sin stock en almacén disponible para reponer.",
            "urgency": "none",
            "display_qty": batches[0].get("quantity", 0),
            "warehouse_qty": 0,
        }

    category = product.get("category", "general").lower()
    min_display = _CATEGORY_MIN_DISPLAY.get(category, 3)
    restock_threshold = _RESTOCK_THRESHOLD_DAYS.get(category, 3)

    # Ordenar por FEFO (el más antiguo primero)
    sorted_batches = sorted(batches, key=lambda b: b.get("expiry_date", "9999-99-99"))
    soonest = sorted_batches[0]
    total_store_qty = sum(b.get("quantity", 0) for b in batches)

    try:
        days_left = (date.fromisoformat(soonest["expiry_date"]) - date.today()).days
    except (ValueError, KeyError):
        days_left = 999

    # Regla FEFO: no reponer si el lote más antiguo va a caducar pronto
    # porque el nuevo stock iría detrás y el viejo podría no venderse
    if days_left <= restock_threshold:
        return {
            "should_restock": False,
            "reason": (
                f"NO reponer — el lote más antiguo caduca en {days_left} días. "
                f"Prioridad: vender {total_store_qty} unidades en tienda primero (FEFO)."
            ),
            "urgency": "none",
            "display_qty": total_store_qty,
            "warehouse_qty": warehouse_qty,
        }

    # Reponer si hay poco stock en tienda
    if total_store_qty <= min_display:
        urgency = "high" if total_store_qty <= 1 else "medium"
        return {
            "should_restock": True,
            "reason": (
                f"SÍ reponer — solo {total_store_qty} unidades en tienda "
                f"(mínimo recomendado: {min_display}). "
                f"Hay {warehouse_qty} unidades disponibles en almacén."
            ),
            "urgency": urgency,
            "display_qty": total_store_qty,
            "warehouse_qty": warehouse_qty,
        }

    # Stock suficiente, no urgente
    return {
        "should_restock": False,
        "reason": (
            f"Reposición no urgente — {total_store_qty} unidades en tienda, "
            f"{warehouse_qty} en almacén, {days_left} días restantes en lote activo."
        ),
        "urgency": "low",
        "display_qty": total_store_qty,
        "warehouse_qty": warehouse_qty,
    }


def decide_restocking_text(product: dict, batches: list[dict], warehouse_qty: int) -> str:
    """Versión texto para compatibilidad."""
    return decide_restocking(product, batches, warehouse_qty)["reason"]
