"""
Price Agent — calcula el descuento óptimo respetando el margen mínimo.
Combina tabla determinista con ajuste por LLM para casos especiales.
"""
from __future__ import annotations
from datetime import date


_DISCOUNT_BY_DAYS: list[tuple[int, float]] = [
    (0, 0.60),
    (1, 0.50),
    (2, 0.40),
    (3, 0.30),
    (5, 0.20),
    (7, 0.10),
]

_MIN_MARGIN_OVER_COST = 1.05


def _base_discount(days_left: int) -> float:
    for threshold, pct in _DISCOUNT_BY_DAYS:
        if days_left <= threshold:
            return pct
    return 0.0


def calculate(product: dict, batch: dict, risk: dict | str) -> dict:
    """
    Calcula el descuento y nuevo precio.
    Devuelve {discount_pct, new_price, original_price, floor_applied, recommendation_text}
    """
    original_price = float(product.get("price", 0))
    cost = float(product.get("cost", 0))

    if original_price <= 0:
        return {
            "discount_pct": 0,
            "new_price": 0,
            "original_price": 0,
            "floor_applied": False,
            "recommendation_text": "Sin precio registrado — no se puede calcular descuento.",
        }

    try:
        days_left = (date.fromisoformat(batch["expiry_date"]) - date.today()).days
    except (ValueError, KeyError):
        days_left = 999

    # Extraer riesgo si viene como dict (nuevo sistema) o str (compatibilidad)
    if isinstance(risk, dict):
        risk_level = risk.get("risk_level", "BAJO")
        suggested_pct = risk.get("price_adjustment_pct", 0) / 100.0
    else:
        risk_level = "ALTO" if "CRÍTICO" in str(risk) or "ALTO" in str(risk) else "BAJO"
        suggested_pct = 0.0

    # Descuento base por días
    base_discount = _base_discount(days_left)

    # Tomar el máximo entre el descuento por días y el sugerido por el evaluador
    discount = max(base_discount, suggested_pct)

    if discount == 0:
        return {
            "discount_pct": 0,
            "new_price": original_price,
            "original_price": original_price,
            "floor_applied": False,
            "recommendation_text": (
                f"Sin descuento recomendado — {days_left} días restantes, margen suficiente."
            ),
        }

    new_price = round(original_price * (1 - discount), 2)
    floor_applied = False

    # Aplicar suelo de coste
    if cost > 0:
        min_price = round(cost * _MIN_MARGIN_OVER_COST, 2)
        if new_price < min_price:
            new_price = min_price
            floor_applied = True
            discount = round(1 - new_price / original_price, 2)

    discount_pct = int(discount * 100)

    recommendation_text = (
        f"REBAJAR {discount_pct}% — "
        f"precio actual {original_price} euros → nuevo precio {new_price} euros"
    )
    if floor_applied:
        recommendation_text += f" (suelo de coste aplicado: mínimo {new_price} euros)"

    return {
        "discount_pct": discount_pct,
        "new_price": new_price,
        "original_price": original_price,
        "floor_applied": floor_applied,
        "recommendation_text": recommendation_text,
        "days_left": days_left,
        "risk_level": risk_level,
    }


def calculate_text(product: dict, batch: dict, risk: dict | str) -> str:
    """Versión que devuelve solo el texto — para compatibilidad con código antiguo."""
    return calculate(product, batch, risk)["recommendation_text"]
