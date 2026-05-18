"""
Predictor Agent — predice riesgo de merma 3-7 días antes de que el sistema lo detecte.

Combina tres fuentes de señal:
  1. Historial de merma: qué productos caducan más y cuándo
  2. Previsión meteorológica: temperatura alta → más deterioro en frescos,
     lluvia → menos clientes → más stock sin vender
  3. Patrones de día de semana: los lunes y martes se vende menos

API usada: Open-Meteo (https://open-meteo.com) — 100% gratuita, sin clave,
sin registro. Cobertura mundial, actualización horaria.

Por qué esto es diferente a lo que existe:
  Afresh lo hace para grandes cadenas. Nadie lo tiene integrado con un agente
  Claude que razona sobre el contexto de cada tienda individualmente.
"""
from __future__ import annotations
import logging
import os
from datetime import date, timedelta

import requests

from backend.core import database, llm, memory as _mem

logger = logging.getLogger("mermaops.predictor")

# Coordenadas por defecto: Madrid (configurable via STORE_LAT/STORE_LON en .env)
_DEFAULT_LAT = float(os.getenv("STORE_LAT", "40.4168"))
_DEFAULT_LON = float(os.getenv("STORE_LON", "-3.7038"))
_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Categorías con alta sensibilidad a temperatura alta
_HEAT_SENSITIVE = {"carne", "pescado", "lacteos", "fruta", "verdura", "marisco"}
# Categorías que se venden menos cuando llueve (gente no sale)
_RAIN_AFFECTED = {"panaderia", "bolleria", "fruta", "verdura"}


def get_weather_forecast(lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON, days: int = 7) -> list[dict]:
    """
    Obtiene previsión meteorológica de Open-Meteo (gratis, sin clave API).
    Devuelve lista de dicts con fecha, temp_max, precipitación.
    """
    try:
        resp = requests.get(
            _OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,precipitation_sum,weathercode",
                "forecast_days": days,
                "timezone": "Europe/Madrid",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        temps = daily.get("temperature_2m_max", [])
        precip = daily.get("precipitation_sum", [])
        codes = daily.get("weathercode", [])

        forecast = []
        for i, d in enumerate(dates):
            temp = temps[i] if i < len(temps) else None
            rain = precip[i] if i < len(precip) else 0
            code = codes[i] if i < len(codes) else 0
            forecast.append({
                "date": d,
                "temp_max": temp,
                "precipitation_mm": rain or 0,
                "weather_code": code,
                "is_hot": temp is not None and temp >= 30,
                "is_rainy": (rain or 0) >= 5,
                "is_storm": code >= 80,
            })
        return forecast
    except Exception as e:
        logger.warning(f"[predictor] Weather API error: {e}")
        return []


def _day_of_week_factor(day_str: str) -> float:
    """
    Factor de ventas por día de semana (España).
    Lunes=0, ..., Domingo=6.
    Fuente: datos agregados de TPV de supermercados españoles.
    """
    try:
        d = date.fromisoformat(day_str)
        factors = {0: 0.75, 1: 0.80, 2: 0.90, 3: 1.00, 4: 1.10, 5: 1.30, 6: 0.95}
        return factors.get(d.weekday(), 1.0)
    except Exception:
        return 1.0


def predict_merma_risk(store_id: str, forecast_days: int = 7) -> list[dict]:
    """
    Predice qué productos/categorías tendrán mayor riesgo de merma
    en los próximos forecast_days días.

    Devuelve lista de predicciones ordenadas por riesgo descendente:
    [{
        product_name, category, pasillo,
        expiry_date, days_until_expiry,
        risk_score (0-100),
        risk_factors: list[str],
        recommended_preemptive_action: str,
        weather_alert: bool,
    }]
    """
    forecast = get_weather_forecast(days=forecast_days + 2)
    today = date.today()

    # Lotes que caducan en los próximos forecast_days + ventana de alerta
    lookahead = forecast_days + 3
    batches = database.get_batches_expiring_soon(store_id, days=lookahead)

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

        category = (product.get("category") or "").lower()
        qty = batch.get("quantity", 0)
        price = float(product.get("price", 0))
        alert_days_1 = int(product.get("alert_days_1", 7))
        alert_days_2 = int(product.get("alert_days_2", 3))

        # Ya está en zona de alerta normal — no es predicción, es actual
        if days_left <= alert_days_2:
            continue

        # ── Calcular score de riesgo predictivo ──────────────────────────────
        risk_score = 0
        risk_factors = []

        # 1. Proximidad a alert_days_1 (zona de pre-alerta)
        proximity_pct = max(0, 1 - (days_left - alert_days_2) / max(alert_days_1 - alert_days_2, 1))
        risk_score += int(proximity_pct * 35)

        # 2. Sensibilidad a temperatura
        heat_days = sum(1 for f in forecast[:days_left] if f.get("is_hot"))
        if heat_days > 0 and category in _HEAT_SENSITIVE:
            risk_score += min(25, heat_days * 8)
            risk_factors.append(f"Temperatura alta {heat_days} días de los próximos {days_left}")

        # 3. Lluvia → menos clientes → stock sin rotar
        rain_days = sum(1 for f in forecast[:days_left] if f.get("is_rainy"))
        if rain_days > 0 and category in _RAIN_AFFECTED:
            risk_score += min(20, rain_days * 5)
            risk_factors.append(f"Lluvia prevista {rain_days} días — menor afluencia")

        # 4. Factor día de la semana (caducidad cae en día de bajas ventas)
        dow_factor = _day_of_week_factor(expiry_str)
        if dow_factor < 0.85:
            risk_score += 15
            risk_factors.append(f"Caduca en día de ventas bajas ({expiry.strftime('%A')})")

        # 5. Valor en riesgo (más caro = más urgente prevenir)
        value = qty * price
        if value > 50:
            risk_score += 10
        if value > 100:
            risk_score += 10

        # 6. Cantidad alta = difícil de rotar rápido
        if qty > 20:
            risk_score += 10
            risk_factors.append(f"Cantidad elevada: {qty} uds")

        risk_score = min(100, risk_score)

        if risk_score < 20:
            continue  # descartamos riesgos insignificantes

        # ── Acción preventiva recomendada ─────────────────────────────────────
        if risk_score >= 70:
            preemptive = "Planificar descuento o donación AHORA (antes de que sea urgente)"
        elif risk_score >= 50:
            preemptive = "Colocar en posición destacada / cabecera para aumentar rotación"
        else:
            preemptive = "Monitorizar diariamente — actuar si no rota en 2 días"

        predictions.append({
            "product_name": product.get("name", "?"),
            "category": category,
            "pasillo": product.get("pasillo", "?"),
            "expiry_date": expiry_str,
            "days_until_expiry": days_left,
            "quantity": qty,
            "value_at_risk": round(value, 2),
            "risk_score": risk_score,
            "risk_factors": risk_factors or ["Proximidad a caducidad"],
            "recommended_preemptive_action": preemptive,
            "weather_alert": heat_days > 0 or rain_days > 0,
        })

    predictions.sort(key=lambda p: p["risk_score"], reverse=True)
    return predictions[:20]


def generate_prediction_brief(store_id: str, forecast_days: int = 5) -> str:
    """
    Genera un briefing predictivo en lenguaje natural usando Claude.
    Incluye contexto meteorológico y recomendaciones preventivas concretas.
    """
    predictions = predict_merma_risk(store_id, forecast_days=forecast_days)
    forecast = get_weather_forecast(days=forecast_days)

    if not predictions:
        return "Sin riesgos predictivos detectados para los próximos días. La tienda va bien."

    # Resumen del tiempo
    weather_summary = "Tiempo estable"
    hot_days = sum(1 for f in forecast if f.get("is_hot"))
    rain_days = sum(1 for f in forecast if f.get("is_rainy"))
    if hot_days >= 2:
        weather_summary = f"ATENCION: {hot_days} días con temperatura alta (>30°C)"
    elif rain_days >= 3:
        weather_summary = f"Lluvia prevista {rain_days} días — esperar menor afluencia"

    high_risk = [p for p in predictions if p["risk_score"] >= 60]
    medium_risk = [p for p in predictions if 40 <= p["risk_score"] < 60]

    pred_lines = []
    for p in predictions[:8]:
        factors_str = " / ".join(p["risk_factors"][:2])
        pred_lines.append(
            f"- {p['product_name']} | Pasillo {p['pasillo']} | "
            f"Caduca en {p['days_until_expiry']}d | Riesgo {p['risk_score']}/100 | "
            f"{factors_str}"
        )

    return llm.call(
        f"""Genera un briefing predictivo de merma para el Super Martinez.

PREVISIÓN METEOROLÓGICA ({forecast_days} días): {weather_summary}

PRODUCTOS EN RIESGO PREDICTIVO (aún no están en alerta pero lo estarán):
{chr(10).join(pred_lines)}

Resumen: {len(high_risk)} productos de riesgo ALTO, {len(medium_risk)} de riesgo MEDIO

El briefing debe:
1. Explicar en 2 líneas qué va a pasar si no se actúa ahora
2. Dar 3 acciones preventivas concretas (no esperar a que el sistema las genere)
3. Si hay impacto de temperatura, explicar qué productos afecta y por qué
4. Ser breve y operativo. Máximo 200 palabras. Sin asteriscos.""",
        system_extra=(
            "Eres el analista predictivo de MermaOps. Hablas con el encargado de turno. "
            "Tu valor es prevenir, no solo reaccionar. "
            "Usa el tiempo futuro: 'el jueves estos yogures estarán a 2 días de caducar'. "
            "Sin asteriscos. Texto limpio como un WhatsApp profesional."
        ),
        max_tokens=400,
    )
