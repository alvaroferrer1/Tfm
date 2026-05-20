"""Tests para backend/core/batch_api.py — sin Anthropic API real."""
from __future__ import annotations
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_product_item(days_left: int = 3, qty: int = 5,
                       price: float = 2.5, cost: float = 1.0) -> dict:
    exp = (date.today() + timedelta(days=days_left)).isoformat()
    return {
        "id": "batch-001",
        "product_id": "prod-001",
        "expiry_date": exp,
        "quantity": qty,
        "products": {
            "name": "Yogur natural", "category": "lacteos",
            "price": price, "cost": cost,
        },
    }


# ── products_to_batch_input ───────────────────────────────────────────────────

class TestProductsToBatchInput:
    def test_empty_returns_empty(self):
        from backend.core.batch_api import products_to_batch_input
        assert products_to_batch_input([]) == []

    def test_maps_fields_correctly(self):
        from backend.core.batch_api import products_to_batch_input
        items = [_make_product_item(days_left=2, qty=10, price=3.0)]
        result = products_to_batch_input(items)
        assert len(result) == 1
        r = result[0]
        assert r["name"] == "Yogur natural"
        assert r["category"] == "lacteos"
        assert r["qty"] == 10
        assert r["price"] == 3.0
        assert r["days_left"] == 2

    def test_days_left_calculated(self):
        from backend.core.batch_api import products_to_batch_input
        items = [_make_product_item(days_left=5)]
        result = products_to_batch_input(items)
        assert result[0]["days_left"] == 5

    def test_invalid_date_handled(self):
        from backend.core.batch_api import products_to_batch_input
        item = _make_product_item()
        item["expiry_date"] = "not-a-date"
        result = products_to_batch_input([item])
        assert result[0]["days_left"] == 999

    def test_context_fn_called(self):
        from backend.core.batch_api import products_to_batch_input
        ctx_fn = MagicMock(return_value="historial: alta rotación")
        items = [_make_product_item()]
        result = products_to_batch_input(items, memory_fn=ctx_fn)
        assert "historial" in result[0]["context"]

    def test_multiple_items(self):
        from backend.core.batch_api import products_to_batch_input
        items = [_make_product_item(days_left=i) for i in range(5)]
        result = products_to_batch_input(items)
        assert len(result) == 5


# ── submit_evaluation_batch ───────────────────────────────────────────────────

class TestSubmitEvaluationBatch:
    def _mock_client_with_batch_id(self, batch_id: str = "msgbatch-test-001"):
        mock_batch = MagicMock()
        mock_batch.id = batch_id
        mock_client = MagicMock()
        mock_client.messages.batches.create.return_value = mock_batch
        return patch("backend.core.batch_api.get_client", return_value=mock_client)

    def test_empty_products_returns_none(self):
        from backend.core.batch_api import submit_evaluation_batch
        result = submit_evaluation_batch([])
        assert result is None

    def test_returns_batch_id(self):
        from backend.core.batch_api import submit_evaluation_batch
        products = [
            {"id": "p1", "name": "Pan", "category": "panaderia",
             "days_left": 1, "qty": 5, "price": 2.0, "cost": 1.0, "context": ""},
        ]
        with self._mock_client_with_batch_id("msgbatch-xyz-001"):
            result = submit_evaluation_batch(products)
        assert result == "msgbatch-xyz-001"

    def test_api_error_returns_none(self):
        from backend.core.batch_api import submit_evaluation_batch
        mock_client = MagicMock()
        mock_client.messages.batches.create.side_effect = RuntimeError("API down")
        with patch("backend.core.batch_api.get_client", return_value=mock_client):
            result = submit_evaluation_batch([
                {"id": "p1", "name": "X", "category": "general",
                 "days_left": 2, "qty": 1, "price": 1.0, "cost": 0.5, "context": ""},
            ])
        assert result is None


# ── get_batch_status ──────────────────────────────────────────────────────────

class TestGetBatchStatus:
    def _build_mock_result(self, json_text: str, custom_id: str = "eval-p1"):
        """Crea un resultado de batch mock."""
        block = MagicMock()
        block.type = "text"
        block.text = json_text

        msg = MagicMock()
        msg.content = [block]
        msg.usage = MagicMock(input_tokens=100, output_tokens=50,
                              cache_read_input_tokens=0,
                              cache_creation_input_tokens=0)

        inner = MagicMock()
        inner.type = "succeeded"
        inner.message = msg

        result = MagicMock()
        result.custom_id = custom_id
        result.result = inner
        return result

    def test_still_processing_returns_status(self):
        from backend.core.batch_api import get_batch_status
        mock_batch = MagicMock()
        mock_batch.processing_status = "processing"
        mock_batch.request_counts = MagicMock(processing=5, succeeded=0, errored=0)
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.return_value = mock_batch
        with patch("backend.core.batch_api.get_client", return_value=mock_client):
            result = get_batch_status("msgbatch-xxx")
        assert result["status"] == "processing"
        assert result["results"] is None

    def test_ended_returns_parsed_results(self):
        from backend.core.batch_api import get_batch_status
        json_payload = '{"score": 85, "risk_level": "CRÍTICO", "action": "rebajar", "price_adjustment_pct": 40, "reasoning": "Caduca hoy."}'
        mock_result = self._build_mock_result(json_payload)
        mock_batch = MagicMock()
        mock_batch.processing_status = "ended"
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.return_value = mock_batch
        mock_client.messages.batches.results.return_value = [mock_result]
        with patch("backend.core.batch_api.get_client", return_value=mock_client):
            result = get_batch_status("msgbatch-xxx")
        assert result["status"] == "ended"
        assert result["results"] is not None
        assert len(result["results"]) == 1
        r = result["results"][0]
        assert r["ok"] is True
        assert r["score"] == 85
        assert r["action"] == "rebajar"

    def test_ended_includes_cost_estimate(self):
        from backend.core.batch_api import get_batch_status
        mock_result = self._build_mock_result('{"score":50,"risk_level":"MEDIO","action":"revisar","price_adjustment_pct":0,"reasoning":"ok"}')
        mock_batch = MagicMock()
        mock_batch.processing_status = "ended"
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.return_value = mock_batch
        mock_client.messages.batches.results.return_value = [mock_result]
        with patch("backend.core.batch_api.get_client", return_value=mock_client):
            result = get_batch_status("msgbatch-xxx")
        assert "cost_usd" in result
        assert result["saved_pct"] == 50
        assert result["cost_usd"] >= 0

    def test_api_error_returns_error_status(self):
        from backend.core.batch_api import get_batch_status
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.side_effect = RuntimeError("Network error")
        with patch("backend.core.batch_api.get_client", return_value=mock_client):
            result = get_batch_status("msgbatch-xxx")
        assert result["status"] == "error"
        assert result["results"] is None
