"""Tests del Price Agent — sin red ni LLM."""
from datetime import date, timedelta
import pytest
from backend.agents.price import calculate, calculate_text, _base_discount, _velocity_boost, _intraday_factor


class TestBaseDiscount:
    def test_expires_today(self):
        assert _base_discount(0) == 0.60

    def test_expires_tomorrow(self):
        assert _base_discount(1) == 0.50

    def test_expires_2_days(self):
        assert _base_discount(2) == 0.40

    def test_expires_3_days(self):
        assert _base_discount(3) == 0.30

    def test_expires_5_days(self):
        assert _base_discount(5) == 0.20

    def test_expires_7_days(self):
        assert _base_discount(7) == 0.10

    def test_expires_10_days(self):
        assert _base_discount(10) == 0.0


class TestCalculate:
    def test_basic_discount_tomorrow(self, product_panaderia, batch_expiring_tomorrow):
        result = calculate(product_panaderia, batch_expiring_tomorrow, {"risk_level": "CRÍTICO", "price_adjustment_pct": 0})
        # panaderia: 50% base × 1.15 multiplicador × factor intraday (varía con la hora del día)
        # El factor intraday puede ser 0.90–1.30, y el precio comercial se redondea a múltiplo de 0.05€
        # Rango válido efectivo (después de redondeo comercial): 40–70%
        assert result["category_multiplier"] == 1.15
        assert 40 <= result["discount_pct"] <= 70, \
            f"Descuento panaderia fuera de rango válido (40-70%): fue {result['discount_pct']}%"
        assert result["new_price"] < product_panaderia["price"]
        assert result["new_price"] >= product_panaderia["cost"]
        # Verificar que el precio está redondeado a múltiplo de 0.05€
        assert round(result["new_price"] % 0.05, 3) in (0.0, 0.05), \
            f"Precio debe ser múltiplo de 0.05€ (comercial), fue {result['new_price']}"

    def test_cost_floor_applied(self):
        product = {"price": 1.00, "cost": 0.95}
        today = date.today()
        batch = {"expiry_date": today.isoformat()}
        result = calculate(product, batch, {"risk_level": "CRÍTICO", "price_adjustment_pct": 0})
        assert result["floor_applied"] is True
        assert result["new_price"] >= round(0.95 * 1.05, 2)

    def test_new_price_never_below_cost(self, product_carne):
        today = date.today()
        batch = {"expiry_date": today.isoformat()}
        result = calculate(product_carne, batch, {"risk_level": "CRÍTICO", "price_adjustment_pct": 70})
        assert result["new_price"] >= product_carne["cost"]

    def test_no_discount_far_future(self):
        product = {"price": 5.00, "cost": 2.00}
        batch = {"expiry_date": (date.today() + timedelta(days=30)).isoformat()}
        result = calculate(product, batch, {"risk_level": "BAJO", "price_adjustment_pct": 0})
        assert result["discount_pct"] == 0
        assert result["new_price"] == 5.00

    def test_no_price_registered(self):
        product = {"price": 0, "cost": 0}
        batch = {"expiry_date": date.today().isoformat()}
        result = calculate(product, batch, {})
        assert result["discount_pct"] == 0
        assert "Sin precio" in result["recommendation_text"]

    def test_recommendation_text_format(self, product_panaderia, batch_expiring_today):
        result = calculate(product_panaderia, batch_expiring_today, {"risk_level": "CRÍTICO", "price_adjustment_pct": 0})
        assert "euros" in result["recommendation_text"]
        assert "REBAJAR" in result["recommendation_text"]
        assert "%" in result["recommendation_text"]

    def test_evaluator_suggestion_overrides_base_when_higher(self, product_pescado, batch_expiring_3days):
        result_base = calculate(product_pescado, batch_expiring_3days, {"risk_level": "ALTO", "price_adjustment_pct": 0})
        result_suggested = calculate(product_pescado, batch_expiring_3days, {"risk_level": "ALTO", "price_adjustment_pct": 45})
        assert result_suggested["discount_pct"] >= result_base["discount_pct"]

    def test_result_has_all_required_keys(self, product_carne, batch_expiring_tomorrow):
        result = calculate(product_carne, batch_expiring_tomorrow, {"risk_level": "CRÍTICO", "price_adjustment_pct": 0})
        required = {"discount_pct", "new_price", "original_price", "floor_applied",
                    "velocity_boost_applied", "recommendation_text", "days_left", "risk_level"}
        assert required.issubset(result.keys())

    def test_carne_has_higher_discount_than_conservas(self):
        today = date.today()
        batch = {"expiry_date": (today + timedelta(days=3)).isoformat(), "quantity": 5}
        product_carne = {"price": 5.00, "cost": 2.00, "category": "carne"}
        product_conserva = {"price": 5.00, "cost": 2.00, "category": "conservas"}
        result_carne = calculate(product_carne, batch, {"risk_level": "ALTO", "price_adjustment_pct": 0})
        result_conserva = calculate(product_conserva, batch, {"risk_level": "ALTO", "price_adjustment_pct": 0})
        assert result_carne["discount_pct"] > result_conserva["discount_pct"]

    def test_discount_never_exceeds_70pct(self):
        product = {"price": 10.00, "cost": 0.10, "category": "carne"}
        batch = {"expiry_date": date.today().isoformat(), "quantity": 5}
        result = calculate(product, batch, {"risk_level": "CRÍTICO", "price_adjustment_pct": 70})
        assert result["discount_pct"] <= 70

    def test_velocity_boost_added_when_insufficient(self):
        product = {"price": 5.00, "cost": 1.00, "category": "lacteos", "avg_daily_sales": 1.0}
        today = date.today()
        batch = {"expiry_date": (today + timedelta(days=3)).isoformat(), "quantity": 30}
        result = calculate(product, batch, {"risk_level": "ALTO", "price_adjustment_pct": 0})
        assert result["velocity_boost_applied"] is True
        assert result["velocity_boost_pct"] > 0

    def test_velocity_boost_not_added_when_sufficient(self):
        product = {"price": 5.00, "cost": 1.00, "category": "lacteos", "avg_daily_sales": 10.0}
        today = date.today()
        batch = {"expiry_date": (today + timedelta(days=5)).isoformat(), "quantity": 10}
        result = calculate(product, batch, {"risk_level": "BAJO", "price_adjustment_pct": 0})
        assert result["velocity_boost_applied"] is False

    def test_string_risk_compat(self, product_panaderia, batch_expiring_today):
        result = calculate(product_panaderia, batch_expiring_today, "CRÍTICO — rebajar urgente")
        assert "recommendation_text" in result
        assert isinstance(result["discount_pct"], int)

    def test_original_price_preserved(self):
        product = {"price": 3.75, "cost": 1.50, "category": "fruta"}
        today = date.today()
        batch = {"expiry_date": (today + timedelta(days=2)).isoformat(), "quantity": 5}
        result = calculate(product, batch, {"risk_level": "ALTO", "price_adjustment_pct": 0})
        assert result["original_price"] == 3.75


class TestVelocityBoost:
    def test_no_boost_when_no_sales_data(self):
        product = {"price": 5.00, "cost": 2.00}
        batch = {"quantity": 20}
        assert _velocity_boost(product, batch, 3) == 0.0

    def test_no_boost_when_sufficient_velocity(self):
        product = {"avg_daily_sales": 10.0}
        batch = {"quantity": 5}
        assert _velocity_boost(product, batch, 3) == 0.0

    def test_boost_nonzero_when_insufficient(self):
        product = {"avg_daily_sales": 1.0}
        batch = {"quantity": 20}
        assert _velocity_boost(product, batch, 3) > 0

    def test_boost_max_15pct(self):
        product = {"avg_daily_sales": 0.01}
        batch = {"quantity": 1000}
        assert _velocity_boost(product, batch, 1) <= 0.15

    def test_no_boost_when_days_zero(self):
        product = {"avg_daily_sales": 1.0}
        batch = {"quantity": 10}
        assert _velocity_boost(product, batch, 0) == 0.0


class TestCalculateText:
    def test_returns_string(self, product_panaderia, batch_expiring_today):
        result = calculate_text(product_panaderia, batch_expiring_today, {"risk_level": "CRÍTICO", "price_adjustment_pct": 0})
        assert isinstance(result, str)
        assert len(result) > 10

    def test_no_discount_returns_sin_descuento(self):
        product = {"price": 5.00, "cost": 2.00}
        batch = {"expiry_date": (date.today() + timedelta(days=30)).isoformat()}
        result = calculate_text(product, batch, {"risk_level": "BAJO", "price_adjustment_pct": 0})
        assert "Sin descuento" in result or "días restantes" in result
