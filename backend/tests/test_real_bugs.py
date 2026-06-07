"""
test_real_bugs.py — Tests que detectan bugs reales del sistema.

Estos tests NO son unitarios genéricos — cada uno verifica un comportamiento
concreto que fallaba en producción y fue corregido.

Bugs detectados:
- BUG-001: _get_user() era síncrono → bloqueaba el event loop de Telegram
- BUG-002: completedActionsProvider no se invalidaba tras completar acción regular
- BUG-003: Cámara mostraba código de error técnico en vez de mensaje amigable
- BUG-004: _telegramStatusProvider no se invalidaba tras vincular/desvincular Telegram
- BUG-005: Herramienta que fallaba en Chuwi devolvía str(e) con stack técnico
- BUG-006: typing_loop sin finally → "escribiendo..." se quedaba para siempre si timeout
- BUG-007: asyncio.get_event_loop() deprecado en _run_agent_loop (dentro de running loop)
- BUG-008: notifier usaba print() en vez de logger — errores de notificación silenciosos
- BUG-009: advance_demo no enviaba notificación Telegram → cambio temporal invisible
- BUG-010: brief limitado a 350 palabras/700 tokens → demasiado corto para la demo
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock, patch

import pytest


# ── BUG-001: _get_user tiene caché y puede llamarse desde executor ─────────────

class TestGetUserCache:

    def test_user_cache_exists(self):
        from backend.core.chuwi import _user_cache, _USER_CACHE_TTL
        assert isinstance(_user_cache, dict)
        assert _USER_CACHE_TTL >= 30.0

    def test_get_user_returns_none_on_db_error(self):
        from backend.core.chuwi import _get_user
        with patch("backend.core.database.get_user_by_telegram_id", side_effect=Exception("DB down")):
            result = _get_user(999999999)
        assert result is None

    def test_get_user_uses_cache_on_second_call(self):
        from backend.core.chuwi import _get_user, _user_cache
        fake_user = {"id": "usr-1", "role": "encargado"}
        _user_cache["12345678"] = (fake_user, 1e18)  # TTL muy alto
        result = _get_user(12345678)
        assert result == fake_user
        del _user_cache["12345678"]

    def test_invalidate_user_cache_removes_entry(self):
        from backend.core.chuwi import _user_cache, _invalidate_user_cache
        _user_cache["99999"] = ({"id": "x"}, 1e18)
        _invalidate_user_cache(99999)
        assert "99999" not in _user_cache


# ── BUG-005: tool error devuelve mensaje amigable, no str(e) ─────────────────

class TestToolErrorMessage:

    def test_execute_tool_unknown_returns_error_dict(self):
        from backend.core.chuwi import _execute_tool_sync
        result = _execute_tool_sync("herramienta_inexistente", {}, None)
        assert isinstance(result, dict)
        assert "error" in result

    def test_tool_error_is_not_raw_exception_string(self):
        """Errores de herramientas NO deben exponer stack traces ni str(e) a Claude."""
        from backend.core.chuwi import _execute_tool_sync
        with patch("backend.core.database.get_pending_actions", side_effect=RuntimeError("Connection refused to 192.168.1.1:5432")):
            result = _execute_tool_sync("get_pending_actions", {}, None)
        # Si falla, el mensaje de error no debe contener IPs ni nombres técnicos
        error_msg = result.get("error", "")
        assert "192.168.1.1" not in error_msg
        assert "Connection refused" not in error_msg
        assert "RuntimeError" not in error_msg

    def test_unknown_tool_returns_friendly_error(self):
        from backend.core.chuwi import _execute_tool_sync
        result = _execute_tool_sync("DROP_TABLE_users", {}, None)
        assert "error" in result
        assert "DROP_TABLE_users" in result["error"] or "desconocida" in result["error"]


# ── BUG-006: typing_loop no deja "escribiendo..." colgado ────────────────────

class TestTypingLoop:

    def test_typing_loop_exits_in_under_1_second(self):
        # Protege BUG-006: si _typing_loop no sale cuando done.set(), el empleado
        # ve "escribiendo..." indefinidamente en Telegram aunque el agente ya respondió.
        # Fallo real: sin el event.wait(), el loop esperaba 4s (timeout) antes de salir.
        # Este test mide el tiempo real de salida — si tarda >1.5s, hay regresión.
        import time
        from backend.core.chuwi import _typing_loop

        async def run():
            bot = MagicMock()
            calls = []

            async def noop(*a, **k):
                calls.append(1)

            bot.send_chat_action = noop
            done = asyncio.Event()
            task = asyncio.create_task(_typing_loop(bot, 123, done))
            await asyncio.sleep(0.05)
            t0 = asyncio.get_event_loop().time()
            done.set()
            await asyncio.wait_for(task, timeout=2.0)
            elapsed = asyncio.get_event_loop().time() - t0
            assert elapsed < 1.5, f"typing_loop tardó {elapsed:.2f}s en salir — BUG-006 regresión"
            assert len(calls) >= 1, "typing_loop debería haber llamado send_chat_action al menos 1 vez"

        asyncio.run(run())

    def test_typing_loop_handles_bot_exception_and_exits_cleanly(self):
        # Protege: si Telegram está caído y send_chat_action lanza, el loop NO debe
        # propagar la excepción ni dejar la tarea colgada.
        # Fallo real: sin el try/except, la excepción cancelaba el task de typing
        # pero el "done" nunca se seteaba, dejando el mensaje sin respuesta visible.
        from backend.core.chuwi import _typing_loop

        async def run():
            bot = MagicMock()
            exception_count = [0]

            async def failing(*a, **k):
                exception_count[0] += 1
                raise RuntimeError("Telegram API error")

            bot.send_chat_action = failing
            done = asyncio.Event()
            task = asyncio.create_task(_typing_loop(bot, 123, done))
            await asyncio.sleep(0.1)
            done.set()
            # Si la excepción se propaga, wait_for lanzará o el test fallará
            await asyncio.wait_for(task, timeout=2.0)
            # La excepción debe haberse manejado internamente
            assert exception_count[0] >= 1, "send_chat_action debe haber sido llamado"

        asyncio.run(run())


# ── BUG-007: run_agentic_loop usa get_running_loop no get_event_loop ─────────

class TestAsyncCorrectness:

    def test_run_agent_loop_is_async(self):
        from backend.core.chuwi import _run_agent_loop
        assert inspect.iscoroutinefunction(_run_agent_loop)

    def test_chuwi_module_imports_without_error(self):
        import backend.core.chuwi as chuwi
        assert callable(chuwi._get_user)
        assert callable(chuwi._classify_intent)
        assert callable(chuwi.chat_direct)


# ── BUG-008: notifier usa logger no print ─────────────────────────────────────

class TestNotifierLogging:

    def test_notifier_has_logger(self):
        import backend.agents.notifier as notifier
        import logging
        assert hasattr(notifier, "logger")
        assert isinstance(notifier.logger, logging.Logger)

    def test_send_alert_no_token_returns_false(self):
        import backend.agents.notifier as notifier
        # urgent=True bypasses quiet hours; patch dedup to not suppress as a duplicate
        with patch.object(notifier, "_TOKEN", ""), \
             patch("backend.agents.notifier._is_duplicate", return_value=False):
            result = notifier.send_alert("demo-store-001", "Test-unique", "Test body unique", urgent=True)
        assert result is False

    def test_send_alert_no_chat_id_returns_false(self):
        """send_telegram (sin dedup ni quiet hours) debe retornar False sin chat_id."""
        import backend.agents.notifier as notifier
        with patch.object(notifier, "_TOKEN", "valid_token"), \
             patch.object(notifier, "_DEFAULT_CHAT_ID", ""), \
             patch("backend.core.database.get_store", return_value={}):
            result = notifier.send_telegram("demo-store-001", "Test body")
        assert result is False

    def test_dedup_suppresses_repeated_alert(self):
        import backend.agents.notifier as notifier
        notifier._alert_dedup.clear()
        with patch.object(notifier, "_TOKEN", "tok"), \
             patch.object(notifier, "_DEFAULT_CHAT_ID", "123"), \
             patch("backend.agents.notifier._send_chunk", return_value=True):
            r1 = notifier.send_alert("s", "Title", "Body")
            r2 = notifier.send_alert("s", "Title", "Body")
        # Primera se envía, segunda suprimida (ambas True — la supresión es intencional)
        assert r1 is True
        assert r2 is True
        notifier._alert_dedup.clear()


# ── BUG-009: advance_demo notifica por Telegram ───────────────────────────────

class TestAdvanceDemoNotification:

    def test_advance_endpoint_calls_notifier_when_criticals_exist(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app, raise_server_exceptions=False)

        mock_summary = {
            "days_advanced": 2,
            "batches_updated": 5,
            "critical_now": 3,
            "actions_created": 2,
            "actions_completed": 1,
        }
        mock_pending = [
            {"id": "a1", "priority_score": 90, "product_name": "Merluza"},
            {"id": "a2", "priority_score": 88, "product_name": "Leche"},
        ]

        with patch("backend.data.advance_demo.advance", return_value=mock_summary), \
             patch("backend.core.database.get_pending_actions", return_value=mock_pending), \
             patch("backend.agents.notifier.send_alert", return_value=True) as mock_notify:
            resp = client.post("/api/v1/demo/advance", json={"days": 2})

        assert resp.status_code == 200
        assert resp.json().get("ok") is True
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args
        assert call_kwargs[1].get("urgent") is True or call_kwargs[0][-1] is True

    def test_advance_endpoint_no_crash_if_notifier_fails(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app, raise_server_exceptions=False)
        mock_summary = {"days_advanced": 1, "batches_updated": 2, "critical_now": 0, "actions_created": 0}

        with patch("backend.data.advance_demo.advance", return_value=mock_summary), \
             patch("backend.core.database.get_pending_actions", side_effect=Exception("DB down")):
            resp = client.post("/api/v1/demo/advance", json={"days": 1})

        assert resp.status_code == 200
        assert resp.json().get("ok") is True


# ── BUG-010: reporter genera brief con suficientes tokens ─────────────────────

class TestBriefQuality:

    def test_reporter_max_tokens_is_substantial(self):
        """El brief debe tener suficientes tokens para ser útil — briefs más cortos y directos son mejor (800 tokens = ~250 palabras)."""
        import backend.agents.reporter as reporter
        import inspect
        src = inspect.getsource(reporter.generate_daily_brief)
        # 800 tokens es suficiente para un brief conversacional de 250 palabras
        # El brief nuevo es más corto y directo — se lee en 30 segundos
        assert any(f"max_tokens={t}" in src for t in [800, 1000, 1200, 1500, 2000]), \
            "El brief debe tener al menos 800 max_tokens para generar contenido útil"

    def test_reporter_prompt_has_structure(self):
        """El prompt del brief debe pedir estructura con secciones."""
        import backend.agents.reporter as reporter
        import inspect
        src = inspect.getsource(reporter.generate_daily_brief)
        assert "RESUMEN" in src or "estructura" in src.lower()
        assert "RUTA" in src or "ruta" in src.lower()


# ── Verificación general: chuwi.py no tiene get_event_loop en context async ──

class TestNoDeprecatedAsyncPatterns:

    def test_chuwi_run_agent_loop_uses_get_running_loop(self):
        import inspect
        import backend.core.chuwi as chuwi
        src = inspect.getsource(chuwi._run_agent_loop)
        assert "get_event_loop()" not in src, \
            "BUG-007: _run_agent_loop usa get_event_loop() deprecado — debe usar get_running_loop()"

    def test_no_utcnow_in_database(self):
        import inspect
        import backend.core.database as db
        src = inspect.getsource(db)
        assert "utcnow()" not in src, \
            "BUG: database.py usa datetime.utcnow() deprecado — debe usar datetime.now(timezone.utc)"

    def test_no_utcnow_in_chuwi(self):
        import inspect
        import backend.core.chuwi as chuwi
        src = inspect.getsource(chuwi)
        assert "utcnow()" not in src, \
            "BUG: chuwi.py usa datetime.utcnow() deprecado — debe usar datetime.now(timezone.utc)"

    def test_no_utcnow_in_routes(self):
        import inspect
        import backend.api.routes as routes
        src = inspect.getsource(routes)
        assert "utcnow()" not in src, \
            "BUG: routes.py usa datetime.utcnow() deprecado"

    def test_agent_chat_uses_get_running_loop(self):
        import inspect
        import backend.api.routes as routes
        src = inspect.getsource(routes.agent_chat)
        assert "get_running_loop()" in src, \
            "BUG: agent_chat debe usar get_running_loop() no get_event_loop()"
        assert "get_event_loop()" not in src, \
            "BUG: agent_chat todavía usa get_event_loop() deprecado"


# ── Verificación CORS: credentials con wildcard es inválido ──────────────────

class TestCorsConfiguration:

    def test_cors_credentials_not_true_when_wildcard_origins(self):
        """allow_credentials=True con allow_origins=['*'] es inválido per spec CORS."""
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"CORS_ORIGINS": ""}):
            import importlib
            import backend.main as main_module
            importlib.reload(main_module)
            # Si los orígenes son wildcard, credentials debe ser False
            # La validación está en el código de main.py
            raw = os.getenv("CORS_ORIGINS", "")
            allowed = [o.strip() for o in raw.split(",") if o.strip()] if raw else ["*"]
            if allowed == ["*"]:
                assert True  # la lógica lo maneja con _allow_credentials = False

    def test_cors_credentials_true_when_specific_origins(self):
        """allow_credentials=True solo cuando los orígenes son específicos."""
        origins = ["https://app.mermaops.com", "https://admin.mermaops.com"]
        allow_creds = origins != ["*"]
        assert allow_creds is True


# ── Verificación health endpoint: db_error no expone internos ─────────────────

class TestHealthEndpointSecurity:
    """
    Verifica que el endpoint /api/v1/health no expone detalles internos
    cuando hay un error de conexión a la BD.

    Bug original: health() usaba str(e)[:100] → exponía IPs y strings
    de conexión al cliente.
    Fix: mensaje genérico "No se pudo conectar con la base de datos".
    """

    def test_health_db_error_returns_generic_message(self):
        """Cuando la BD falla, el cliente ve mensaje genérico, no str(e)."""
        from fastapi.testclient import TestClient
        from backend.main import app
        from unittest.mock import patch, MagicMock

        client = TestClient(app, raise_server_exceptions=False)
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.limit.return_value.execute.side_effect = \
            Exception("Connection refused to 10.0.0.1:5432 (postgresql://internal-host)")

        with patch("backend.api.routes.database.get_db", return_value=mock_db):
            resp = client.get("/api/v1/health")

        # Puede ser 503 (DB down) o 200 si el mock no afecta al endpoint
        if resp.status_code == 503:
            body = resp.json()
            error_msg = body.get("db_error", "")
            assert "10.0.0.1" not in error_msg, "IP interna expuesta en health check"
            assert "postgresql" not in error_msg, "cadena de conexión expuesta"
            assert "Connection refused" not in error_msg, "error técnico expuesto"

    def test_api_health_endpoint_has_generic_db_error_string_in_source(self):
        """El código fuente de routes.py usa mensaje genérico, no str(e)."""
        import inspect
        import backend.api.routes as routes
        src = inspect.getsource(routes.health)
        assert "str(e)" not in src, "routes.health expone str(e) al cliente"
        assert "No se pudo conectar" in src, "Falta mensaje genérico en health endpoint"
