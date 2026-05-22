"""
Stock Agent — decide si reponer considerando FEFO, categoría y velocidad de venta.
Incluye cálculo de cobertura en días y cantidad óptima de pedido.
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


def _days_coverage(total_qty: int, avg_daily_sales: float) -> float | None:
    """Días de cobertura al ritmo de venta actual. None si no hay dato de ventas."""
    if avg_daily_sales > 0 and total_qty >= 0:
        return round(total_qty / avg_daily_sales, 1)
    return None


def _suggested_order_qty(
    avg_daily_sales: float,
    total_store_qty: int,
    warehouse_qty: int,
    target_coverage_days: int = 10,
) -> int | None:
    """
    Cantidad óptima de pedido para alcanzar target_coverage_days de cobertura.
    Considera lo que ya hay en tienda + almacén.
    None si no hay dato de ventas.
    """
    if avg_daily_sales <= 0:
        return None
    current_total = total_store_qty + warehouse_qty
    needed = int(avg_daily_sales * target_coverage_days) - current_total
    return max(0, needed)


def decide_restocking(product: dict, batches: list[dict], warehouse_qty: int) -> dict:
    """
    Decide si reponer basándose en FEFO, stock actual, categoría y velocidad de venta.
    Devuelve {should_restock, reason, urgency, display_qty, warehouse_qty,
              days_coverage, suggested_order_qty}
    """
    avg_daily_sales = float(product.get("avg_daily_sales", 0))

    if not batches:
        return {
            "should_restock": False,
            "reason": "Sin lotes activos — no aplica reposición.",
            "urgency": "none",
            "display_qty": 0,
            "warehouse_qty": warehouse_qty,
            "days_coverage": None,
            "suggested_order_qty": None,
        }

    if warehouse_qty <= 0:
        display_qty = batches[0].get("quantity", 0)
        return {
            "should_restock": False,
            "reason": "Sin stock en almacén disponible para reponer.",
            "urgency": "none",
            "display_qty": display_qty,
            "warehouse_qty": 0,
            "days_coverage": _days_coverage(display_qty, avg_daily_sales),
            "suggested_order_qty": None,
        }

    category = product.get("category", "general").lower()
    min_display = _CATEGORY_MIN_DISPLAY.get(category, 3)
    restock_threshold = _RESTOCK_THRESHOLD_DAYS.get(category, 3)

    # Ordenar por FEFO (el más antiguo primero)
    sorted_batches = sorted(batches, key=lambda b: b.get("expiry_date", "9999-99-99"))
    soonest = sorted_batches[0]
    total_store_qty = sum(b.get("quantity", 0) for b in batches)
    coverage = _days_coverage(total_store_qty, avg_daily_sales)

    try:
        days_left = (date.fromisoformat(soonest["expiry_date"]) - date.today()).days
    except (ValueError, KeyError):
        days_left = 999

    # Cobertura insuficiente detectada por velocidad de venta (más preciso que min_display)
    velocity_insufficient = (
        coverage is not None
        and coverage < restock_threshold
        and days_left > restock_threshold  # FEFO ok
    )

    # FEFO mejorado: bloquear solo si el stock crítico es mayoría del total.
    # Antes: 1 unidad que caduca mañana bloqueaba reponer 50 unidades que van bien.
    # Ahora: si ese lote crítico es <30% del stock, FEFO no aplica — el stock sano domina.
    soon_qty = sum(
        b.get("quantity", 0) for b in sorted_batches
        if (date.fromisoformat(b["expiry_date"]) - date.today()).days <= restock_threshold
        if b.get("expiry_date")
    )
    fefo_critical_pct = soon_qty / total_store_qty if total_store_qty > 0 else 1.0
    fefo_blocks = days_left <= restock_threshold and fefo_critical_pct >= 0.30

    if fefo_blocks:
        return {
            "should_restock": False,
            "reason": (
                f"NO reponer — {soon_qty}/{total_store_qty} uds "
                f"({int(fefo_critical_pct*100)}% del stock) caducan en ≤{restock_threshold} días. "
                f"Prioridad: vender primero (FEFO)."
            ),
            "urgency": "none",
            "display_qty": total_store_qty,
            "warehouse_qty": warehouse_qty,
            "days_coverage": coverage,
            "suggested_order_qty": None,
        }

    # Reponer si hay poco stock en tienda O la velocidad de venta agotará el stock antes del restock
    order_qty = _suggested_order_qty(avg_daily_sales, total_store_qty, warehouse_qty)

    if total_store_qty <= min_display or velocity_insufficient:
        urgency = "high" if (total_store_qty <= 1 or (coverage is not None and coverage < 1)) else "medium"
        velocity_note = (
            f" (cobertura actual: {coverage}d a ritmo de {avg_daily_sales:.1f} uds/día)"
            if coverage is not None else ""
        )
        return {
            "should_restock": True,
            "reason": (
                f"SÍ reponer — solo {total_store_qty} unidades en tienda "
                f"(mínimo recomendado: {min_display}). "
                f"Hay {warehouse_qty} unidades disponibles en almacén.{velocity_note}"
            ),
            "urgency": urgency,
            "display_qty": total_store_qty,
            "warehouse_qty": warehouse_qty,
            "days_coverage": coverage,
            "suggested_order_qty": order_qty,
        }

    # Stock suficiente
    coverage_note = f" Cobertura: {coverage}d." if coverage is not None else ""
    return {
        "should_restock": False,
        "reason": (
            f"Reposición no urgente — {total_store_qty} unidades en tienda, "
            f"{warehouse_qty} en almacén, {days_left} días restantes en lote activo.{coverage_note}"
        ),
        "urgency": "low",
        "display_qty": total_store_qty,
        "warehouse_qty": warehouse_qty,
        "days_coverage": coverage,
        "suggested_order_qty": order_qty,
    }


def decide_restocking_text(product: dict, batches: list[dict], warehouse_qty: int) -> str:
    """Versión texto para compatibilidad."""
    return decide_restocking(product, batches, warehouse_qty)["reason"]
