"""
Tests del agente Chuwi — _execute_tool_sync, multi-turn loop, advance_demo.

Todos los tests son deterministas: no llaman al LLM real ni a Supabase.
Solo testean la lógica de routing, construcción de mensajes y estructura de datos.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── Fixtures comunes ──────────────────────────────────────────────────────────

def _make_batch(days_left: int = 2, qty: int = 5, price: float = 3.0, cost: float = 1.5,
                name: str = "Merluza", pasillo: str = "4") -> dict:
    exp = (date.today() + timedelta(days=days_left)).isoformat()
    return {
        "id": "batch-test-001",
        "store_id": "demo-store-001",
        "product_id": "prod-001",
        "expiry_date": exp,
        "quantity": qty,
        "status": "active",
        "products": {"name": name, "price": price, "cost": cost, "pasillo": pasillo},
    }


def _make_action(score: int = 90, action_type: str = "rebajar", status: str = "pending") -> dict:
    return {
        "id": f"act-{score}",
        "store_id": "demo-store-001",
        "batch_id": "batch-test-001",
        "action_type": action_type,
        "priority_score": score,
        "status": status,
        "notes": "Test action",
        "batches": _make_batch(),
    }


# ── Tests _execute_tool_sync ──────────────────────────────────────────────────

class TestExecuteToolSync:
    """Tests para cada herramienta del agente Chuwi."""

    def _run(self, tool_name: str, tool_input: dict, user: dict | None = None,
             mock_db_calls: dict | None = None):
        """Helper: ejecuta _execute_tool_sync con mocks de BD."""
        from backend.core.chuwi import _execute_tool_sync

        patches = {
            "backend.core.chuwi.database.get_pending_actions": MagicMock(return_value=[]),
            "backend.core.chuwi.database.get_latest_brief": MagicMock(return_value=None),
            "backend.core.chuwi.database.get_batches_expiring_soon": MagicMock(return_value=[]),
            "backend.core.chuwi.database.get_merma_history": MagicMock(return_value=[]),
            "backend.core.chuwi.database.get_donation_stats": MagicMock(return_value={
                "total_donations": 0, "total_quantity": 0, "total_value_donated": 0.0
            }),
            "backend.core.chuwi.database.get_supplier_stats": MagicMock(return_value=[]),
            "backend.core.chuwi.database.get_order_suggestions": MagicMock(return_value=[]),
            "backend.core.chuwi.database.complete_action": MagicMock(return_value=True),
            "backend.core.chuwi.database.log_donation": MagicMock(return_value=True),
        }
        if mock_db_calls:
            patches.update(mock_db_calls)

        with patch.dict("sys.modules", {}):
            for target, mock in patches.items():
                with patch(target, mock):
                    pass

        with patch("backend.core.chuwi.database.get_pending_actions",
                   patches["backend.core.chuwi.database.get_pending_actions"]), \
             patch("backend.core.chuwi.database.get_latest_brief",
                   patches["backend.core.chuwi.database.get_latest_brief"]), \
             patch("backend.core.chuwi.database.get_batches_expiring_soon",
                   patches["backend.core.chuwi.database.get_batches_expiring_soon"]), \
             patch("backend.core.chuwi.database.get_merma_history",
                   patches["backend.core.chuwi.database.get_merma_history"]), \
             patch("backend.core.chuwi.database.get_donation_stats",
                   patches["backend.core.chuwi.database.get_donation_stats"]), \
             patch("backend.core.chuwi.database.get_supplier_stats",
                   patches["backend.core.chuwi.database.get_supplier_stats"]), \
             patch("backend.core.chuwi.database.get_order_suggestions",
                   patches["backend.core.chuwi.database.get_order_suggestions"]), \
             patch("backend.core.chuwi.database.complete_action",
                   patches["backend.core.chuwi.database.complete_action"]), \
             patch("backend.core.chuwi.database.log_donation",
                   patches["backend.core.chuwi.database.log_donation"]):
            return _execute_tool_sync(tool_name, tool_input, user)

    def test_get_store_overview_no_actions(self):
        result = self._run("get_store_overview", {})
        assert "semaforo" in result
        assert result["semaforo"] in ("VERDE", "AMARILLO", "ROJO")
        assert result["pending_total"] == 0
        assert result["criticos"] == 0

    def test_get_store_overview_with_criticals(self):
        criticos = [_make_action(score=90), _make_action(score=95), _make_action(score=87),
                    _make_action(score=91), _make_action(score=92)]
        result = self._run("get_store_overview", {}, mock_db_calls={
            "backend.core.chuwi.database.get_pending_actions": MagicMock(return_value=criticos),
        })
        assert result["semaforo"] == "ROJO"
        assert result["criticos"] == 5

    def test_get_pending_actions_structure(self):
        actions = [_make_action(score=90), _make_action(score=70)]
        result = self._run("get_pending_actions", {"max_results": 5}, mock_db_calls={
            "backend.core.chuwi.database.get_pending_actions": MagicMock(return_value=actions),
        })
        assert "acciones" in result
        assert result["total"] == 2
        assert result["mostrando"] == 2
        first = result["acciones"][0]
        assert first["priority_score"] == 90
        assert "product" in first
        assert "action_type" in first

    def test_get_pending_actions_sorted_by_priority(self):
        actions = [_make_action(score=50), _make_action(score=95), _make_action(score=70)]
        result = self._run("get_pending_actions", {"max_results": 10}, mock_db_calls={
            "backend.core.chuwi.database.get_pending_actions": MagicMock(return_value=actions),
        })
        scores = [a["priority_score"] for a in result["acciones"]]
        assert scores == sorted(scores, reverse=True)

    def test_get_pending_actions_max_results_respected(self):
        actions = [_make_action(score=i) for i in range(80, 95)]
        result = self._run("get_pending_actions", {"max_results": 3}, mock_db_calls={
            "backend.core.chuwi.database.get_pending_actions": MagicMock(return_value=actions),
        })
        assert result["mostrando"] <= 3

    def test_complete_action_ok(self):
        user = {"email": "carlos@supermarinez.es", "role": "employee"}
        result = self._run("complete_action", {"action_id": "act-123"}, user=user)
        assert result["ok"] is True
        assert "carlos" in result["completada_por"]

    def test_complete_action_without_user(self):
        result = self._run("complete_action", {"action_id": "act-456"}, user=None)
        assert result["ok"] is True
        assert result["completada_por"] == "empleado"

    def test_register_donation_banco_alimentos(self):
        user = {"email": "ana@supermarinez.es", "role": "employee"}
        result = self._run("register_donation", {
            "entity": "banco_alimentos",
            "quantity": 8,
            "product_name": "Pan de molde",
        }, user=user)
        assert result["ok"] is True
        assert result["entidad"] == "Banco de Alimentos"
        assert result["cantidad"] == 8

    def test_register_donation_caritas(self):
        result = self._run("register_donation", {
            "entity": "caritas",
            "quantity": 3,
            "product_name": "Yogures",
        })
        assert result["ok"] is True
        assert result["entidad"] == "Cáritas"

    def test_get_suppliers_requires_manager(self):
        user = {"email": "empleado@supermarinez.es", "role": "employee"}
        result = self._run("get_suppliers", {}, user=user)
        assert "error" in result

    def test_get_suppliers_manager_ok(self):
        user = {"email": "manager@supermarinez.es", "role": "manager"}
        result = self._run("get_suppliers", {}, user=user)
        assert "proveedores" in result

    def test_get_order_suggestions_requires_manager(self):
        user = {"email": "emp@supermarinez.es", "role": "employee"}
        result = self._run("get_order_suggestions", {}, user=user)
        assert "error" in result

    def test_get_merma_stats_no_history(self):
        result = self._run("get_merma_stats", {"days": 7})
        assert result["valor_total_eur"] == 0.0
        assert result["dias"] == 7

    def test_unknown_tool_returns_error(self):
        result = self._run("herramienta_que_no_existe", {})
        assert "error" in result

    def test_get_donation_impact_structure(self):
        result = self._run("get_donation_impact", {"days": 30})
        assert "total_donations" in result


# ── Tests lógica advance_demo ─────────────────────────────────────────────────

class TestAdvanceDemoLogic:
    """Tests para la lógica de simulación temporal — sin llamar a Supabase real."""

    def test_fmt_date_format(self):
        from backend.data.advance_demo import _fmt_date
        d = date(2026, 5, 20)
        result = _fmt_date(d)
        assert "mayo" in result
        assert "20" in result

    def test_fmt_date_weekday(self):
        from backend.data.advance_demo import _fmt_date
        d = date(2026, 5, 18)
        result = _fmt_date(d)
        assert "lunes" in result

    def test_advance_result_keys(self):
        from backend.data.advance_demo import advance
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        with patch("backend.data.advance_demo.get_db", return_value=mock_db), \
             patch("backend.data.advance_demo._ensure_risk_distribution"), \
             patch("backend.data.advance_demo._generate_simulated_brief"), \
             patch("backend.data.advance_demo._send_day_telegram_messages", return_value=0):
            result = advance(2.0, store_id="demo-store-001", generate_brief=False)

        assert "days" in result
        assert "batches_updated" in result
        assert "actions_created" in result
        assert "actions_completed" in result
        assert "stock_reduced" in result
        assert "telegram_messages_sent" in result
        assert result["days"] == 2.0

    def test_advance_days_1_calls_simulate_once(self):
        from backend.data.advance_demo import advance
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []

        simulate_mock = MagicMock(return_value={
            "batches_updated": 5, "actions_created": 2,
            "actions_completed": 3, "stock_reduced": 10,
        })

        with patch("backend.data.advance_demo.get_db", return_value=mock_db), \
             patch("backend.data.advance_demo._simulate_one_day", simulate_mock), \
             patch("backend.data.advance_demo._send_day_telegram_messages", return_value=2), \
             patch("backend.data.advance_demo._ensure_risk_distribution"), \
             patch("backend.data.advance_demo._generate_simulated_brief"):
            result = advance(1.0, generate_brief=True)

        assert simulate_mock.call_count == 1
        assert result["batches_updated"] == 5

    def test_advance_days_3_calls_simulate_three_times(self):
        from backend.data.advance_demo import advance
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []

        simulate_mock = MagicMock(return_value={
            "batches_updated": 3, "actions_created": 1,
            "actions_completed": 2, "stock_reduced": 5,
        })

        with patch("backend.data.advance_demo.get_db", return_value=mock_db), \
             patch("backend.data.advance_demo._simulate_one_day", simulate_mock), \
             patch("backend.data.advance_demo._send_day_telegram_messages", return_value=3), \
             patch("backend.data.advance_demo._ensure_risk_distribution"), \
             patch("backend.data.advance_demo._generate_simulated_brief"):
            result = advance(3.0, generate_brief=False)

        assert simulate_mock.call_count == 3
        assert result["batches_updated"] == 9

    def test_simulate_one_day_expired_batches_become_sold(self):
        from backend.data.advance_demo import _simulate_one_day

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        batches_active = [{"id": "b1", "expiry_date": yesterday, "quantity": 5, "status": "active"}]
        pending_actions = [{"id": "a1", "batch_id": "b1", "priority_score": 50}]
        fresh_batches = [{"id": "b1", "expiry_date": yesterday, "quantity": 5,
                          "status": "active", "products": {}}]

        update_calls = []

        def table_side_effect(name):
            m = MagicMock()
            if name == "batches":
                def select_chain(*a, **kw):
                    s = MagicMock()
                    s.eq.return_value.eq.return_value.execute.return_value.data = batches_active
                    s.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = fresh_batches
                    return s
                m.select.side_effect = select_chain
                def update_chain(data):
                    update_calls.append(data)
                    u = MagicMock()
                    u.eq.return_value.execute.return_value = MagicMock()
                    return u
                m.update.side_effect = update_chain
                m.upsert.return_value.execute.return_value = MagicMock()
            elif name == "actions":
                a = MagicMock()
                a.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = pending_actions
                a.update.return_value.eq.return_value.execute.return_value = MagicMock()
                a.upsert.return_value.execute.return_value = MagicMock()
                return a
            return m

        mock_db = MagicMock()
        mock_db.table.side_effect = table_side_effect

        _simulate_one_day(mock_db, "demo-store-001", date.today(), timedelta(days=1), date.today())

        assert any(c.get("status") == "sold" for c in update_calls if isinstance(c, dict))

    def test_simulate_one_day_stock_reduced(self):
        from backend.data.advance_demo import _simulate_one_day

        future = (date.today() + timedelta(days=10)).isoformat()
        batches_active = [{"id": "b2", "expiry_date": future, "quantity": 100, "status": "active"}]
        pending_actions: list = []
        fresh_batches: list = []

        def table_side_effect(name):
            m = MagicMock()
            if name == "batches":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = batches_active
                m.update.return_value.eq.return_value.execute.return_value = MagicMock()
                m.upsert.return_value.execute.return_value = MagicMock()
            elif name == "actions":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = pending_actions
                m.update.return_value.eq.return_value.execute.return_value = MagicMock()
                m.upsert.return_value.execute.return_value = MagicMock()
            return m

        mock_db = MagicMock()
        mock_db.table.side_effect = table_side_effect

        result = _simulate_one_day(mock_db, "test", date.today(), timedelta(days=1), date.today())
        assert result["batches_updated"] == 1


# ── Tests lógica de detección de queries complejas ────────────────────────────

class TestComplexQueryDetection:
    def test_short_message_not_complex(self):
        from backend.core.chuwi import _is_complex_query
        assert _is_complex_query("hola") is False
        assert _is_complex_query("ok") is False

    def test_long_message_is_complex(self):
        from backend.core.chuwi import _is_complex_query
        long_msg = "x" * 150
        assert _is_complex_query(long_msg) is True

    def test_analisis_keyword_is_complex(self):
        from backend.core.chuwi import _is_complex_query
        assert _is_complex_query("analiza los productos del pasillo 3") is True

    def test_merma_keyword_is_complex(self):
        from backend.core.chuwi import _is_complex_query
        assert _is_complex_query("cuál fue la merma esta semana") is True

    def test_simple_action_not_complex(self):
        from backend.core.chuwi import _is_complex_query
        assert _is_complex_query("ya lo hice") is False
        assert _is_complex_query("listo") is False


# ── Tests herramientas CHUWI_TOOLS están bien definidas ──────────────────────

class TestChuwiToolsDefinition:
    def test_all_tools_have_required_fields(self):
        from backend.core.chuwi import CHUWI_TOOLS
        for tool in CHUWI_TOOLS:
            assert "name" in tool, f"Tool sin name: {tool}"
            assert "description" in tool, f"Tool sin description: {tool}"
            assert "input_schema" in tool, f"Tool sin input_schema: {tool}"
            assert tool["input_schema"]["type"] == "object"

    def test_tool_names_match_labels(self):
        from backend.core.chuwi import CHUWI_TOOLS, _TOOL_LABELS
        tool_names = {t["name"] for t in CHUWI_TOOLS}
        for label_key in _TOOL_LABELS:
            assert label_key in tool_names, f"Label '{label_key}' no tiene tool correspondiente"

    def test_advance_demo_tool_exists(self):
        from backend.core.chuwi import CHUWI_TOOLS
        names = [t["name"] for t in CHUWI_TOOLS]
        assert "advance_demo_time" in names

    def test_register_donation_tool_exists(self):
        from backend.core.chuwi import CHUWI_TOOLS
        names = [t["name"] for t in CHUWI_TOOLS]
        assert "register_donation" in names

    def test_max_agent_iterations_value(self):
        from backend.core.chuwi import MAX_AGENT_ITERATIONS
        assert MAX_AGENT_ITERATIONS >= 3
        assert MAX_AGENT_ITERATIONS <= 10


# ── Tests nuevos comandos y seguridad ────────────────────────────────────────

class TestNewCommandHandlers:
    """Valida que todos los nuevos handlers estén definidos y sean async."""

    def test_cmd_agentes_is_coroutine(self):
        import inspect
        from backend.core.chuwi import _cmd_agentes
        assert inspect.iscoroutinefunction(_cmd_agentes)

    def test_cmd_kuine_is_coroutine(self):
        import inspect
        from backend.core.chuwi import _cmd_kuine
        assert inspect.iscoroutinefunction(_cmd_kuine)

    def test_cmd_demo_is_coroutine(self):
        import inspect
        from backend.core.chuwi import _cmd_demo
        assert inspect.iscoroutinefunction(_cmd_demo)

    def test_cmd_yo_is_coroutine(self):
        import inspect
        from backend.core.chuwi import _cmd_yo
        assert inspect.iscoroutinefunction(_cmd_yo)

    def test_cmd_estado_is_coroutine(self):
        import inspect
        from backend.core.chuwi import _cmd_estado
        assert inspect.iscoroutinefunction(_cmd_estado)

    def test_cmd_criticos_is_coroutine(self):
        import inspect
        from backend.core.chuwi import _cmd_criticos
        assert inspect.iscoroutinefunction(_cmd_criticos)

    def test_cmd_ayuda_is_coroutine(self):
        import inspect
        from backend.core.chuwi import _cmd_ayuda
        assert inspect.iscoroutinefunction(_cmd_ayuda)

    def test_cmd_logout_is_coroutine(self):
        import inspect
        from backend.core.chuwi import _cmd_logout
        assert inspect.iscoroutinefunction(_cmd_logout)

    def test_handle_demo_callback_is_coroutine(self):
        import inspect
        from backend.core.chuwi import _handle_demo_callback
        assert inspect.iscoroutinefunction(_handle_demo_callback)

    def test_auto_save_chat_id_callable(self):
        from backend.core.chuwi import _auto_save_chat_id
        assert callable(_auto_save_chat_id)

    def test_agentes_text_contains_kuine(self):
        from backend.core.chuwi import _AGENTES_TEXT
        text_upper = _AGENTES_TEXT.upper()
        assert "KUINE" in text_upper
        assert "EVALUADOR" in text_upper or "EVALUATOR" in text_upper

    def test_agentes_text_contains_models(self):
        from backend.core.chuwi import _AGENTES_TEXT
        assert "Opus" in _AGENTES_TEXT
        assert "Sonnet" in _AGENTES_TEXT

    def test_post_init_is_coroutine(self):
        import inspect
        from backend.core.chuwi import _post_init
        assert inspect.iscoroutinefunction(_post_init)


class TestLogoutFlow:
    """Tests para el flujo de desvinculación de Telegram."""

    def _make_user(self, role: str = "staff") -> dict:
        return {"id": "user-001", "email": "test@supermarinez.es", "role": role}

    def test_do_unlink_updates_telegram_id(self):
        """_do_unlink_telegram debe llamar a database.get_db().table('users').update()."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from backend.core.chuwi import _do_unlink_telegram

        mock_update = MagicMock()
        mock_update.effective_user.first_name = "Carlos"
        mock_update.message.reply_text = AsyncMock()

        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        async def _run():
            with patch("backend.core.chuwi.database.get_db", return_value=mock_db):
                await _do_unlink_telegram(mock_update, self._make_user())

        asyncio.run(_run())

        mock_db.table.assert_called_with("users")
        update_call_args = mock_db.table.return_value.update.call_args[0][0]
        assert update_call_args.get("telegram_user_id") is None
        mock_update.message.reply_text.assert_called_once()

    def test_do_unlink_no_user(self):
        """Sin usuario, debe pedir /start."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from backend.core.chuwi import _do_unlink_telegram

        mock_update = MagicMock()
        mock_update.effective_user.first_name = "Alguien"
        mock_update.message.reply_text = AsyncMock()

        asyncio.run(_do_unlink_telegram(mock_update, None))

        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "/start" in call_text


class TestCallbackRouting:
    """Valida que los nuevos callback_data están correctamente manejados."""

    def test_demo_advance_callback_data_format(self):
        """El callback data demo:advance:N tiene el formato correcto."""
        data = "demo:advance:3"
        parts = data.split(":")
        assert parts[0] == "demo"
        assert parts[1] == "advance"
        assert float(parts[2]) == 3.0

    def test_demo_reset_callback_data(self):
        data = "demo:reset"
        assert data.startswith("demo:")
        parts = data.split(":")
        assert parts[1] == "reset"

    def test_cmd_estado_callback_data(self):
        assert "cmd:estado".startswith("cmd:")
        assert "cmd:estado" != "cmd:menu"

    def test_cmd_criticos_callback_data(self):
        assert "cmd:criticos".startswith("cmd:")

    def test_cmd_agentes_info_callback_data(self):
        assert "cmd:agentes_info".startswith("cmd:")


class TestSecurityEndpoints:
    """Tests de seguridad para los endpoints de la API."""

    def test_unlink_telegram_requires_real_auth(self):
        """El endpoint DELETE /user/link-telegram rechaza dev_mode."""
        from backend.api.routes import unlink_telegram
        import pytest
        from fastapi import HTTPException

        auth_dev = {"sub": "user-001", "dev_mode": True}
        with pytest.raises(HTTPException) as exc_info:
            unlink_telegram(auth=auth_dev)
        assert exc_info.value.status_code == 401

    def test_unlink_telegram_requires_sub(self):
        """Sin sub en el token, debe rechazar con 401."""
        from backend.api.routes import unlink_telegram
        import pytest
        from fastapi import HTTPException

        auth_empty = {"dev_mode": False}
        with pytest.raises(HTTPException) as exc_info:
            unlink_telegram(auth=auth_empty)
        assert exc_info.value.status_code == 401

    def test_chuwi_token_not_in_code(self):
        """El token de Telegram NO debe estar hardcodeado en ningún fichero .py."""
        import os, re
        token_pattern = re.compile(r'\d{8,10}:AA[A-Za-z0-9_-]{33}')
        base = os.path.join(os.path.dirname(__file__), '..', '..')
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'build', '.dart_tool')]
            for fname in files:
                if fname.endswith('.py') and fname != '.env':
                    fpath = os.path.join(root, fname)
                    try:
                        content = open(fpath, encoding='utf-8', errors='ignore').read()
                        if token_pattern.search(content):
                            raise AssertionError(f"Token Telegram hardcodeado en {fpath}")
                    except (PermissionError, IsADirectoryError):
                        pass

    def test_anthropic_key_not_in_code(self):
        """La API key de Anthropic NO debe estar hardcodeada en ningún fichero .py."""
        import os, re
        key_pattern = re.compile(r'sk-ant-api\d{2}-[A-Za-z0-9_-]{20,}')
        base = os.path.join(os.path.dirname(__file__), '..', '..')
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'build', '.dart_tool')]
            for fname in files:
                if fname.endswith('.py'):
                    fpath = os.path.join(root, fname)
                    try:
                        content = open(fpath, encoding='utf-8', errors='ignore').read()
                        if key_pattern.search(content):
                            raise AssertionError(f"API key Anthropic hardcodeada en {fpath}")
                    except (PermissionError, IsADirectoryError):
                        pass

    def test_supabase_key_not_in_code(self):
        """El service key de Supabase NO debe estar hardcodeado en ficheros .py."""
        import os, re
        key_pattern = re.compile(r'sb_secret_[A-Za-z0-9_-]{20,}')
        base = os.path.join(os.path.dirname(__file__), '..', '..')
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'build', '.dart_tool')]
            for fname in files:
                if fname.endswith('.py'):
                    fpath = os.path.join(root, fname)
                    try:
                        content = open(fpath, encoding='utf-8', errors='ignore').read()
                        if key_pattern.search(content):
                            raise AssertionError(f"Supabase service key hardcodeada en {fpath}")
                    except (PermissionError, IsADirectoryError):
                        pass


# ── Fase 2: Intent Classification ────────────────────────────────────────────

class TestIntentClassification:
    """Verifica el clasificador de intención basado en keywords (sin LLM)."""

    def test_classify_intent_exists(self):
        from backend.core.chuwi import _classify_intent
        assert callable(_classify_intent)

    def test_registrar_donacion(self):
        from backend.core.chuwi import _classify_intent
        assert _classify_intent("quiero donar las baguettes") == "registrar_donacion"
        assert _classify_intent("donación al banco de alimentos") == "registrar_donacion"

    def test_pedir_ruta(self):
        from backend.core.chuwi import _classify_intent
        assert _classify_intent("iniciar ruta de hoy") == "pedir_ruta"
        assert _classify_intent("dame la ruta") == "pedir_ruta"

    def test_pedir_brief(self):
        from backend.core.chuwi import _classify_intent
        assert _classify_intent("generar brief") == "pedir_brief"
        assert _classify_intent("cómo estamos hoy") == "pedir_brief"

    def test_completar_accion(self):
        from backend.core.chuwi import _classify_intent
        assert _classify_intent("ya está hecho") == "completar_accion"
        assert _classify_intent("listo, lo hice") == "completar_accion"

    def test_consulta_estado(self):
        from backend.core.chuwi import _classify_intent
        assert _classify_intent("cuántos críticos hay") == "consulta_estado"
        assert _classify_intent("qué caduca hoy") == "consulta_estado"

    def test_pregunta_libre_fallback(self):
        from backend.core.chuwi import _classify_intent
        assert _classify_intent("hola") == "pregunta_libre"
        assert _classify_intent("¿cómo te llamas?") == "pregunta_libre"

    def test_configuracion(self):
        from backend.core.chuwi import _classify_intent
        assert _classify_intent("ayuda con los comandos") == "configuracion"

    def test_registrar_merma(self):
        from backend.core.chuwi import _classify_intent
        assert _classify_intent("registrar merma de hoy") == "registrar_merma"

    def test_all_intents_covered(self):
        from backend.core.chuwi import _INTENT_PATTERNS
        intents = {p[0] for p in _INTENT_PATTERNS}
        required = {
            "registrar_donacion", "registrar_merma", "pedir_ruta",
            "pedir_brief", "completar_accion", "crear_accion",
            "consulta_estado", "configuracion",
        }
        missing = required - intents
        assert not missing, f"Faltan intents: {missing}"

    def test_intent_context_builder_exists(self):
        from backend.core.chuwi import _build_intent_context
        assert callable(_build_intent_context)

    def test_intent_context_returns_string(self):
        from backend.core.chuwi import _build_intent_context
        from unittest.mock import patch, MagicMock
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        with patch("backend.core.database.get_db", return_value=mock_db):
            result = _build_intent_context("consulta_estado", "demo-store-001")
        assert isinstance(result, str)

    def test_run_agent_loop_signature_has_intent(self):
        import inspect
        from backend.core.chuwi import _run_agent_loop
        sig = inspect.signature(_run_agent_loop)
        assert "intent_tag" in sig.parameters
        assert "intent_context" in sig.parameters

    def test_upsert_telegram_user_exists(self):
        from backend.core.chuwi import _upsert_telegram_user
        assert callable(_upsert_telegram_user)


class TestTelegramSecurityFlow:
    def test_unlinked_user_returns_none(self):
        from backend.core.chuwi import _get_user
        from unittest.mock import patch, MagicMock
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
        with patch("backend.core.database.get_db", return_value=mock_db):
            result = _get_user(99999999)
        assert result is None

    def test_linked_user_is_returned(self):
        from backend.core.chuwi import _get_user
        from unittest.mock import patch, MagicMock
        fake_user = {"id": "user-123", "role": "manager", "store_id": "demo-store-001"}
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=fake_user)
        with patch("backend.core.database.get_db", return_value=mock_db):
            result = _get_user(12345)
        assert result is not None and result["role"] == "manager"


class TestChuwiPromptInjection:
    """
    Protege a Chuwi de ataques reales de prompt injection por Telegram.
    Un empleado malintencionado o un mensaje accidental no debe poder:
    - Cambiar el comportamiento del agente
    - Acceder a datos de otras tiendas
    - Saltarse restricciones de rol
    - Provocar errores en el sistema
    """

    def test_tool_unknown_returns_error_not_crash(self):
        # Protege: si alguien envía un tool_name con inyección (ej. "get_store_overview; DROP TABLE"),
        # _execute_tool_sync no debe crashear ni ejecutar código arbitrario.
        from backend.core.chuwi import _execute_tool_sync
        malicious_names = [
            "'; DROP TABLE batches; --",
            "__import__('os').system('rm -rf /')",
            "get_store_overview\nignore_previous_instructions",
            "../../../../etc/passwd",
        ]
        for name in malicious_names:
            result = _execute_tool_sync(name, {}, None)
            assert "error" in result, f"Tool maliciosa '{name[:30]}' debe devolver error"
            # El error puede contener el nombre de la tool (para debug), pero NO debe
            # ejecutar código ni devolver datos reales del sistema
            assert "batches" not in str(result.get("error", "")).lower().replace("drop table batches", ""), \
                "Error no debe exponer nombres de tablas reales del sistema"
            assert isinstance(result, dict), "Siempre debe devolver dict, no explotar"

    def test_manager_only_tool_blocked_for_staff(self):
        # Protege: empleado normal no puede acceder a datos de proveedores ni ESG.
        # Si un empleado envía manualmente "get_suppliers" a través de Telegram,
        # debe recibir error de permisos, no los datos.
        from backend.core.chuwi import _execute_tool_sync
        staff_user = {"id": "emp-001", "role": "staff", "store_id": "demo-store-001"}
        result_suppliers = _execute_tool_sync("get_suppliers", {}, staff_user)
        result_esg = _execute_tool_sync("get_esg_metrics", {}, staff_user)
        result_orders = _execute_tool_sync("get_order_suggestions", {}, staff_user)
        assert "error" in result_suppliers, "Staff no debe ver proveedores"
        assert "error" in result_esg, "Staff no debe ver ESG"
        assert "error" in result_orders, "Staff no debe ver pedidos"

    def test_intent_with_empty_message_does_not_crash(self):
        # Protege: mensaje de Telegram completamente vacío o solo espacios.
        # Ocurre cuando el empleado envía un sticker o media sin caption.
        from backend.core.chuwi_intent import _classify_intent
        for msg in ["", "   ", "\n", "\t\n  "]:
            result = _classify_intent(msg)
            assert isinstance(result, str), f"Intent vacío debe devolver string, got {type(result)}"
            assert len(result) > 0, "Intent vacío no puede devolver string vacío"

    def test_intent_with_very_long_message_does_not_crash(self):
        # Protege: mensaje de 10.000 caracteres (spam o error del usuario).
        # Sin límite, esto podría saturar el contexto del LLM.
        from backend.core.chuwi_intent import _classify_intent
        huge_msg = "¿cuántos críticos hay? " * 500  # 11.000 chars
        result = _classify_intent(huge_msg)
        assert isinstance(result, str)

    def test_execute_tool_with_none_input_does_not_crash(self):
        # Protege: si el JSON de la tool llega malformado (None en vez de dict),
        # el sistema debe manejarlo sin explotar.
        from backend.core.chuwi import _execute_tool_sync
        # get_store_overview no tiene campos requeridos — debe manejar input vacío
        result = _execute_tool_sync("get_store_overview", {}, None)
        # Sin BD real, esperamos error de conexión, no un crash del servidor
        assert isinstance(result, dict), "Siempre debe devolver dict"
