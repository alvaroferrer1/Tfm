"""Tests del Price Agent — sin red ni LLM."""
from datetime import date, timedelta
import pytest
from backend.agents.price import calculate, _base_discount


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
        assert result["discount_pct"] == 50
        assert result["new_price"] < product_panaderia["price"]
        assert result["new_price"] >= product_panaderia["cost"]

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
