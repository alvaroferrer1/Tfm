"""
Price Agent — calcula el descuento óptimo respetando el margen mínimo.
Combina tabla determinista con ajuste por velocidad de ventas.
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

# Multiplicador de descuento por categoría.
# Categorías muy perecederas (carne, pescado) → descuentos más agresivos.
# Categorías de larga duración (conservas, bebidas) → descuentos más suaves.
# El multiplicador se aplica ANTES del suelo de coste.
_CATEGORY_DISCOUNT_MULTIPLIER: dict[str, float] = {
    "carne": 1.20,
    "pescado": 1.20,
    "marisco": 1.20,
    "lacteos": 1.10,
    "fruta": 1.08,
    "verdura": 1.08,
    "panaderia": 1.15,   # el pan del día: bajada agresiva en el mismo día
    "bolleria": 1.12,
    "congelados": 0.90,  # fecha real de deterioro es mucho más larga
    "conservas": 0.80,
    "bebidas": 0.80,
    "legumbres": 0.75,
}

_MIN_MARGIN_OVER_COST = 1.05


def _base_discount(days_left: int) -> float:
    for threshold, pct in _DISCOUNT_BY_DAYS:
        if days_left <= threshold:
            return pct
    return 0.0


def _velocity_boost(product: dict, batch: dict, days_left: int) -> float:
    """
    Boost adicional al descuento cuando la velocidad de venta es insuficiente
    para liquidar el stock antes de la caducidad.

    Ejemplo: 20 uds, venta media 2/día, caduca en 3 días → necesitas vender
    6 uds pero solo venderás 6 → justo. Si vendes 1/día → solo 3 uds,
    quedarán 17 sin vender → necesitas un descuento mayor para acelerar la rotación.

    Solo se activa cuando el producto tiene avg_daily_sales registrado.
    Boost máximo: 15 puntos porcentuales adicionales.
    """
    avg_daily_sales = float(product.get("avg_daily_sales", 0))
    if avg_daily_sales <= 0 or days_left <= 0:
        return 0.0

    qty = int(batch.get("quantity", 0))
    if qty <= 0:
        return 0.0

    days_to_sell = qty / avg_daily_sales
    if days_to_sell <= days_left:
        return 0.0  # la velocidad actual es suficiente — sin boost

    # Ratio de exceso: cuántas veces más tiempo del disponible se necesita
    excess_ratio = (days_to_sell / days_left) - 1.0
    # Boost logarítmico: crece rápido al principio, se aplana
    boost = min(0.15, excess_ratio * 0.08)
    return round(boost, 3)


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

    # Multiplicador por categoría — perecederos frescos se descuentan más agresivamente
    category = product.get("category", "").lower()
    cat_multiplier = _CATEGORY_DISCOUNT_MULTIPLIER.get(category, 1.0)
    base_discount = min(0.70, round(base_discount * cat_multiplier, 3))

    # Tomar el máximo entre el descuento por días y el sugerido por el evaluador
    discount = max(base_discount, suggested_pct)

    # Boost por velocidad de venta insuficiente (solo si avg_daily_sales está definido)
    vel_boost = _velocity_boost(product, batch, days_left)
    discount = min(0.70, discount + vel_boost)

    if discount == 0:
        return {
            "discount_pct": 0,
            "new_price": original_price,
            "original_price": original_price,
            "floor_applied": False,
            "velocity_boost_applied": False,
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
    if vel_boost > 0:
        recommendation_text += f" [+{int(vel_boost * 100)}% por velocidad de venta insuficiente]"
    if cat_multiplier != 1.0:
        direction = "mayor urgencia perecedero" if cat_multiplier > 1 else "menor urgencia"
        recommendation_text += f" [{direction}: x{cat_multiplier} por categoría {category}]"

    return {
        "discount_pct": discount_pct,
        "new_price": new_price,
        "original_price": original_price,
        "floor_applied": floor_applied,
        "velocity_boost_applied": vel_boost > 0,
        "velocity_boost_pct": int(vel_boost * 100),
        "category_multiplier": cat_multiplier,
        "recommendation_text": recommendation_text,
        "days_left": days_left,
        "risk_level": risk_level,
    }


def calculate_text(product: dict, batch: dict, risk: dict | str) -> str:
    """Versión que devuelve solo el texto — para compatibilidad con código antiguo."""
    return calculate(product, batch, risk)["recommendation_text"]
