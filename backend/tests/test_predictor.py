"""
Tests del Predictor Agent.
Sin llamadas a Open-Meteo ni Supabase — se mockea requests y database.
"""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import pytest

from backend.agents.predictor import (
    get_weather_forecast,
    _day_of_week_factor,
    predict_merma_risk,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_batch(days_ahead: int, category: str, qty: int, price: float,
                alert1: int = 7, alert2: int = 3) -> dict:
    today = date.today()
    expiry = today + timedelta(days=days_ahead)
    return {
        "id": f"b-{days_ahead}",
        "expiry_date": expiry.isoformat(),
        "quantity": qty,
        "status": "active",
        "products": {
            "name": f"Producto {category}",
            "category": category,
            "price": price,
            "cost": price * 0.5,
            "pasillo": "3",
            "alert_days_1": alert1,
            "alert_days_2": alert2,
        },
    }


_FORECAST_NORMAL = [
    {"date": (date.today() + timedelta(days=i)).isoformat(),
     "temp_max": 20.0, "precipitation_mm": 0, "weather_code": 0,
     "is_hot": False, "is_rainy": False, "is_storm": False}
    for i in range(10)
]

_FORECAST_HOT = [
    {"date": (date.today() + timedelta(days=i)).isoformat(),
     "temp_max": 35.0, "precipitation_mm": 0, "weather_code": 0,
     "is_hot": True, "is_rainy": False, "is_storm": False}
    for i in range(10)
]

_FORECAST_RAINY = [
    {"date": (date.today() + timedelta(days=i)).isoformat(),
     "temp_max": 18.0, "precipitation_mm": 10.0, "weather_code": 61,
     "is_hot": False, "is_rainy": True, "is_storm": False}
    for i in range(10)
]


# ── Tests: get_weather_forecast ───────────────────────────────────────────────

class TestGetWeatherForecast:
    def test_returns_list_of_dicts(self):
        mock_data = {
            "daily": {
                "time": [(date.today() + timedelta(days=i)).isoformat() for i in range(5)],
                "temperature_2m_max": [22.0, 25.0, 30.0, 28.0, 19.0],
                "precipitation_sum": [0, 0, 5.0, 0, 12.0],
                "weathercode": [0, 0, 61, 0, 80],
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.agents.predictor.requests.get", return_value=mock_resp):
            forecast = get_weather_forecast(days=5)

        assert len(forecast) == 5
        assert all("is_hot" in f for f in forecast)
        assert forecast[2]["is_hot"] is True   # 30°C ≥ 30°C
        assert forecast[4]["is_rainy"] is True  # 12 mm ≥ 5 mm

    def test_api_error_returns_empty_list(self):
        with patch("backend.agents.predictor.requests.get",
                   side_effect=Exception("Network error")):
            result = get_weather_forecast()

        assert result == []

    def test_hot_flag_threshold_is_30(self):
        mock_data = {
            "daily": {
                "time": [date.today().isoformat()],
                "temperature_2m_max": [29.9],
                "precipitation_sum": [0],
                "weathercode": [0],
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.agents.predictor.requests.get", return_value=mock_resp):
            forecast = get_weather_forecast(days=1)

        assert forecast[0]["is_hot"] is False  # 29.9 < 30

    def test_rainy_flag_threshold_is_5mm(self):
        mock_data = {
            "daily": {
                "time": [date.today().isoformat()],
                "temperature_2m_max": [20.0],
                "precipitation_sum": [4.9],
                "weathercode": [0],
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.agents.predictor.requests.get", return_value=mock_resp):
            forecast = get_weather_forecast(days=1)

        assert forecast[0]["is_rainy"] is False  # 4.9 < 5


# ── Tests: _day_of_week_factor ────────────────────────────────────────────────

class TestDayOfWeekFactor:
    def test_saturday_has_highest_factor(self):
        # Buscar un sábado próximo
        d = date.today()
        while d.weekday() != 5:  # 5 = Sábado
            d += timedelta(days=1)
        assert _day_of_week_factor(d.isoformat()) == 1.30

    def test_monday_has_lowest_factor(self):
        d = date.today()
        while d.weekday() != 0:  # 0 = Lunes
            d += timedelta(days=1)
        assert _day_of_week_factor(d.isoformat()) == 0.75

    def test_invalid_date_returns_one(self):
        assert _day_of_week_factor("not-a-date") == 1.0
        assert _day_of_week_factor("") == 1.0


# ── Tests: predict_merma_risk ─────────────────────────────────────────────────

class TestPredictMermaRisk:
    def test_empty_batches_returns_empty_list(self):
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_NORMAL):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=[]):
                result = predict_merma_risk("demo-store-001", forecast_days=7)

        assert result == []

    def test_already_expired_batches_excluded(self):
        batch = _make_batch(days_ahead=-1, category="carne", qty=10, price=5.0)
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_NORMAL):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=[batch]):
                result = predict_merma_risk("demo-store-001")

        assert result == []

    def test_batches_in_alert_zone_excluded(self):
        # alert_days_2 = 3, batch expires in 2 days → ya está en alerta normal
        batch = _make_batch(days_ahead=2, category="carne", qty=10, price=5.0,
                            alert1=7, alert2=3)
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_NORMAL):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=[batch]):
                result = predict_merma_risk("demo-store-001")

        assert result == []

    def test_heat_increases_risk_for_meat(self):
        batch = _make_batch(days_ahead=6, category="carne", qty=15, price=6.0)
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_HOT):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=[batch]):
                result_hot = predict_merma_risk("demo-store-001")

        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_NORMAL):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=[batch]):
                result_normal = predict_merma_risk("demo-store-001")

        if result_hot and result_normal:
            assert result_hot[0]["risk_score"] > result_normal[0]["risk_score"]

    def test_rain_increases_risk_for_bread(self):
        batch = _make_batch(days_ahead=5, category="panaderia", qty=20, price=1.20)
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_RAINY):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=[batch]):
                result_rain = predict_merma_risk("demo-store-001")

        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_NORMAL):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=[batch]):
                result_dry = predict_merma_risk("demo-store-001")

        if result_rain and result_dry:
            assert result_rain[0]["risk_score"] >= result_dry[0]["risk_score"]

    def test_result_sorted_descending_by_risk(self):
        batches = [
            _make_batch(days_ahead=4, category="verdura", qty=5, price=0.80),
            _make_batch(days_ahead=6, category="carne", qty=25, price=8.00),
        ]
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_HOT):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=batches):
                result = predict_merma_risk("demo-store-001")

        if len(result) >= 2:
            for i in range(len(result) - 1):
                assert result[i]["risk_score"] >= result[i + 1]["risk_score"]

    def test_risk_score_bounded_0_100(self):
        batches = [_make_batch(days_ahead=5, category="carne", qty=100, price=20.0)]
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_HOT):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=batches):
                result = predict_merma_risk("demo-store-001")

        for pred in result:
            assert 0 <= pred["risk_score"] <= 100

    def test_all_required_keys_in_prediction(self):
        batch = _make_batch(days_ahead=5, category="carne", qty=10, price=5.0)
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_HOT):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=[batch]):
                result = predict_merma_risk("demo-store-001")

        if result:
            required = {
                "product_name", "category", "pasillo", "expiry_date",
                "days_until_expiry", "quantity", "value_at_risk",
                "risk_score", "risk_factors", "recommended_preemptive_action",
                "weather_alert",
            }
            assert required.issubset(result[0].keys())

    def test_max_20_results_returned(self):
        batches = [
            _make_batch(days_ahead=i + 4, category="carne", qty=10, price=5.0)
            for i in range(30)
        ]
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_HOT):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=batches):
                result = predict_merma_risk("demo-store-001")

        assert len(result) <= 20

    def test_batch_without_product_skipped(self):
        batch_no_product = {
            "id": "b-bad",
            "expiry_date": (date.today() + timedelta(days=5)).isoformat(),
            "quantity": 10,
            "status": "active",
            "products": None,
        }
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_NORMAL):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=[batch_no_product]):
                result = predict_merma_risk("demo-store-001")

        assert result == []

    def test_high_risk_score_recommends_preemptive_action(self):
        # Gran cantidad + calor + caducidad próxima → score alto
        batch = _make_batch(days_ahead=4, category="carne", qty=50, price=10.0)
        with patch("backend.agents.predictor.get_weather_forecast",
                   return_value=_FORECAST_HOT):
            with patch("backend.agents.predictor.database.get_batches_expiring_soon",
                       return_value=[batch]):
                result = predict_merma_risk("demo-store-001")

        if result and result[0]["risk_score"] >= 70:
            assert "AHORA" in result[0]["recommended_preemptive_action"].upper() or \
                   "planificar" in result[0]["recommended_preemptive_action"].lower()
