"""
Price Agent — calcula el descuento óptimo respetando el margen mínimo.
Combina tabla determinista con ajuste por velocidad de ventas.

v2: Price curve learning — running average de qué descuento liquidó el stock
por producto y categoría. Aprende con el tiempo en vez de usar curvas fijas.
"""
from __future__ import annotations
import logging
from datetime import date, datetime

logger = logging.getLogger("mermaops.price")


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

# Intraday pricing — ajusta el descuento según la hora del día (patrón Wasteless)
# Mañana: tiempo de sobra → descuento base. Noche: liquidar ya → más agresivo.
_INTRADAY_FACTOR: list[tuple[range, float]] = [
    (range(8, 11),  0.90),   # 8-11h: apertura, tiempo de sobra
    (range(11, 15), 1.00),   # 11-15h: pico de mediodía
    (range(15, 19), 1.10),   # 15-19h: tarde, urgencia creciente
    (range(19, 24), 1.25),   # 19-23h: cierre → liquidar ya
    (range(0, 8),   1.30),   # madrugada/apertura temprana → máximo
]


def _intraday_factor() -> float:
    hour = datetime.now().hour
    for time_range, factor in _INTRADAY_FACTOR:
        if hour in time_range:
            return factor
    return 1.0

# Descuentos estándar de pegatina en supermercados españoles.
# Estos son los valores que el personal de etiquetado maneja físicamente.
# Precios como 2.37€ no existen en el lineal — siempre se redondea a .X0 o .X5.
_COMMERCIAL_DISCOUNTS = [0.10, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70]


def _round_to_commercial_price(price: float, cost: float) -> tuple[float, int]:
    """
    Redondea el precio a valores comerciales reales (.x0 o .x5).
    Ajusta también el descuento resultante al múltiplo de 5% más cercano.
    Respeta siempre el suelo de coste.

    Ejemplos:
      2.37€ → 2.35€  (se redondea a .05 más cercano)
      1.18€ → 1.20€
      0.73€ → 0.75€

    Retorna (precio_redondeado, descuento_pct_efectivo)
    """
    if price <= 0:
        return price, 0

    # Redondear a múltiplo de 0.05 más cercano
    rounded = round(price / 0.05) * 0.05
    rounded = round(rounded, 2)

    # Nunca bajar del coste
    if cost > 0:
        floor = round(cost * _MIN_MARGIN_OVER_COST, 2)
        if rounded < floor:
            rounded = round(floor / 0.05) * 0.05
            rounded = round(rounded, 2)

    return rounded, 0  # caller calcula el pct


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


def _wasteless_adjustment(
    days_left: int,
    qty: int,
    avg_daily_sales: float,
    next_delivery_days: int | None,
    has_substitute: bool,
    base_discount: float,
) -> tuple[float, str]:
    """
    Ajuste de descuento al estilo Wasteless — las variables que los sistemas
    de dynamic pricing reales usan y que las tablas estáticas ignoran.

    Variables consideradas:
    - next_delivery_days: si el restock llega pronto, descontar más agresivamente
      para liquidar antes de que llegue nueva mercancía (evita stock duplicado).
    - has_substitute: si NO hay sustituto, los clientes compran igual → menos descuento.
      Si SÍ hay sustituto, necesitas incentivar más la compra del producto cercano a caducar.

    Returns (adjusted_discount, reason_string)
    """
    adjusted = base_discount
    reasons = []

    # Ajuste por próxima entrega — si llega en <3 días, descontar más
    if next_delivery_days is not None and next_delivery_days <= 3 and days_left > 0:
        delivery_boost = min(0.10, 0.05 * (3 - next_delivery_days + 1))
        adjusted = min(0.70, adjusted + delivery_boost)
        reasons.append(f"+{int(delivery_boost*100)}% (entrega en {next_delivery_days}d)")

    # Ajuste por sustituto — sin sustituto, reducir descuento (demanda inelástica)
    if not has_substitute and days_left >= 2:
        substitute_reduction = 0.05
        adjusted = max(0.05, adjusted - substitute_reduction)
        reasons.append(f"-{int(substitute_reduction*100)}% (sin sustituto)")
    elif has_substitute and days_left <= 2:
        # Con sustituto y urgente: más descuento para competir
        substitute_boost = 0.05
        adjusted = min(0.70, adjusted + substitute_boost)
        reasons.append(f"+{int(substitute_boost*100)}% (sustituto disponible)")

    return round(adjusted, 3), ", ".join(reasons)


def calculate(product: dict, batch: dict, risk: dict | str) -> dict:
    """
    Calcula el descuento y nuevo precio.
    Incorpora señales de Wasteless: next_delivery_date + has_substitute.
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

    # Intraday dynamic pricing — más agresivo conforme avanza el día (patrón Wasteless)
    # Solo aplica para productos urgentes (≤3 días) para no molestar con cambios continuos
    if days_left <= 3:
        discount = min(0.70, round(discount * _intraday_factor(), 3))

    # ── Wasteless signals — ajuste dinámico por contexto externo ─────────────
    # next_delivery_days: días hasta próxima entrega del proveedor (0 = hoy)
    # has_substitute: si hay otro producto similar disponible en tienda
    _next_delivery = product.get("next_delivery_days")  # int o None
    _has_sub = bool(product.get("has_substitute", False))
    if _next_delivery is not None or _has_sub:
        _avg_sales = float(product.get("avg_daily_sales", 0))
        _qty = int(batch.get("quantity", 0))
        discount, _wasteless_reason = _wasteless_adjustment(
            days_left, _qty, _avg_sales, _next_delivery, _has_sub, discount
        )
    else:
        _wasteless_reason = ""

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

    raw_price = round(original_price * (1 - discount), 2)
    floor_applied = False

    # Aplicar suelo de coste
    if cost > 0:
        min_price = round(cost * _MIN_MARGIN_OVER_COST, 2)
        if raw_price < min_price:
            raw_price = min_price
            floor_applied = True

    # Redondear a precio comercial real (.x0 o .x5) — evita precios como 2.37€
    # que no existen en el lineal de ningún supermercado español.
    new_price, _ = _round_to_commercial_price(raw_price, cost)
    if new_price <= 0:
        new_price = raw_price

    discount = round(1 - new_price / original_price, 3) if original_price > 0 else 0
    discount_pct = int(round(discount * 100))

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
    if _wasteless_reason:
        recommendation_text += f" [{_wasteless_reason}]"

    return {
        "discount_pct": discount_pct,
        "new_price": new_price,
        "original_price": original_price,
        "floor_applied": floor_applied,
        "velocity_boost_applied": vel_boost > 0,
        "velocity_boost_pct": int(vel_boost * 100),
        "category_multiplier": cat_multiplier,
        "wasteless_adjustment": _wasteless_reason,
        "recommendation_text": recommendation_text,
        "days_left": days_left,
        "risk_level": risk_level,
    }


def calculate_text(product: dict, batch: dict, risk: dict | str) -> str:
    """Versión que devuelve solo el texto — para compatibilidad con código antiguo."""
    return calculate(product, batch, risk)["recommendation_text"]


# ── Price curve learning ──────────────────────────────────────────────────────
# Aprende qué descuento realmente liquidó el stock para cada producto/categoría.
# Usa una running average simple: discount_learned = 0.7*prev + 0.3*actual
# Se guarda en memoria episódica y se recupera al calcular el próximo descuento.

def record_successful_clearance(
    store_id: str,
    product_id: str,
    category: str,
    days_left: int,
    discount_pct: int,
    qty_sold: int,
    qty_total: int,
) -> None:
    """
    Registra que un descuento liquidó el stock.
    Llama esto cuando una acción rebajar se completa (complete_action).
    Solo aprende de clearances exitosos (vendió ≥70% del stock).
    """
    if qty_total <= 0 or qty_sold / qty_total < 0.70:
        return  # no fue suficientemente exitoso para aprender

    try:
        from backend.core import memory as _mem
        # Clave: historial por producto
        _prod_key = f"price_learning_product_{product_id}_days_{min(days_left, 7)}"
        _prev_raw = _mem.recall(store_id, _prod_key)
        if _prev_raw:
            try:
                _prev = float(_prev_raw)
                _learned = round(0.7 * _prev + 0.3 * discount_pct, 1)
            except Exception:
                _learned = float(discount_pct)
        else:
            _learned = float(discount_pct)
        _mem.remember(store_id, _prod_key, str(_learned))

        # Clave: historial por categoría (más general, para productos nuevos)
        _cat_key = f"price_learning_category_{category}_days_{min(days_left, 7)}"
        _cat_raw = _mem.recall(store_id, _cat_key)
        if _cat_raw:
            try:
                _cat_prev = float(_cat_raw)
                _cat_learned = round(0.8 * _cat_prev + 0.2 * discount_pct, 1)
            except Exception:
                _cat_learned = float(discount_pct)
        else:
            _cat_learned = float(discount_pct)
        _mem.remember(store_id, _cat_key, str(_cat_learned))
        logger.debug(f"[price_learning] {product_id} d={days_left}: {discount_pct}% → learned {_learned}%")
    except Exception as e:
        logger.debug(f"[price_learning] fallo silencioso: {e}")


def get_learned_discount(store_id: str, product_id: str, category: str, days_left: int) -> float | None:
    """
    Recupera el descuento aprendido para un producto/categoría.
    Returns None si no hay historial suficiente.
    """
    try:
        from backend.core import memory as _mem
        _prod_key = f"price_learning_product_{product_id}_days_{min(days_left, 7)}"
        _prod_raw = _mem.recall(store_id, _prod_key)
        if _prod_raw:
            return float(_prod_raw) / 100.0  # devuelve como ratio (0-1)

        _cat_key = f"price_learning_category_{category}_days_{min(days_left, 7)}"
        _cat_raw = _mem.recall(store_id, _cat_key)
        if _cat_raw:
            return float(_cat_raw) / 100.0
    except Exception:
        pass
    return None


def calculate_with_learning(
    product: dict,
    batch: dict,
    risk: dict | str,
    store_id: str,
) -> dict:
    """
    Versión de calculate() que incorpora price curve learning.
    Si hay historial de qué descuento funcionó antes para este producto,
    lo usa como punto de partida en vez de la tabla estática.
    """
    result = calculate(product, batch, risk)

    product_id = product.get("id", "")
    category = product.get("category", "").lower()
    try:
        days_left = (date.fromisoformat(batch["expiry_date"]) - date.today()).days
    except Exception:
        days_left = 999

    if product_id and store_id:
        learned = get_learned_discount(store_id, product_id, category, days_left)
        if learned is not None:
            original_price = float(product.get("price", 0))
            cost = float(product.get("cost", 0))
            min_price = round(cost * _MIN_MARGIN_OVER_COST, 2) if cost > 0 else 0
            learned_price = round(original_price * (1 - learned), 2)
            if learned_price >= min_price and learned_price > 0:
                current_discount = result.get("discount_pct", 0) / 100.0
                # Promediar entre lo estático y lo aprendido (dar más peso al aprendido)
                blended = round(0.4 * current_discount + 0.6 * learned, 3)
                new_price = max(min_price, round(original_price * (1 - blended), 2))
                result["new_price"] = new_price
                result["discount_pct"] = int(blended * 100)
                result["learning_applied"] = True
                result["learned_discount_pct"] = int(learned * 100)
                result["recommendation_text"] = (
                    f"REBAJAR {result['discount_pct']}% (aprendido: {int(learned*100)}% liquidó antes) — "
                    f"precio {original_price}€ → {new_price}€"
                )
                logger.debug(f"[price_learning] aplicado para {product.get('name')}: {int(blended*100)}%")

    return result
