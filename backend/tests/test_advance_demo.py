"""
Tests for backend.data.advance_demo — sin conexión real a Supabase.

Todos los tests mockean get_admin_db (get_db) para no tocar la BD real.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ── Helper: mock de db que simula respuestas de Supabase ─────────────────────

def _make_batch(batch_id: str, days_from_today: int, product_id: str = "p-001", qty: int = 10) -> dict:
    expiry = (date.today() + timedelta(days=days_from_today)).isoformat()
    return {"id": batch_id, "expiry_date": expiry, "product_id": product_id, "quantity": qty}


def _build_mock_db(batches: list[dict], pending_actions: list[dict], old_pending: list[dict] | None = None):
    """Construye un mock de get_admin_db() que devuelve respuestas controladas."""
    mock_db = MagicMock()

    def table_side_effect(table_name: str):
        t = MagicMock()

        if table_name == "batches":
            select_chain = MagicMock()
            select_chain.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=batches)
            t.select.return_value = select_chain
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
            t.insert.return_value.execute.return_value = MagicMock()

        elif table_name == "actions":
            select_chain = MagicMock()
            select_chain.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=old_pending or []
            )
            t.select.return_value = select_chain
            t.insert.return_value.execute.return_value = MagicMock()
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()

        return t

    mock_db.table.side_effect = table_side_effect
    return mock_db


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAdvanceDemoSummaryKeys:
    """El resumen siempre debe tener las claves requeridas."""

    def test_required_keys_present_with_zero_days(self):
        from backend.data.advance_demo import advance
        with patch("backend.data.advance_demo.get_db") as mock_get_db:
            mock_get_db.return_value = _build_mock_db([], [])
            summary = advance(days=0, store_id="demo-store-001")

        required = {"days", "batches_updated", "actions_created", "actions_completed", "stock_reduced"}
        assert required.issubset(summary.keys()), f"Faltan claves: {required - summary.keys()}"

    def test_required_keys_present_with_two_days(self):
        from backend.data.advance_demo import advance
        batches = [_make_batch("b-1", 5), _make_batch("b-2", 10)]
        with patch("backend.data.advance_demo.get_db") as mock_get_db:
            mock_get_db.return_value = _build_mock_db(batches, [])
            summary = advance(days=2, store_id="demo-store-001")

        required = {"days", "batches_updated", "actions_created", "actions_completed", "stock_reduced"}
        assert required.issubset(summary.keys())


class TestAdvanceDemoZeroDays:
    """advance(days=0) no toca la BD y devuelve todo a cero."""

    def test_zero_days_returns_zero_counts(self):
        from backend.data.advance_demo import advance
        with patch("backend.data.advance_demo.get_db") as mock_get_db:
            mock_get_db.return_value = MagicMock()
            summary = advance(days=0, store_id="demo-store-001")

        assert summary["days"] == 0
        assert summary["batches_updated"] == 0
        assert summary["actions_created"] == 0
        assert summary["actions_completed"] == 0

    def test_zero_days_does_not_query_batches(self):
        """Con days=0 no debe hacer queries a Supabase."""
        from backend.data.advance_demo import advance
        mock_db = MagicMock()
        with patch("backend.data.advance_demo.get_db", return_value=mock_db):
            advance(days=0, store_id="demo-store-001")
        mock_db.table.assert_not_called()


class TestAdvanceDemoDaysField:
    """El campo days debe reflejar el argumento recibido."""

    def test_days_matches_input(self):
        from backend.data.advance_demo import advance
        with patch("backend.data.advance_demo.get_db") as mock_get_db:
            mock_get_db.return_value = _build_mock_db([], [])
            summary = advance(days=3, store_id="demo-store-001")
        assert summary["days"] == 3

    def test_days_single_day(self):
        from backend.data.advance_demo import advance
        with patch("backend.data.advance_demo.get_db") as mock_get_db:
            mock_get_db.return_value = _build_mock_db([], [])
            summary = advance(days=1, store_id="demo-store-001")
        assert summary["days"] == 1


class TestAdvanceDemoExpiryCalculation:
    """La resta de días se aplica correctamente a las fechas de caducidad."""

    def test_batches_updated_count_matches_active_batches(self):
        from backend.data.advance_demo import advance

        batches = [
            _make_batch("b-1", 10),
            _make_batch("b-2", 7),
            _make_batch("b-3", 15),
        ]
        with patch("backend.data.advance_demo.get_db") as mock_get_db:
            mock_get_db.return_value = _build_mock_db(batches, [])
            summary = advance(days=2, store_id="demo-store-001")

        # Al menos los 3 lotes activos deben haber sido actualizados
        assert summary["batches_updated"] >= 3

    def test_critical_detection_creates_actions(self):
        """Un lote que vence en 3 días se vuelve CRÍTICO (days_left=1) al avanzar 2."""
        from backend.data.advance_demo import advance

        batches = [_make_batch("b-critico", 3)]

        mock_db = MagicMock()

        def table_side(name):
            t = MagicMock()
            if name == "batches":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=batches)
                t.update.return_value.eq.return_value.execute.return_value = MagicMock()
                t.insert.return_value.execute.return_value = MagicMock()
            elif name == "actions":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                t.insert.return_value.execute.return_value = MagicMock()
                t.update.return_value.eq.return_value.execute.return_value = MagicMock()
            return t

        mock_db.table.side_effect = table_side

        with patch("backend.data.advance_demo.get_db", return_value=mock_db):
            summary = advance(days=2, store_id="demo-store-001")

        # Al avanzar 2 días sobre un lote a 3 días → queda a 1 día → CRÍTICO → acción creada
        assert summary["actions_created"] >= 1


class TestAdvanceDemoEmptyBatches:
    """advance() con BD vacía no lanza excepción y devuelve dict."""

    def test_empty_batches_no_crash(self):
        from backend.data.advance_demo import advance
        with patch("backend.data.advance_demo.get_db") as mock_get_db:
            mock_get_db.return_value = _build_mock_db([], [])
            summary = advance(days=2, store_id="demo-store-001")
        assert isinstance(summary, dict)

    def test_empty_batches_actions_created_nonneg(self):
        from backend.data.advance_demo import advance
        with patch("backend.data.advance_demo.get_db") as mock_get_db:
            mock_get_db.return_value = _build_mock_db([], [])
            summary = advance(days=1, store_id="demo-store-001")
        assert summary["actions_created"] >= 0


class TestAdvanceDemoReturnType:
    """advance() siempre devuelve dict, nunca None."""

    def test_returns_dict(self):
        from backend.data.advance_demo import advance
        with patch("backend.data.advance_demo.get_db") as mock_get_db:
            mock_get_db.return_value = _build_mock_db([], [])
            result = advance(days=2, store_id="demo-store-001")
        assert isinstance(result, dict)

    def test_all_numeric_values_are_integers(self):
        from backend.data.advance_demo import advance
        with patch("backend.data.advance_demo.get_db") as mock_get_db:
            mock_get_db.return_value = _build_mock_db([], [])
            summary = advance(days=1, store_id="demo-store-001")
        int_keys = ["batches_updated", "actions_created", "actions_completed", "stock_reduced"]
        for k in int_keys:
            assert isinstance(summary[k], int), f"{k} debe ser int, got {type(summary[k])}"
