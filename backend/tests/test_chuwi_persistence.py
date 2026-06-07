"""
Tests para chuwi_persistence — estado de sesión, historial y persistencia.
Todos deterministas: ningún test llama a Supabase ni al LLM.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

import backend.core.chuwi_persistence as cp


# ── Conv state ────────────────────────────────────────────────────────────────

class TestConvState:
    def setup_method(self):
        cp._conv_state.clear()

    def test_default_state_is_idle(self):
        state = cp._get_conv_state("user-123")
        assert state["mode"] == "idle"
        assert state["data"] == {}

    def test_set_and_get_state(self):
        cp._set_conv_state("user-123", "route_active", {"step": 1})
        state = cp._get_conv_state("user-123")
        assert state["mode"] == "route_active"
        assert state["data"]["step"] == 1

    def test_clear_state(self):
        cp._set_conv_state("user-123", "donation_flow")
        cp._clear_conv_state("user-123")
        state = cp._get_conv_state("user-123")
        assert state["mode"] == "idle"

    def test_clear_nonexistent_leaves_state_idle(self):
        # Protege: _clear_conv_state con usuario inexistente no debe crear entradas
        # huérfanas ni corromper el dict global _conv_state.
        # Fallo real: si creara una entrada {"mode": "idle"} para usuarios inexistentes,
        # el dict crecería indefinidamente en producción con millones de user IDs.
        cp._clear_conv_state("user-never-existed")
        assert "user-never-existed" not in cp._conv_state, \
            "clear en usuario inexistente NO debe crear entrada en _conv_state"

    def test_state_isolated_per_user(self):
        cp._set_conv_state("user-A", "route_active")
        cp._set_conv_state("user-B", "donation_flow")
        assert cp._get_conv_state("user-A")["mode"] == "route_active"
        assert cp._get_conv_state("user-B")["mode"] == "donation_flow"


# ── History — fallback JSON ───────────────────────────────────────────────────

class TestHistoryFallback:
    def test_compact_keeps_recent_when_short(self):
        history = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        result = cp._compact_history(history)
        assert result == history  # sin cambio — debajo del umbral

    def test_compact_truncates_when_over_max(self):
        # MAX_HISTORY = 30; con 35 mensajes debe compactar
        history = [{"role": "user", "content": f"mensaje {i}"} for i in range(35)]
        with patch("backend.core.chuwi_persistence.llm.call_fast", return_value="resumen corto"):
            result = cp._compact_history(history)
        assert len(result) < 35
        # El primer elemento debe ser el resumen
        assert "resumen" in result[0]["content"].lower() or "contexto" in result[0]["content"].lower()

    def test_compact_fallback_when_llm_fails(self):
        history = [{"role": "user", "content": f"msg {i}"} for i in range(35)]
        with patch("backend.core.chuwi_persistence.llm.call_fast", side_effect=Exception("LLM down")):
            result = cp._compact_history(history)
        assert len(result) < 35
        assert isinstance(result[0]["content"], str)

    def test_get_chat_history_returns_empty_list_when_no_data(self):
        with patch("backend.core.chuwi_persistence._load_history_db", return_value=None), \
             patch("backend.core.chuwi_persistence._load_history", return_value={}):
            result = cp._get_chat_history("user-999-chat")
        assert result == []

    def test_get_chat_history_prefers_db_over_json(self):
        db_history = [{"role": "user", "content": "from db"}]
        json_history = [{"role": "user", "content": "from json"}]
        with patch("backend.core.chuwi_persistence._load_history_db", return_value=db_history), \
             patch("backend.core.chuwi_persistence._load_history", return_value={"key": json_history}):
            result = cp._get_chat_history("key")
        assert result[0]["content"] == "from db"

    def test_persist_chat_history_falls_back_to_json(self):
        captured = {}
        with patch("backend.core.chuwi_persistence._save_history_db", return_value=False), \
             patch("backend.core.chuwi_persistence._load_history", return_value={}), \
             patch("backend.core.chuwi_persistence._save_history", side_effect=lambda h: captured.update(h)):
            cp._persist_chat_history("chat-key", [{"role": "user", "content": "hola"}])
        assert "chat-key" in captured


# ── User cache ────────────────────────────────────────────────────────────────

class TestUserCache:
    def setup_method(self):
        cp._user_cache.clear()

    def test_get_user_returns_none_when_db_fails(self):
        with patch("backend.core.chuwi_persistence.database.get_user_by_telegram_id",
                   side_effect=Exception("DB down")):
            result = cp._get_user(99999)
        assert result is None

    def test_get_user_caches_result(self):
        mock_user = {"id": "u-001", "role": "worker"}
        with patch("backend.core.chuwi_persistence.database.get_user_by_telegram_id",
                   return_value=mock_user) as mock_db:
            result1 = cp._get_user(12345)
            result2 = cp._get_user(12345)
        # DB solo llamada 1 vez — segunda viene del cache
        mock_db.assert_called_once()
        assert result1 == result2 == mock_user

    def test_invalidate_clears_cache(self):
        cp._user_cache["12345"] = ({"id": "u-001"}, 9999999999.0)
        cp._invalidate_user_cache(12345)
        assert "12345" not in cp._user_cache

    def test_is_manager_true_for_admin(self):
        assert cp._is_manager({"role": "admin"}) is True

    def test_is_manager_true_for_manager(self):
        assert cp._is_manager({"role": "manager"}) is True

    def test_is_manager_false_for_worker(self):
        assert cp._is_manager({"role": "worker"}) is False

    def test_is_manager_false_for_none(self):
        assert cp._is_manager(None) is False


# ── Upsert telegram user ──────────────────────────────────────────────────────

class TestUpsertTelegramUser:
    def test_linked_user_sets_status_linked(self):
        mock_db = MagicMock()
        linked = {"id": "u-001", "store_id": "store-001"}
        with patch("backend.core.chuwi_persistence.database.get_db", return_value=mock_db):
            cp._upsert_telegram_user("111", "user_handle", "111", linked)
        call_args = mock_db.table.return_value.upsert.call_args[0][0]
        assert call_args["status"] == "linked"
        assert call_args["user_id"] == "u-001"

    def test_unlinked_user_sets_status_pending(self):
        mock_db = MagicMock()
        with patch("backend.core.chuwi_persistence.database.get_db", return_value=mock_db):
            cp._upsert_telegram_user("222", None, "222", None)
        call_args = mock_db.table.return_value.upsert.call_args[0][0]
        assert call_args["status"] == "pending"

    def test_db_error_does_not_block_telegram_handling(self):
        # Protege: si Supabase falla al registrar el usuario de Telegram, el sistema
        # NO debe romper el flujo — el empleado sigue recibiendo respuesta.
        # Fallo real: si esto propagaba, cada mensaje de un usuario nuevo crasheaba
        # el handler de Telegram y el bot se quedaba sin responder.
        from backend.core import chuwi_persistence as _cp
        with patch("backend.core.chuwi_persistence.database.get_db",
                   side_effect=Exception("DB down")):
            _cp._upsert_telegram_user("333", "user", "333", None)
        # El estado interno no debe quedar marcado como usuario registrado
        # (no hay cache de usuarios en _upsert, así que solo verificamos que no explota)


# ── Persist conversation message ──────────────────────────────────────────────

class TestPersistConversationMessage:
    def setup_method(self):
        cp._conv_id_cache.clear()

    def test_creates_conversation_and_logs_messages(self):
        with patch("backend.core.chuwi_persistence.database.get_active_conversation",
                   return_value=None), \
             patch("backend.core.chuwi_persistence.database.create_agent_conversation",
                   return_value="conv-abc-001"), \
             patch("backend.core.chuwi_persistence.database.log_agent_message") as mock_log:
            cp._persist_conversation_message(
                chat_key="store-demo_111",
                store_id="demo-store-001",
                telegram_user_id="111",
                user_text="¿cuántos críticos hay?",
                response="Hay 3 productos críticos.",
                tools_used=["get_pending_actions"],
                intent_tag="consulta_estado",
            )
        # 2 mensajes: user + assistant
        assert mock_log.call_count == 2

    def test_kuine_coordination_logged_when_analyze_product_used(self):
        with patch("backend.core.chuwi_persistence.database.get_active_conversation",
                   return_value="conv-xyz"), \
             patch("backend.core.chuwi_persistence.database.log_agent_message") as mock_log:
            cp._persist_conversation_message(
                chat_key="store-demo_222",
                store_id="demo-store-001",
                telegram_user_id="222",
                user_text="analiza el 8410001",
                response="Producto en riesgo alto.",
                tools_used=["analyze_product"],
            )
        # 3 mensajes: user + assistant + system (coordinación Kuine)
        assert mock_log.call_count == 3
        roles = [c.kwargs.get("role") or c.args[2] for c in mock_log.call_args_list]
        assert "system" in roles

    def test_db_error_silenced_and_conv_id_cache_not_poisoned(self):
        # Protege: cuando Supabase falla, _persist_conversation_message NO debe:
        #   1. Lanzar excepción (rompe la conversación del usuario)
        #   2. Guardar None en _conv_id_cache (causaría errores silenciosos posteriores)
        # Fallo real antes del fix: si la excepción se propagaba, el mensaje del empleado
        # se perdía sin respuesta y Telegram mostraba error al usuario.
        cp._conv_id_cache.clear()
        cp._conv_id_cache["k"] = "old-conv-id"  # simular entrada previa válida
        with patch("backend.core.chuwi_persistence.database.get_active_conversation",
                   side_effect=Exception("DB down")):
            cp._persist_conversation_message(
                chat_key="k", store_id="s", telegram_user_id="t",
                user_text="hola", response="hola", tools_used=[],
            )
        # Cache no debe quedar en estado inconsistente
        assert cp._conv_id_cache.get("k") == "old-conv-id", \
            "DB error no debe corromper el conv_id_cache existente"

    def test_conv_id_cached_after_first_call(self):
        cp._conv_id_cache.clear()
        with patch("backend.core.chuwi_persistence.database.get_active_conversation",
                   return_value="conv-cached"), \
             patch("backend.core.chuwi_persistence.database.log_agent_message"):
            cp._persist_conversation_message(
                chat_key="cache-test", store_id="s", telegram_user_id="t",
                user_text="msg1", response="resp1", tools_used=[],
            )
        assert cp._conv_id_cache.get("cache-test") == "conv-cached"


# ── Cache cleanup ─────────────────────────────────────────────────────────────

class TestCacheCleanup:
    def test_cleanup_removes_stale_users(self):
        import time
        cp._user_last_msg.clear()
        cp._conv_state.clear()
        # Añadir usuario con timestamp muy antiguo
        cp._user_last_msg["stale-user"] = time.monotonic() - cp._CACHE_TTL_SECONDS - 1
        cp._conv_state["stale-user"] = {"mode": "idle", "data": {}}
        cp._last_cleanup = 0.0  # forzar que se ejecute el cleanup

        cp._cleanup_stale_caches()

        assert "stale-user" not in cp._user_last_msg
        assert "stale-user" not in cp._conv_state

    def test_cleanup_skips_if_recent(self):
        import time
        cp._last_cleanup = time.monotonic()  # acaba de limpiar
        cp._user_last_msg["recent-user"] = time.monotonic() - 10  # reciente
        cp._cleanup_stale_caches()
        assert "recent-user" in cp._user_last_msg  # no debería haberse borrado
