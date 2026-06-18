"""
Tests para el Notificador — alertas Telegram, deduplicación y horario silencio.
Sin red real: todos los tests mockean requests.post y la BD.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import time
import pytest

import backend.agents.notifier as notifier


STORE_ID = "demo-store-001"


# ── Deduplicación ─────────────────────────────────────────────────────────────

class TestDeduplication:
    def setup_method(self):
        notifier._alert_dedup.clear()

    def test_first_alert_not_duplicate(self):
        key = notifier._dedup_key(STORE_ID, "Crítico", "Baguette caduca hoy")
        assert notifier._is_duplicate(key) is False

    def test_same_alert_within_window_is_duplicate(self):
        key = notifier._dedup_key(STORE_ID, "Crítico", "Baguette caduca hoy")
        notifier._is_duplicate(key)  # primera vez — registra
        assert notifier._is_duplicate(key) is True  # segunda — duplicado

    def test_different_alerts_are_not_duplicates(self):
        key1 = notifier._dedup_key(STORE_ID, "Crítico", "Baguette caduca hoy")
        key2 = notifier._dedup_key(STORE_ID, "Crítico", "Yogur caduca hoy")
        notifier._is_duplicate(key1)
        assert notifier._is_duplicate(key2) is False

    def test_dedup_key_is_deterministic(self):
        k1 = notifier._dedup_key(STORE_ID, "T", "B")
        k2 = notifier._dedup_key(STORE_ID, "T", "B")
        assert k1 == k2

    def test_dedup_key_different_stores(self):
        k1 = notifier._dedup_key("store-001", "T", "B")
        k2 = notifier._dedup_key("store-002", "T", "B")
        assert k1 != k2


# ── Horario de silencio ───────────────────────────────────────────────────────

class TestQuietHours:
    def test_hour_22_is_quiet(self):
        mock_dt = MagicMock()
        mock_dt.now.return_value.hour = 22
        with patch("backend.agents.notifier._datetime", mock_dt):
            assert notifier._is_quiet_hours() is True

    def test_hour_3_is_quiet(self):
        mock_dt = MagicMock()
        mock_dt.now.return_value.hour = 3
        with patch("backend.agents.notifier._datetime", mock_dt):
            assert notifier._is_quiet_hours() is True

    def test_hour_10_is_not_quiet_during_work_hours(self):
        # Hora 10 = horario laboral (8-21h) → alertas SIEMPRE pasan para no dejar callado a Chuwi
        mock_dt = MagicMock()
        mock_dt.now.return_value.hour = 10
        mock_dt.now.return_value.minute = 30
        with patch("backend.agents.notifier._datetime", mock_dt):
            assert notifier._is_quiet_hours() is False  # en horario laboral nunca silenciar

    def test_hour_10_urgent_still_sends(self):
        # Alertas urgentes SIEMPRE se envían, incluso en hora pico de caja
        mock_dt = MagicMock()
        mock_dt.now.return_value.hour = 10
        mock_dt.now.return_value.minute = 30
        with patch("backend.agents.notifier._datetime", mock_dt):
            assert notifier._is_quiet_hours(urgent=True) is False

    def test_hour_7_is_not_quiet(self):
        mock_dt = MagicMock()
        mock_dt.now.return_value.hour = 7
        mock_dt.now.return_value.minute = 0
        with patch("backend.agents.notifier._datetime", mock_dt):
            assert notifier._is_quiet_hours() is False


# ── send_telegram ─────────────────────────────────────────────────────────────

class TestSendTelegram:
    def test_returns_false_when_no_token(self):
        with patch.object(notifier, "_TOKEN", ""):
            result = notifier.send_telegram(STORE_ID, "Hola mundo")
        assert result is False

    def test_calls_requests_post_with_token(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.object(notifier, "_TOKEN", "fake-token-123"), \
             patch.object(notifier, "_DEFAULT_CHAT_ID", "chat-001"), \
             patch("backend.agents.notifier.get_store", return_value=None), \
             patch("backend.agents.notifier.requests.post", return_value=mock_resp) as mock_post:
            result = notifier.send_telegram(STORE_ID, "Hola mundo")
        mock_post.assert_called()
        assert result is True

    def test_returns_false_on_network_error(self):
        with patch.object(notifier, "_TOKEN", "fake-token-123"), \
             patch.object(notifier, "_DEFAULT_CHAT_ID", "chat-001"), \
             patch("backend.agents.notifier.get_store", return_value=None), \
             patch("backend.agents.notifier.requests.post",
                   side_effect=Exception("network error")):
            result = notifier.send_telegram(STORE_ID, "Hola")
        assert result is False

    def test_long_message_chunked(self):
        """Mensajes >4096 chars con párrafos se envían en múltiples chunks."""
        # El chunking divide por líneas — necesitamos párrafos para que divida
        long_text = "\n".join(["Línea de alerta " + str(i) + ": " + "X" * 100 for i in range(50)])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.object(notifier, "_TOKEN", "fake-token-123"), \
             patch.object(notifier, "_DEFAULT_CHAT_ID", "chat-001"), \
             patch("backend.agents.notifier.get_store", return_value=None), \
             patch("backend.agents.notifier.requests.post", return_value=mock_resp) as mock_post:
            notifier.send_telegram(STORE_ID, long_text)
        # Debe haberse llamado al menos 2 veces (chunks)
        assert mock_post.call_count >= 2


# ── send_alert ────────────────────────────────────────────────────────────────

class TestSendAlert:
    def setup_method(self):
        notifier._alert_dedup.clear()

    def test_duplicate_alert_not_sent_twice(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_dt = MagicMock()
        mock_dt.now.return_value.hour = 14  # horario laboral — no silencio
        with patch.object(notifier, "_TOKEN", "fake-token"), \
             patch.object(notifier, "_DEFAULT_CHAT_ID", "chat-001"), \
             patch("backend.agents.notifier.get_store", return_value=None), \
             patch("backend.agents.notifier._datetime", mock_dt), \
             patch("backend.agents.notifier.requests.post", return_value=mock_resp) as mock_post:
            notifier.send_alert(STORE_ID, "Crítico", "Baguette")
            notifier.send_alert(STORE_ID, "Crítico", "Baguette")  # duplicado
        # El segundo no debe generar una nueva llamada HTTP
        assert mock_post.call_count == 1

    def test_urgent_alert_sent_even_in_quiet_hours(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_dt = MagicMock()
        mock_dt.now.return_value.hour = 23  # hora silencio
        with patch.object(notifier, "_TOKEN", "fake-token"), \
             patch.object(notifier, "_DEFAULT_CHAT_ID", "chat-001"), \
             patch("backend.agents.notifier.get_store", return_value=None), \
             patch("backend.agents.notifier._datetime", mock_dt), \
             patch("backend.agents.notifier.requests.post", return_value=mock_resp) as mock_post:
            notifier.send_alert(STORE_ID, "URGENTE", "Retirar inmediatamente", urgent=True)
        mock_post.assert_called()
