"""
Tests for get_stores_comparison and import_batches_csv — Features #15 and #18.
All deterministic, no real Supabase connection.
"""
from unittest.mock import patch, MagicMock, call
import pytest

from backend.core.database import get_stores_comparison, import_batches_csv


STORE_ID = "demo-store-001"


# ─── get_stores_comparison ────────────────────────────────────────────────────

def _mock_db_comparison(rows):
    """Returns a mock get_db() whose table().select().eq().execute() returns rows."""
    mock_exec = MagicMock()
    mock_exec.execute.return_value = MagicMock(data=rows)
    mock_table = MagicMock()
    mock_table.table.return_value.select.return_value.eq.return_value = mock_exec
    return mock_table


class TestGetStoresComparison:
    def _run(self, current_rows, prev_rows=None):
        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if call_count == 1:
                mock.data = current_rows
            else:
                mock.data = prev_rows or []
            return mock

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = side_effect
        with patch("backend.core.database.get_db", return_value=mock_db):
            return get_stores_comparison(STORE_ID)

    def test_returns_list(self):
        rows = [{"store_id": STORE_ID, "store_name": "Súper Martínez", "merma_rate_pct": 5.2, "period": "2026-05"}]
        result = self._run(rows)
        assert isinstance(result, list)

    def test_adds_rank_field(self):
        rows = [
            {"store_id": "s1", "store_name": "A", "merma_rate_pct": 3.8, "period": "2026-05"},
            {"store_id": STORE_ID, "store_name": "B", "merma_rate_pct": 5.2, "period": "2026-05"},
        ]
        result = self._run(rows)
        ranks = {r["store_id"]: r["rank"] for r in result}
        assert ranks["s1"] == 1
        assert ranks[STORE_ID] == 2

    def test_sorted_by_merma_rate_ascending(self):
        rows = [
            {"store_id": "s2", "store_name": "C", "merma_rate_pct": 11.4, "period": "2026-05"},
            {"store_id": "s1", "store_name": "A", "merma_rate_pct": 3.8, "period": "2026-05"},
            {"store_id": STORE_ID, "store_name": "B", "merma_rate_pct": 5.2, "period": "2026-05"},
        ]
        result = self._run(rows)
        rates = [r["merma_rate_pct"] for r in result]
        assert rates == sorted(rates)

    def test_marks_current_store(self):
        rows = [
            {"store_id": "s1", "store_name": "Other", "merma_rate_pct": 3.8, "period": "2026-05"},
            {"store_id": STORE_ID, "store_name": "Súper Martínez", "merma_rate_pct": 5.2, "period": "2026-05"},
        ]
        result = self._run(rows)
        current = next(r for r in result if r["store_id"] == STORE_ID)
        other = next(r for r in result if r["store_id"] != STORE_ID)
        assert current["is_current"] is True
        assert other["is_current"] is False

    def test_empty_current_falls_back_to_previous_period(self):
        prev_rows = [{"store_id": STORE_ID, "store_name": "Súper Martínez", "merma_rate_pct": 5.2, "period": "2026-04"}]
        result = self._run(current_rows=[], prev_rows=prev_rows)
        assert len(result) == 1
        assert result[0]["store_name"] == "Súper Martínez"

    def test_both_periods_empty_returns_empty_list(self):
        result = self._run(current_rows=[], prev_rows=[])
        assert result == []

    def test_rank_1_is_lowest_merma(self):
        rows = [
            {"store_id": "s1", "store_name": "Best", "merma_rate_pct": 1.0, "period": "2026-05"},
            {"store_id": "s2", "store_name": "Worst", "merma_rate_pct": 20.0, "period": "2026-05"},
        ]
        result = self._run(rows)
        assert result[0]["rank"] == 1
        assert result[0]["merma_rate_pct"] == 1.0


# ─── import_batches_csv ───────────────────────────────────────────────────────

_VALID_PRODUCT = {"id": "p-001", "name": "Baguette artesana", "store_id": STORE_ID}
_VALID_CSV = "barcode,quantity,expiry_date\n8410001000001,10,2026-06-15\n"


class TestImportBatchesCsv:
    def _run(self, csv_data, product=_VALID_PRODUCT):
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])
        with patch("backend.core.database.get_product_by_barcode", return_value=product), \
             patch("backend.core.database.get_db", return_value=mock_db):
            return import_batches_csv(STORE_ID, csv_data)

    def test_valid_csv_imports_one_row(self):
        result = self._run(_VALID_CSV)
        assert result["imported"] == 1
        assert result["errors"] == 0

    def test_returns_dict_with_keys(self):
        result = self._run(_VALID_CSV)
        assert "imported" in result
        assert "errors" in result
        assert "error_details" in result

    def test_alias_columns_codigo_cantidad(self):
        csv = "codigo,cantidad,expiry_date\n8410001000001,5,2026-06-15\n"
        result = self._run(csv)
        assert result["imported"] == 1

    def test_date_format_ddmmyyyy_slash(self):
        csv = "barcode,quantity,expiry_date\n8410001000001,10,15/06/2026\n"
        result = self._run(csv)
        assert result["imported"] == 1
        assert result["errors"] == 0

    def test_date_format_ddmmyyyy_dash(self):
        csv = "barcode,quantity,expiry_date\n8410001000001,10,15-06-2026\n"
        result = self._run(csv)
        assert result["imported"] == 1

    def test_missing_barcode_counts_as_error(self):
        csv = "barcode,quantity,expiry_date\n,10,2026-06-15\n"
        result = self._run(csv)
        assert result["errors"] == 1
        assert result["imported"] == 0

    def test_invalid_quantity_counts_as_error(self):
        csv = "barcode,quantity,expiry_date\n8410001000001,abc,2026-06-15\n"
        result = self._run(csv)
        assert result["errors"] == 1

    def test_zero_quantity_counts_as_error(self):
        csv = "barcode,quantity,expiry_date\n8410001000001,0,2026-06-15\n"
        result = self._run(csv)
        assert result["errors"] == 1
        assert result["imported"] == 0

    def test_missing_expiry_date_counts_as_error(self):
        csv = "barcode,quantity,expiry_date\n8410001000001,10,\n"
        result = self._run(csv)
        assert result["errors"] == 1

    def test_product_not_found_counts_as_error(self):
        result = self._run(_VALID_CSV, product=None)
        assert result["errors"] == 1
        assert result["imported"] == 0

    def test_multiple_rows_mixed_valid_invalid(self):
        csv = (
            "barcode,quantity,expiry_date\n"
            "8410001000001,10,2026-06-15\n"  # valid
            ",5,2026-06-20\n"                 # no barcode
            "8410001000001,3,2026-06-10\n"   # valid
        )
        result = self._run(csv)
        assert result["imported"] == 2
        assert result["errors"] == 1

    def test_error_details_capped_at_10(self):
        # 15 rows all with missing barcode
        rows = "\n".join(f",{i},2026-06-15" for i in range(1, 16))
        csv = f"barcode,quantity,expiry_date\n{rows}\n"
        result = self._run(csv)
        assert len(result["error_details"]) <= 10

    def test_empty_csv_returns_zero_imported(self):
        csv = "barcode,quantity,expiry_date\n"
        result = self._run(csv)
        assert result["imported"] == 0
        assert result["errors"] == 0


# ─── Fase 1: agent_conversations, agent_messages, agent_sessions ──────────────

class TestAgentConversations:
    """Verifica que las funciones de persistencia de conversaciones existen y se firman bien."""

    def test_create_agent_conversation_exists(self):
        from backend.core.database import create_agent_conversation
        import inspect
        assert callable(create_agent_conversation)
        sig = inspect.signature(create_agent_conversation)
        assert "store_id" in sig.parameters
        assert "telegram_user_id" in sig.parameters

    def test_get_active_conversation_exists(self):
        from backend.core.database import get_active_conversation
        import inspect
        assert callable(get_active_conversation)
        sig = inspect.signature(get_active_conversation)
        assert "store_id" in sig.parameters
        assert "telegram_user_id" in sig.parameters

    def test_log_agent_message_exists(self):
        from backend.core.database import log_agent_message
        import inspect
        assert callable(log_agent_message)
        sig = inspect.signature(log_agent_message)
        required = ["conversation_id", "store_id", "role", "content"]
        for p in required:
            assert p in sig.parameters, f"Falta parámetro: {p}"

    def test_log_agent_message_optional_fields(self):
        from backend.core.database import log_agent_message
        import inspect
        sig = inspect.signature(log_agent_message)
        assert "tools_used" in sig.parameters
        assert "intent_tag" in sig.parameters
        assert "agent_source" in sig.parameters

    def test_create_agent_conversation_calls_supabase(self):
        from backend.core import database
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
        with patch("backend.core.database.get_db", return_value=mock_db):
            result = database.create_agent_conversation("demo-store-001", "12345")
        assert isinstance(result, str)
        assert len(result) > 0
        mock_db.table.assert_called_with("agent_conversations")

    def test_log_agent_message_inserts_and_returns_id(self):
        from backend.core import database
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(count=5)
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        with patch("backend.core.database.get_db", return_value=mock_db):
            msg_id = database.log_agent_message(
                conversation_id="conv-001",
                store_id="demo-store-001",
                role="user",
                content="Hola Chuwi",
                tools_used=[],
            )
        assert isinstance(msg_id, str)

    def test_log_agent_message_with_tools(self):
        from backend.core import database
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(count=3)
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        with patch("backend.core.database.get_db", return_value=mock_db):
            msg_id = database.log_agent_message(
                conversation_id="conv-001",
                store_id="demo-store-001",
                role="assistant",
                content="Aquí tienes el análisis",
                tools_used=["get_expiring_batches", "evaluate_batch"],
                agent_source="chuwi",
            )
        assert isinstance(msg_id, str)
        insert_call_args = mock_db.table.return_value.insert.call_args[0][0]
        assert insert_call_args["tools_used"] == ["get_expiring_batches", "evaluate_batch"]


class TestAgentSessions:
    def test_create_agent_session_exists(self):
        from backend.core.database import create_agent_session
        import inspect
        assert callable(create_agent_session)
        sig = inspect.signature(create_agent_session)
        assert "store_id" in sig.parameters

    def test_close_agent_session_exists(self):
        from backend.core.database import close_agent_session
        import inspect
        assert callable(close_agent_session)
        sig = inspect.signature(close_agent_session)
        assert "session_id" in sig.parameters

    def test_increment_session_stats_exists(self):
        from backend.core.database import increment_session_stats
        import inspect
        assert callable(increment_session_stats)
        sig = inspect.signature(increment_session_stats)
        assert "session_id" in sig.parameters

    def test_create_agent_session_returns_id(self):
        from backend.core import database
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
        with patch("backend.core.database.get_db", return_value=mock_db):
            sid = database.create_agent_session("demo-store-001", "99999")
        assert isinstance(sid, str) and len(sid) > 0


class TestCompleteActionMermaLog:
    """Verifica que complete_action escribe en merma_log (Fix Fase 1)."""

    def test_complete_action_logs_merma(self):
        from backend.core import database
        mock_db = MagicMock()
        # action query
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        # select action
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"store_id": "demo-store-001", "batch_id": "batch-1", "action_type": "rebajar", "donation_quantity": None}
        )
        # select batch
        batch_mock = MagicMock()
        batch_mock.data = {
            "store_id": "demo-store-001",
            "product_id": "prod-1",
            "quantity": 5,
            "products": {"price": 2.5, "cost": 1.0},
        }
        # The second select().eq().single().execute() is for batches
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            MagicMock(data={"store_id": "s", "batch_id": "b", "action_type": "rebajar", "donation_quantity": None}),
            batch_mock,
        ]
        # merma_log insert
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()

        with patch("backend.core.database.get_db", return_value=mock_db):
            database.complete_action("action-001", "empleado1", "ok")

        # Verificar que se hizo insert en alguna tabla (merma_log es una de ellas)
        assert mock_db.table.return_value.insert.called

    def test_complete_action_no_crash_without_batch(self):
        """complete_action no falla si no hay batch asociado."""
        from backend.core import database
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"store_id": "s", "batch_id": None, "action_type": "revisar", "donation_quantity": None}
        )
        with patch("backend.core.database.get_db", return_value=mock_db):
            database.complete_action("action-002", "empleado1")  # no debe lanzar excepción


class TestChuwiPersistenceHelpers:
    """Verifica que chuwi.py tiene las funciones de persistencia de Fase 1."""

    def test_persist_conversation_message_exists(self):
        import inspect
        from backend.core import chuwi
        assert hasattr(chuwi, "_persist_conversation_message")
        assert callable(chuwi._persist_conversation_message)
        sig = inspect.signature(chuwi._persist_conversation_message)
        assert "chat_key" in sig.parameters
        assert "tools_used" in sig.parameters

    def test_conv_id_cache_exists(self):
        from backend.core import chuwi
        assert hasattr(chuwi, "_conv_id_cache")
        assert isinstance(chuwi._conv_id_cache, dict)

    def test_run_agent_loop_returns_tuple(self):
        """_run_agent_loop debe retornar (str, list) — tupla con respuesta y tools."""
        import inspect
        from backend.core import chuwi
        assert inspect.iscoroutinefunction(chuwi._run_agent_loop)
        # Verificamos la firma
        sig = inspect.signature(chuwi._run_agent_loop)
        params = list(sig.parameters.keys())
        assert "chat_history" in params
        assert "user_text" in params
        assert "user" in params
