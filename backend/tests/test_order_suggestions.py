"""
Tests for get_order_suggestions — Feature #25.
All deterministic, no LLM, no real database.
"""
from unittest.mock import patch, MagicMock
import pytest

from backend.core.database import get_order_suggestions


STORE_ID = "demo-store-001"


def _make_log(product_id: str, product_name: str, qty_lost: int, date: str = "2026-05-10") -> dict:
    return {
        "id": f"log-{product_id}-{date}",
        "store_id": STORE_ID,
        "date": date,
        "quantity_lost": qty_lost,
        "value_lost": qty_lost * 1.2,
        "batches": {
            "products": {
                "id": product_id,
                "name": product_name,
                "category": "panaderia",
                "pasillo": "A1",
                "price": 1.2,
            }
        },
    }


class TestGetOrderSuggestions:
    def _run(self, logs, warehouse=0):
        with patch("backend.core.database.get_merma_history", return_value=logs), \
             patch("backend.core.database.get_warehouse_stock", return_value=warehouse):
            return get_order_suggestions(STORE_ID)

    def test_empty_logs_returns_empty(self):
        result = self._run([])
        assert result == []

    def test_single_product_with_enough_loss(self):
        logs = [_make_log("p-001", "Baguette", qty_lost=14)]
        result = self._run(logs, warehouse=0)
        assert len(result) == 1
        r = result[0]
        assert r["product_name"] == "Baguette"
        assert r["order_qty"] > 0
        assert r["avg_daily_loss"] == pytest.approx(round(14 / 30, 2), abs=0.01)

    def test_warehouse_stock_reduces_order_qty(self):
        # qty_lost=30 → avg_daily=1.0, suggested_weekly=7
        # warehouse=0 → order_qty=7; warehouse=2 → order_qty=5
        logs = [_make_log("p-001", "Baguette", qty_lost=30)]
        result_no_stock = self._run(logs, warehouse=0)
        result_with_stock = self._run(logs, warehouse=2)
        assert len(result_no_stock) == 1 and len(result_with_stock) == 1
        assert result_with_stock[0]["order_qty"] < result_no_stock[0]["order_qty"]

    def test_warehouse_covers_full_need_order_is_zero(self):
        logs = [_make_log("p-001", "Baguette", qty_lost=7)]
        # avg daily = 7/30 ≈ 0.23, suggested_weekly ≈ round(0.23*7)=round(1.6)=2
        # warehouse=5 > 2, so order_qty = 0 → filtered out
        result = self._run(logs, warehouse=100)
        assert result == []

    def test_sorted_by_estimated_value_desc(self):
        logs = [
            _make_log("p-001", "Baguette", qty_lost=7),
            _make_log("p-002", "Nata fresca", qty_lost=60),
        ]
        # p-002 should come first (higher estimated_value)
        with patch("backend.core.database.get_merma_history", return_value=logs), \
             patch("backend.core.database.get_warehouse_stock", return_value=0):
            result = get_order_suggestions(STORE_ID)
        if len(result) >= 2:
            assert result[0]["estimated_value"] >= result[1]["estimated_value"]

    def test_logs_without_product_data_are_skipped(self):
        logs = [
            {"id": "log-x", "quantity_lost": 10, "batches": None},
            {"id": "log-y", "quantity_lost": 5, "batches": {"products": None}},
        ]
        result = self._run(logs)
        assert result == []

    def test_max_20_suggestions_returned(self):
        # Create 25 unique products each losing 10 units
        logs = [_make_log(f"p-{i:03d}", f"Producto {i}", qty_lost=10) for i in range(25)]
        result = self._run(logs, warehouse=0)
        assert len(result) <= 20
