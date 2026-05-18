"""Tests del Stock Agent — sin red ni LLM."""
from datetime import date, timedelta
import pytest
from backend.agents.stock import decide_restocking


class TestDecideRestocking:
    def test_no_batches(self, product_carne):
        result = decide_restocking(product_carne, [], warehouse_qty=10)
        assert result["should_restock"] is False

    def test_no_warehouse_stock(self, product_carne, batch_expiring_3days):
        result = decide_restocking(product_carne, [batch_expiring_3days], warehouse_qty=0)
        assert result["should_restock"] is False
        assert "almacén" in result["reason"]

    def test_fefo_blocks_restock_near_expiry(self, product_carne, batch_expiring_tomorrow):
        result = decide_restocking(product_carne, [batch_expiring_tomorrow], warehouse_qty=20)
        assert result["should_restock"] is False
        assert "FEFO" in result["reason"] or "caduca" in result["reason"].lower()

    def test_restock_when_low_stock_and_time(self):
        product = {
            "id": "p-007",
            "name": "Leche fresca 1L",
            "category": "lacteos",
            "price": 1.20,
            "cost": 0.55,
        }
        today = date.today()
        batch = {
            "id": "b-011",
            "product_id": "p-007",
            "expiry_date": (today + timedelta(days=5)).isoformat(),
            "quantity": 2,
            "status": "active",
        }
        result = decide_restocking(product, [batch], warehouse_qty=48)
        assert result["should_restock"] is True
        assert result["urgency"] in ("high", "medium")

    def test_no_restock_when_stock_sufficient(self, product_panaderia):
        today = date.today()
        batch = {
            "id": "b-013",
            "product_id": product_panaderia["id"],
            "expiry_date": (today + timedelta(days=5)).isoformat(),
            "quantity": 15,
            "status": "active",
        }
        result = decide_restocking(product_panaderia, [batch], warehouse_qty=10)
        assert result["should_restock"] is False

    def test_fefo_carne_threshold_is_2_days(self, product_carne):
        today = date.today()
        batch_2days = {
            "id": "b-x",
            "product_id": product_carne["id"],
            "expiry_date": (today + timedelta(days=2)).isoformat(),
            "quantity": 1,
            "status": "active",
        }
        result = decide_restocking(product_carne, [batch_2days], warehouse_qty=20)
        assert result["should_restock"] is False

    def test_urgency_high_when_only_1_unit(self):
        product = {"id": "p-x", "name": "Test", "category": "lacteos"}
        today = date.today()
        batch = {
            "id": "b-x",
            "product_id": "p-x",
            "expiry_date": (today + timedelta(days=6)).isoformat(),
            "quantity": 1,
            "status": "active",
        }
        result = decide_restocking(product, [batch], warehouse_qty=10)
        assert result["urgency"] == "high"
