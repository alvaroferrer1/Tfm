"""
Tests del Parallel Evaluator.
Verifica paralelismo, ordenación, tolerancia a fallos y estadísticas.
"""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import pytest

from backend.agents.parallel_evaluator import evaluate_all_parallel, summary_stats

STORE_ID = "demo-store-001"

_MOCK_RISK_CRITICAL = {
    "risk_level": "CRÍTICO", "score": 95, "action": "rebajar",
    "price_adjustment_pct": 50, "reasoning": "Caduca hoy.",
    "thinking_summary": "", "days_left": 0, "total_value_at_risk": 50.0,
}
_MOCK_RISK_LOW = {
    "risk_level": "BAJO", "score": 10, "action": "ok",
    "price_adjustment_pct": 0, "reasoning": "Sin urgencia.",
    "thinking_summary": "", "days_left": 10, "total_value_at_risk": 5.0,
}


def _make_batch(batch_id: str, product_id: str, days: int, qty: int = 5) -> dict:
    return {
        "id": batch_id,
        "product_id": product_id,
        "expiry_date": (date.today() + timedelta(days=days)).isoformat(),
        "quantity": qty,
        "status": "active",
        "products": {
            "id": product_id,
            "name": f"Producto {product_id}",
            "category": "lacteos",
            "price": 2.0,
            "cost": 0.8,
            "pasillo": "1",
            "estanteria": "1",
            "nivel": "1",
        },
    }


class TestEvaluateAllParallel:
    def test_empty_batches_returns_empty_list(self):
        with patch("backend.agents.parallel_evaluator.database.get_batches_expiring_soon", return_value=[]):
            result = evaluate_all_parallel(STORE_ID, days=7)
        assert result == []

    def test_returns_results_for_each_batch(self):
        batches = [_make_batch("b-1", "p-1", 0), _make_batch("b-2", "p-2", 3)]
        with patch("backend.agents.parallel_evaluator.database.get_batches_expiring_soon", return_value=batches):
            with patch("backend.agents.parallel_evaluator.mem.recall_product_pattern", return_value=None):
                with patch("backend.agents.parallel_evaluator.database.get_warehouse_stock", return_value=0):
                    with patch("backend.agents.parallel_evaluator.evaluator.evaluate") as mock_eval:
                        mock_eval.return_value = _MOCK_RISK_LOW
                        result = evaluate_all_parallel(STORE_ID, days=7)
        assert len(result) == 2

    def test_sorted_by_score_descending(self):
        batches = [
            _make_batch("b-low", "p-low", 10),
            _make_batch("b-crit", "p-crit", 0),
        ]
        def fake_eval(product, batch_list, **kwargs):
            if product.get("id") == "p-crit":
                return _MOCK_RISK_CRITICAL
            return _MOCK_RISK_LOW

        with patch("backend.agents.parallel_evaluator.database.get_batches_expiring_soon", return_value=batches):
            with patch("backend.agents.parallel_evaluator.mem.recall_product_pattern", return_value=None):
                with patch("backend.agents.parallel_evaluator.database.get_warehouse_stock", return_value=0):
                    with patch("backend.agents.parallel_evaluator.evaluator.evaluate", side_effect=fake_eval):
                        result = evaluate_all_parallel(STORE_ID, days=7)

        assert len(result) == 2
        assert result[0]["score"] >= result[1]["score"]

    def test_result_has_location_fields(self):
        batches = [_make_batch("b-1", "p-1", 2)]
        with patch("backend.agents.parallel_evaluator.database.get_batches_expiring_soon", return_value=batches):
            with patch("backend.agents.parallel_evaluator.mem.recall_product_pattern", return_value=None):
                with patch("backend.agents.parallel_evaluator.database.get_warehouse_stock", return_value=0):
                    with patch("backend.agents.parallel_evaluator.evaluator.evaluate", return_value=_MOCK_RISK_LOW):
                        result = evaluate_all_parallel(STORE_ID, days=7)

        item = result[0]
        assert "pasillo" in item
        assert "estanteria" in item
        assert "batch_id" in item
        assert "product_name" in item

    def test_tolerates_individual_evaluation_error(self):
        """Un producto que falla no debe parar la evaluación de los demás."""
        batches = [_make_batch("b-ok", "p-ok", 3), _make_batch("b-fail", "p-fail", 1)]

        def fake_eval(product, batch_list, **kwargs):
            if product.get("id") == "p-fail":
                raise RuntimeError("LLM timeout simulado")
            return _MOCK_RISK_LOW

        with patch("backend.agents.parallel_evaluator.database.get_batches_expiring_soon", return_value=batches):
            with patch("backend.agents.parallel_evaluator.mem.recall_product_pattern", return_value=None):
                with patch("backend.agents.parallel_evaluator.database.get_warehouse_stock", return_value=0):
                    with patch("backend.agents.parallel_evaluator.evaluator.evaluate", side_effect=fake_eval):
                        result = evaluate_all_parallel(STORE_ID, days=7)

        # El producto que no falló debe aparecer, el que falló también (con fallback)
        assert len(result) == 2


class TestSummaryStats:
    def test_empty_returns_zeros(self):
        stats = summary_stats([])
        assert stats["total"] == 0
        assert stats["critical"] == 0
        assert stats["total_value_at_risk"] == 0.0

    def test_counts_by_level(self):
        results = [
            {**_MOCK_RISK_CRITICAL, "total_value_at_risk": 50.0},
            {**_MOCK_RISK_CRITICAL, "total_value_at_risk": 30.0},
            {**_MOCK_RISK_LOW, "total_value_at_risk": 5.0},
        ]
        stats = summary_stats(results)
        assert stats["total"] == 3
        assert stats["critical"] == 2
        assert stats["low"] == 1
        assert stats["total_value_at_risk"] == 85.0

    def test_actions_needed_excludes_ok_and_revisar(self):
        results = [
            {"risk_level": "CRÍTICO", "score": 95, "action": "rebajar", "total_value_at_risk": 50.0},
            {"risk_level": "MEDIO", "score": 50, "action": "revisar", "total_value_at_risk": 10.0},
            {"risk_level": "BAJO", "score": 10, "action": "ok", "total_value_at_risk": 5.0},
        ]
        stats = summary_stats(results)
        assert stats["actions_needed"] == 1
