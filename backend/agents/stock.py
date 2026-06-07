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


def decide_restocking(
    product: dict,
    batches: list[dict],
    warehouse_qty: int,
    prediction_data: dict | None = None,
) -> dict:
    """
    Decide si reponer basándose en FEFO, stock actual, categoría y velocidad de venta.
    prediction_data: dict del Predictor con forecast de demanda (opcional).
                     Ajusta target_coverage_days según demanda prevista.
    Devuelve {should_restock, reason, urgency, display_qty, warehouse_qty,
              days_coverage, suggested_order_qty}
    """
    avg_daily_sales = float(product.get("avg_daily_sales", 0))

    # Ajustar cobertura objetivo según predicciones de demanda
    _target_coverage = 10  # default
    _prediction_note = ""
    if prediction_data:
        predicted_risk = prediction_data.get("risk_level", "")
        predicted_demand_factor = prediction_data.get("demand_factor", 1.0)
        if predicted_risk in ("high", "CRÍTICO") or predicted_demand_factor > 1.3:
            _target_coverage = 14  # mayor demanda prevista → más stock
            _prediction_note = " (previsión de alta demanda: objetivo +40%)"
        elif predicted_risk in ("low", "BAJO") or predicted_demand_factor < 0.7:
            _target_coverage = 7   # menor demanda → menos stock
            _prediction_note = " (previsión de baja demanda: objetivo reducido)"

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

    # Sanear cantidades negativas (devoluciones mal registradas, errores de ERP).
    # Una cantidad negativa es un error de datos — tratar como 0 para no tomar
    # decisiones de restock absurdas basadas en stock fantasma.
    batches = [
        {**b, "quantity": max(0, int(b.get("quantity", 0) or 0))}
        for b in batches
    ]

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
    except (ValueError, KeyError, TypeError):
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
    def _days_until(exp_str: str) -> int:
        try:
            return (date.fromisoformat(exp_str) - date.today()).days
        except (ValueError, TypeError):
            return 999

    soon_qty = sum(
        b.get("quantity", 0) for b in sorted_batches
        if b.get("expiry_date")
        if _days_until(b["expiry_date"]) <= restock_threshold
    )
    fefo_critical_pct = soon_qty / total_store_qty if total_store_qty > 0 else 1.0
    fefo_blocks = days_left <= restock_threshold and fefo_critical_pct >= 0.30

    if fefo_blocks:
        return {
            "should_restock": False,
            "reason": (
                f"No saques más del almacén hasta liquidar lo del lineal — "
                f"tienes {soon_qty} de {total_store_qty} uds que caducan en menos de {restock_threshold} días. "
                f"Primero vende lo más antiguo (FEFO), luego repones."
            ),
            "urgency": "none",
            "display_qty": total_store_qty,
            "warehouse_qty": warehouse_qty,
            "days_coverage": coverage,
            "suggested_order_qty": None,
        }

    # Reponer si hay poco stock en tienda O la velocidad de venta agotará el stock antes del restock
    order_qty = _suggested_order_qty(avg_daily_sales, total_store_qty, warehouse_qty, _target_coverage)

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
                f"Hay {warehouse_qty} unidades disponibles en almacén.{velocity_note}{_prediction_note}"
            ),
            "urgency": urgency,
            "display_qty": total_store_qty,
            "warehouse_qty": warehouse_qty,
            "days_coverage": coverage,
            "suggested_order_qty": order_qty,
            "target_coverage_days": _target_coverage,
        }

    # Stock suficiente
    coverage_note = f" Cobertura: {coverage}d." if coverage is not None else ""
    return {
        "should_restock": False,
        "reason": (
            f"Reposición no urgente — {total_store_qty} unidades en tienda, "
            f"{warehouse_qty} en almacén, {days_left} días restantes en lote activo.{coverage_note}{_prediction_note}"
        ),
        "urgency": "low",
        "display_qty": total_store_qty,
        "warehouse_qty": warehouse_qty,
        "days_coverage": coverage,
        "suggested_order_qty": order_qty,
        "target_coverage_days": _target_coverage,
    }


def decide_restocking_text(product: dict, batches: list[dict], warehouse_qty: int) -> str:
    """Versión texto para compatibilidad."""
    return decide_restocking(product, batches, warehouse_qty)["reason"]


def check_fefo_violation(warehouse_batches: list[dict], store_batches: list[dict]) -> dict:
    """
    Detecta si reponer causaría violación FEFO (stock nuevo delante del viejo).
    Reglamento CE 853/2004 exige FEFO en perecederos.
    """
    if not warehouse_batches or not store_batches:
        return {"violation": False}
    try:
        oldest_store = min(b.get("expiry_date", "9999-12-31") for b in store_batches)
        newest_wh = max(b.get("expiry_date", "0000-01-01") for b in warehouse_batches)
        if newest_wh > oldest_store:
            return {
                "violation": True,
                "warning": (
                    f"FEFO violation: almacén caduca {newest_wh} > tienda {oldest_store}. "
                    "Liquidar stock tienda antes de reponer."
                ),
            }
    except Exception:
        pass
    return {"violation": False}


def decide_preemptive_restock(product: dict, prediction: dict, current_qty: int) -> dict:
    """
    Si el predictor ve riesgo alto de agotamiento en ≤3 días → reponer HOY
    aunque el stock parezca suficiente. Patrón Afresh: +2 días de shelf life.
    """
    risk_score = prediction.get("risk_score", 0)
    shortage_date = prediction.get("predicted_shortage_date")
    if risk_score >= 70 and shortage_date:
        try:
            from datetime import date
            days = (date.fromisoformat(shortage_date) - date.today()).days
            if days <= 3:
                return {
                    "restock": True,
                    "reason": "preemptive",
                    "urgency": "ALTA",
                    "message": (
                        f"Predictor: agotamiento en {days}d. "
                        "Reponer ahora para evitar rotura de stock."
                    ),
                    "suggested_qty": product.get("min_order_qty", 10),
                }
        except Exception:
            pass
    return {"restock": False, "reason": "stock_sufficient"}
