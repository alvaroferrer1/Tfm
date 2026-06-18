"""
Predictor Agent — predice riesgo de merma 3-7 días antes de que el sistema lo detecte.

Combina cuatro fuentes de señal:
  1. Historial de merma: qué productos caducan más y cuándo
  2. Previsión meteorológica: temperatura alta → más deterioro en frescos,
     lluvia → menos clientes → más stock sin vender
  3. Patrones de día de semana: los lunes y martes se vende menos
  4. Calendario de eventos españoles + estacionalidad mensual por categoría

API usada: Open-Meteo (https://open-meteo.com) — 100% gratuita, sin clave.
"""
from __future__ import annotations
import logging
import os
from datetime import date, timedelta

import requests

from backend.core import database, llm, memory as _mem

logger = logging.getLogger("mermaops.predictor")

_DEFAULT_LAT = float(os.getenv("STORE_LAT", "40.4168"))
_DEFAULT_LON = float(os.getenv("STORE_LON", "-3.7038"))
_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

_HEAT_SENSITIVE = {"carne", "pescado", "lacteos", "fruta", "verdura", "marisco"}
_RAIN_AFFECTED  = {"panaderia", "bolleria", "fruta", "verdura"}

_weather_cache: dict[tuple, tuple[float, list[dict]]] = {}
_WEATHER_CACHE_TTL = 3600.0

# ── Estacionalidad mensual por categoría (mes 1-12 → float multiplicador) ────
# Representada como lista de 12 valores (ene-dic) por categoría.
_SEASON_ROWS: dict[str, list[float]] = {
    "carne":    [1.0,  0.95, 1.0,  1.05, 1.1,  1.25, 1.30, 1.25, 1.1,  1.0,  1.05, 1.2],
    "pescado":  [0.95, 0.95, 1.15, 1.15, 1.0,  1.2,  1.25, 1.2,  1.05, 1.0,  0.95, 1.1],
    "lacteos":  [1.05, 1.05, 1.0,  1.0,  1.0,  0.95, 0.9,  0.9,  1.0,  1.0,  1.05, 1.1],
    "fruta":    [0.9,  0.9,  0.95, 1.0,  1.1,  1.2,  1.25, 1.2,  1.1,  1.0,  0.9,  0.95],
    "verdura":  [0.95, 0.95, 1.0,  1.05, 1.1,  1.15, 1.2,  1.15, 1.1,  1.0,  0.95, 1.0],
    "panaderia":[1.15, 1.05, 1.0,  1.05, 1.0,  0.95, 0.9,  0.9,  1.1,  1.05, 1.1,  1.2],
    "bolleria": [1.1,  1.05, 1.0,  1.05, 1.0,  0.9,  0.85, 0.85, 1.1,  1.0,  1.05, 1.15],
    "marisco":  [0.9,  0.85, 0.9,  1.0,  1.05, 1.15, 1.2,  1.15, 1.0,  0.95, 1.1,  1.3],
}
_FALLBACK_LOSS_RATE: dict[str, float] = {
    "carne": 0.08, "pescado": 0.10, "lacteos": 0.04, "fruta": 0.12,
    "verdura": 0.11, "panaderia": 0.09, "bolleria": 0.07, "marisco": 0.13,
}


def _get_seasonal_modifier(month: int, category: str) -> float:
    row = _SEASON_ROWS.get(category.lower())
    return row[month - 1] if row else 1.0


def _get_upcoming_events(days: int = 14) -> list[str]:
    """Devuelve nombres de eventos del calendario español que caen en los próximos `days` días."""
    today = date.today()
    end   = today + timedelta(days=days)
    events: list[str] = []
    year = today.year

    def _in(d: date) -> bool:
        return today <= d <= end

    def _overlap(s: date, e: date) -> bool:
        return s <= end and e >= today

    # Navidad, Reyes
    for y in (year, year + 1):
        if _overlap(date(y, 12, 24), date(y, 12, 26)): events.append("Navidad"); break
    for y in (year, year + 1):
        if _overlap(date(y, 1, 5), date(y, 1, 6)):    events.append("Reyes Magos"); break

    # San Valentín
    for y in (year, year + 1):
        if _in(date(y, 2, 14)): events.append("San Valentín"); break

    # Semana Santa (fechas fijas 2026-2028, resto aproximado)
    _SS = {2026: (date(2026, 3, 29), date(2026, 4, 5)),
           2027: (date(2027, 3, 28), date(2027, 4, 4)),
           2028: (date(2028, 4, 13), date(2028, 4, 20))}
    for y in (year, year + 1):
        ss, se = _SS.get(y, (date(y, 4, 6), date(y, 4, 13)))
        if _overlap(ss, se): events.append("Semana Santa"); break

    # Día de la Madre — primer domingo de mayo
    for y in (year, year + 1):
        d = date(y, 5, 1)
        while d.weekday() != 6: d += timedelta(days=1)
        if _in(d): events.append("Día de la Madre"); break

    # Verano, Vuelta al cole, Halloween
    for y in (year, year + 1):
        if _overlap(date(y, 6, 21), date(y, 9, 22)): events.append("Temporada de Verano"); break
    for y in (year, year + 1):
        if _overlap(date(y, 9, 1), date(y, 9, 15)):  events.append("Vuelta al Cole"); break
    for y in (year, year + 1):
        if _in(date(y, 10, 31)):                      events.append("Halloween"); break

    # Black Friday — último viernes de noviembre
    for y in (year, year + 1):
        d = date(y, 11, 30)
        while d.weekday() != 4: d -= timedelta(days=1)
        if _in(d): events.append("Black Friday"); break

    return list(dict.fromkeys(events))


def get_historical_loss_rate(store_id: str) -> dict[str, float]:
    """Tasa media diaria de merma por categoría (últimos 30 días). Fallback heurístico."""
    try:
        db = database.get_db()
        since = (date.today() - timedelta(days=30)).isoformat()
        result = (
            db.table("merma_log")
            .select("quantity, products(category)")
            .eq("store_id", store_id)
            .gte("created_at", since)
            .execute()
        )
        rows = result.data or []
        totals: dict[str, float] = {}
        for row in rows:
            cat = ((row.get("products") or {}).get("category") or "otro").lower()
            totals[cat] = totals.get(cat, 0.0) + float(row.get("quantity", 0))
        return {cat: round(v / 30.0, 4) for cat, v in totals.items()} or _FALLBACK_LOSS_RATE.copy()
    except Exception as e:
        logger.warning(f"[predictor] Error historial merma: {e}")
        return _FALLBACK_LOSS_RATE.copy()


def get_weather_forecast(lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON, days: int = 7) -> list[dict]:
    """Previsión Open-Meteo con caché 1h. Incluye temp aparente, humedad, UV, viento, prob. lluvia."""
    import time as _time
    cache_key = (lat, lon, days, str(date.today()))
    cached = _weather_cache.get(cache_key)
    if cached:
        ts, data = cached
        if (_time.monotonic() - ts) < _WEATHER_CACHE_TTL:
            return data

    try:
        resp = requests.get(
            _OPEN_METEO_URL,
            params={
                "latitude": lat, "longitude": lon,
                "daily": (
                    "temperature_2m_max,precipitation_sum,weathercode,"
                    "apparent_temperature_max,relative_humidity_2m_max,"
                    "uv_index_max,windspeed_10m_max,precipitation_probability_max"
                ),
                "forecast_days": days,
                "timezone": "Europe/Madrid",
            },
            timeout=8,
        )
        resp.raise_for_status()
        d = resp.json().get("daily", {})
        dates  = d.get("time", [])
        temps  = d.get("temperature_2m_max", [])
        precip = d.get("precipitation_sum", [])
        codes  = d.get("weathercode", [])
        apptemp = d.get("apparent_temperature_max", [])
        hum    = d.get("relative_humidity_2m_max", [])
        uv     = d.get("uv_index_max", [])
        wind   = d.get("windspeed_10m_max", [])
        pp     = d.get("precipitation_probability_max", [])

        def _g(lst, i): return lst[i] if i < len(lst) else None

        forecast = []
        for i, dt in enumerate(dates):
            t   = _g(temps, i)
            r   = _g(precip, i) or 0
            forecast.append({
                "date": dt,
                "temp_max":                    t,
                "apparent_temperature_max":    _g(apptemp, i),
                "relative_humidity_2m_max":    _g(hum, i),
                "uv_index_max":                _g(uv, i),
                "windspeed_10m_max":           _g(wind, i),
                "precipitation_probability_max": _g(pp, i),
                "precipitation_mm":            r,
                "weather_code":                _g(codes, i) or 0,
                "is_hot":   t is not None and t >= 30,
                "is_rainy": r >= 5,
                "is_storm": (_g(codes, i) or 0) >= 80,
            })
        _weather_cache[cache_key] = (_time.monotonic(), forecast)
        logger.info(f"[predictor] Weather cacheado — {len(forecast)} días")
        return forecast
    except Exception as e:
        logger.warning(f"[predictor] Weather API error: {e}")
        return []


def _day_of_week_factor(day_str: str) -> float:
    """Factor de ventas por día de semana (España, Lunes=0…Domingo=6)."""
    try:
        factors = {0: 0.75, 1: 0.80, 2: 0.90, 3: 1.00, 4: 1.10, 5: 1.30, 6: 0.95}
        return factors.get(date.fromisoformat(day_str).weekday(), 1.0)
    except Exception:
        return 1.0


def _weather_narrative(category: str, heat_days: int, rain_days: int, forecast: list[dict]) -> str:
    """Una línea describiendo el impacto meteorológico sobre la categoría."""
    if not forecast:
        return "Sin datos meteorológicos."
    f0   = forecast[0]
    t    = f0.get("temp_max")
    h    = f0.get("relative_humidity_2m_max")
    ts   = f"{t:.0f}°C" if t is not None else "temp. desconocida"
    hs   = f", humedad {h:.0f}%" if h is not None else ""
    if heat_days >= 2 and category in _HEAT_SENSITIVE:
        return f"Calor {heat_days} días (hasta {ts}{hs}) — acelera deterioro en {category}."
    if rain_days >= 2 and category in _RAIN_AFFECTED:
        return f"Lluvia {rain_days} días — menos afluencia, {category} rota peor."
    if t is not None and t >= 25 and category in _HEAT_SENSITIVE:
        return f"Temperatura elevada ({ts}{hs}) — vigilar {category}."
    return f"Tiempo estable ({ts}{hs}) — impacto bajo."


def predict_merma_risk(store_id: str, forecast_days: int = 7) -> list[dict]:
    """Predice riesgo de merma por producto para los próximos forecast_days días.
    Devuelve lista (máx. 20) ordenada por risk_score descendente."""
    forecast        = get_weather_forecast(days=forecast_days + 2)
    today           = date.today()
    upcoming_events = _get_upcoming_events(days=forecast_days + 7)
    historical_loss = get_historical_loss_rate(store_id)
    batches         = database.get_batches_expiring_soon(store_id, days=forecast_days + 3)

    predictions: list[dict] = []

    for batch in batches:
        product = batch.get("products") or {}
        if not product:
            continue
        expiry_str = batch.get("expiry_date", "")
        try:
            expiry = date.fromisoformat(expiry_str)
        except (ValueError, TypeError):
            continue
        days_left = (expiry - today).days
        if days_left < 0:
            continue

        category     = (product.get("category") or "").lower()
        qty          = batch.get("quantity", 0)
        price        = float(product.get("price", 0))
        alert_days_1 = int(product.get("alert_days_1", 7))
        alert_days_2 = int(product.get("alert_days_2", 3))

        if days_left <= alert_days_2:
            continue  # ya en alerta normal, no predicción

        risk_score   = 0
        risk_factors = []
        signal_count = 0

        # 1. Proximidad a zona de pre-alerta
        prox = max(0, 1 - (days_left - alert_days_2) / max(alert_days_1 - alert_days_2, 1))
        risk_score += int(prox * 35)
        if prox > 0.5: signal_count += 1

        # 2. Calor
        heat_days = sum(1 for f in forecast[:days_left] if f.get("is_hot"))
        is_hot    = heat_days > 0 and category in _HEAT_SENSITIVE
        if is_hot:
            risk_score += min(25, heat_days * 8)
            risk_factors.append(f"Temperatura alta {heat_days} días de los próximos {days_left}")
            signal_count += 1

        # 3. Lluvia
        rain_days  = sum(1 for f in forecast[:days_left] if f.get("is_rainy"))
        is_rainy   = rain_days > 0 and category in _RAIN_AFFECTED
        if is_rainy:
            risk_score += min(20, rain_days * 5)
            risk_factors.append(f"Lluvia prevista {rain_days} días — menor afluencia")
            signal_count += 1

        # 4. Día de semana
        dow        = _day_of_week_factor(expiry_str)
        low_day    = dow < 0.85
        if low_day:
            risk_score += 15
            risk_factors.append(f"Caduca en día de ventas bajas ({expiry.strftime('%A')})")
            signal_count += 1

        # 4b. Efectos compuestos
        if is_hot and low_day:
            cb = min(15, heat_days * 3)
            risk_score += cb
            risk_factors.append(f"COMPUESTO: calor + día ventas bajas +{cb}pts")
        if is_rainy and not low_day and dow >= 1.1:
            risk_score += 8
            risk_factors.append("Lluvia en fin de semana — clientes compran menos frescos")

        # 5. Valor en riesgo
        value = qty * price
        if value > 50:  risk_score += 10; signal_count += 1
        if value > 100: risk_score += 10

        # 6. Cantidad alta
        if qty > 20:
            risk_score += 10
            risk_factors.append(f"Cantidad elevada: {qty} uds")
            signal_count += 1

        # 7. Estacionalidad baja
        sea_mod = _get_seasonal_modifier(today.month, category)
        if sea_mod < 0.95:
            risk_score += 8
            risk_factors.append(f"Temporada baja para {category} (índice {sea_mod:.2f})")
            signal_count += 1

        # 8. Eventos próximos (alta demanda → reducen riesgo)
        _HIGH_DEMAND = {"Navidad": 0.2, "Reyes Magos": 0.2, "Black Friday": 0.2,
                        "Semana Santa": 0.1, "Día de la Madre": 0.1, "Temporada de Verano": 0.1}
        ev_boost = sum(_HIGH_DEMAND[e] for e in upcoming_events if e in _HIGH_DEMAND)
        if ev_boost > 0:
            red = min(15, int(ev_boost * 20))
            risk_score = max(0, risk_score - red)
            ev_names = [e for e in upcoming_events if e in _HIGH_DEMAND]
            risk_factors.append(f"Alta demanda próxima: {', '.join(ev_names)} (-{red}pts)")

        risk_score = min(100, risk_score)
        if risk_score < 20:
            continue

        confidence_level = "alta" if signal_count >= 3 else ("media" if signal_count == 2 else "baja")

        if risk_score >= 70:
            preemptive = "Planificar descuento o donación AHORA (antes de que sea urgente)"
        elif risk_score >= 50:
            preemptive = "Colocar en posición destacada / cabecera para aumentar rotación"
        else:
            preemptive = "Monitorizar diariamente — actuar si no rota en 2 días"

        demand_index = round(min(2.0, max(0.5, dow * sea_mod * (1.0 + ev_boost * 0.5))), 3)

        predictions.append({
            "product_name":                product.get("name", "?"),
            "category":                    category,
            "pasillo":                     product.get("pasillo", "?"),
            "expiry_date":                 expiry_str,
            "days_until_expiry":           days_left,
            "quantity":                    qty,
            "value_at_risk":               round(value, 2),
            "risk_score":                  risk_score,
            "risk_factors":                risk_factors or ["Proximidad a caducidad"],
            "recommended_preemptive_action": preemptive,
            "weather_alert":               heat_days > 0 or rain_days > 0,
            "confidence_level":            confidence_level,
            "signal_count":                signal_count,
            # Nuevos campos
            "weather_narrative":           _weather_narrative(category, heat_days, rain_days, forecast),
            "seasonal_modifier":           sea_mod,
            "upcoming_events":             upcoming_events,
            "historical_loss_rate":        historical_loss.get(category, _FALLBACK_LOSS_RATE.get(category, 0.05)),
            "demand_index":                demand_index,
        })

    predictions.sort(key=lambda p: p["risk_score"], reverse=True)
    return predictions[:20]

def generate_prediction_brief(store_id: str, forecast_days: int = 5) -> str:
    """Briefing predictivo en lenguaje natural con fechas, datos meteorológicos y eventos."""
    predictions     = predict_merma_risk(store_id, forecast_days=forecast_days)
    forecast        = get_weather_forecast(days=forecast_days)
    upcoming_events = _get_upcoming_events(days=forecast_days + 7)

    if not predictions:
        return "Sin riesgos predictivos detectados para los próximos días. La tienda va bien."

    today      = date.today()
    date_range = f"{today.isoformat()} al {(today + timedelta(days=forecast_days)).isoformat()}"

    hot_days  = sum(1 for f in forecast if f.get("is_hot"))
    rain_days = sum(1 for f in forecast if f.get("is_rainy"))
    max_temp  = max((f.get("temp_max") or 0 for f in forecast), default=0)
    max_hum   = max((f.get("relative_humidity_2m_max") or 0 for f in forecast), default=0)
    max_uv    = max((f.get("uv_index_max") or 0 for f in forecast), default=0)
    max_wind  = max((f.get("windspeed_10m_max") or 0 for f in forecast), default=0)
    max_pp    = max((f.get("precipitation_probability_max") or 0 for f in forecast), default=0)

    weather_summary = (
        f"Tmax: {max_temp:.0f}°C | Humedad máx: {max_hum:.0f}% | UV máx: {max_uv:.1f} | "
        f"Viento máx: {max_wind:.0f} km/h | Prob. lluvia máx: {max_pp:.0f}% | "
        f"Días calor (≥30°C): {hot_days} | Días lluvia (≥5mm): {rain_days}"
    )

    if hot_days >= 2:
        weather_impact = (
            f"Vienen {hot_days} días de calor (hasta {max_temp:.0f}°C, humedad {max_hum:.0f}%). "
            "Los frescos y lácteos se deterioran más rápido. Ojo con el stock hoy mismo."
        )
    elif rain_days >= 3:
        weather_impact = (
            f"Lluvia {rain_days} días (prob. hasta {max_pp:.0f}%). "
            "Menos clientes — pan y fruta madura se quedarán sin vender."
        )
    else:
        weather_impact = f"Tiempo estable para el período {date_range}. Rotación normal esperada."

    events_str = ", ".join(upcoming_events) if upcoming_events else "Ninguno relevante"

    high_risk   = [p for p in predictions if p["risk_score"] >= 60]
    medium_risk = [p for p in predictions if 40 <= p["risk_score"] < 60]

    pred_lines = []
    for p in predictions[:8]:
        factors = " / ".join(p["risk_factors"][:2])
        pred_lines.append(
            f"• {p['product_name']} | {p['category']} | Pasillo {p['pasillo']}\n"
            f"  Caduca {p['expiry_date']} ({p['days_until_expiry']}d) | "
            f"Riesgo {p['risk_score']}/100 | Demanda {p['demand_index']} | "
            f"Merma hist. {p['historical_loss_rate']:.3f}/día\n"
            f"  Factores: {factors}\n"
            f"  Tiempo: {p['weather_narrative']}"
        )

    return llm.call(
        f"""Genera un briefing predictivo de merma para el Super Martinez.

PERÍODO: {date_range}
METEOROLOGÍA: {weather_summary}
IMPACTO ESPERADO: {weather_impact}
EVENTOS PRÓXIMOS: {events_str}

PRODUCTOS EN RIESGO PREDICTIVO:
{chr(10).join(pred_lines)}

RESUMEN: {len(high_risk)} riesgo ALTO, {len(medium_risk)} riesgo MEDIO.

El briefing debe:
1. Mencionar fechas concretas y valores de temperatura/humedad al hablar del tiempo
2. Si hay eventos del calendario, explicar cómo afectan a la demanda
3. Dar 3 acciones preventivas con producto y pasillo específico (viñetas •)
4. Explicar qué categorías afecta el calor/lluvia y por qué
5. Máximo 220 palabras. Sin asteriscos.""",
        system_extra=(
            "Eres el analista predictivo de MermaOps. Hablas con el encargado de turno. "
            "Tu valor es prevenir, no reaccionar. Usa fechas concretas y datos reales. "
            "Sin asteriscos. Texto limpio como un WhatsApp profesional."
        ),
        max_tokens=450,
    )
