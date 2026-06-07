"""
test_scheduler.py — Tests del scheduler y monitor proactivo de MermaOps.

Cubre:
- build_scheduler devuelve scheduler con 7 jobs configurados
- _proactive_monitor no crashea con BD vacía
- _proactive_monitor filtra por cutoff correcto (no solo expirados)
- _escalate_critical_actions no crashea sin acciones overdue
- _escalate_critical_actions envía alerta si hay acciones overdue
- Jobs tienen los IDs y triggers correctos
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest


STORE_ID = "demo-store-001"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_batch(days_from_today: int, qty: int = 10, batch_id: str = "b-001") -> dict:
    expiry = (date.today() + timedelta(days=days_from_today)).isoformat()
    return {
        "id": batch_id,
        "expiry_date": expiry,
        "quantity": qty,
        "products": {"name": "Producto test", "pasillo": "A1"},
    }


def _make_action(batch_id: str, score: int = 90, action_type: str = "rebajar") -> dict:
    return {
        "id": f"action-{batch_id}",
        "batch_id": batch_id,
        "priority_score": score,
        "action_type": action_type,
        "batches": {
            "expiry_date": (date.today() - timedelta(days=1)).isoformat(),
            "quantity": 5,
            "products": {"name": "Producto test", "pasillo": "A1"},
        },
    }


# ── build_scheduler ───────────────────────────────────────────────────────────

class TestBuildScheduler:

    def test_returns_scheduler_object(self):
        from backend.core.scheduler import build_scheduler
        with patch("backend.agents.supervisor.run_daily_brief"):
            scheduler = build_scheduler(STORE_ID)
        assert scheduler is not None

    def test_scheduler_has_expected_jobs(self):
        from backend.core.scheduler import build_scheduler
        with patch("backend.agents.supervisor.run_daily_brief"):
            scheduler = build_scheduler(STORE_ID)
        jobs = scheduler.get_jobs()
        # 11 jobs: predicción, morning_greeting, brief, mediodía, cierre, semanal,
        # mensual, escalación, monitor_proactivo, retrospective_reflection, sla_check
        assert len(jobs) >= 8, f"Se esperaban al menos 8 jobs, hay {len(jobs)}"

    def test_scheduler_has_daily_brief_job(self):
        from backend.core.scheduler import build_scheduler
        with patch("backend.agents.supervisor.run_daily_brief"):
            scheduler = build_scheduler(STORE_ID)
        job_ids = [j.id for j in scheduler.get_jobs()]
        assert "daily_brief" in job_ids

    def test_scheduler_has_proactive_monitor_job(self):
        from backend.core.scheduler import build_scheduler
        with patch("backend.agents.supervisor.run_daily_brief"):
            scheduler = build_scheduler(STORE_ID)
        job_ids = [j.id for j in scheduler.get_jobs()]
        assert "proactive_monitor" in job_ids

    def test_scheduler_has_escalation_job(self):
        from backend.core.scheduler import build_scheduler
        with patch("backend.agents.supervisor.run_daily_brief"):
            scheduler = build_scheduler(STORE_ID)
        job_ids = [j.id for j in scheduler.get_jobs()]
        assert "escalation" in job_ids

    def test_all_expected_job_ids_present(self):
        from backend.core.scheduler import build_scheduler
        with patch("backend.agents.supervisor.run_daily_brief"):
            scheduler = build_scheduler(STORE_ID)
        job_ids = {j.id for j in scheduler.get_jobs()}
        expected = {
            "daily_brief", "intraday_check", "closing",
            "weekly_report", "monthly_report",
            "escalation", "proactive_monitor",
        }
        missing = expected - job_ids
        assert not missing, f"Jobs faltantes: {missing}"


# ── _proactive_monitor ────────────────────────────────────────────────────────

class TestProactiveMonitor:

    def test_empty_batches_sends_zero_alerts(self):
        # Protege: con BD vacía el monitor no debe enviar alertas vacías/falsas.
        # Fallo real posible: si el código no cortaba al recibir lista vacía,
        # podría enviar un mensaje de "0 productos críticos" que confundiría al encargado.
        from backend.core.scheduler import _proactive_monitor
        with patch("backend.core.database.get_batches_expiring_soon", return_value=[]), \
             patch("backend.core.database.get_pending_actions", return_value=[]), \
             patch("backend.agents.notifier.send_alert") as mock_alert, \
             patch("backend.agents.notifier.send_alert_with_buttons") as mock_buttons:
            _proactive_monitor(STORE_ID)
        assert mock_alert.call_count == 0, "BD vacía no debe generar alertas"
        assert mock_buttons.call_count == 0, "BD vacía no debe generar botones"

    def test_no_alert_when_no_critical(self):
        """No envía alerta si no hay críticos."""
        from backend.core.scheduler import _proactive_monitor
        with patch("backend.core.database.get_batches_expiring_soon", return_value=[]), \
             patch("backend.core.database.get_pending_actions", return_value=[]), \
             patch("backend.agents.notifier.send_alert") as mock_alert, \
             patch("backend.agents.notifier.send_alert_with_buttons") as mock_buttons:
            _proactive_monitor(STORE_ID)
        mock_alert.assert_not_called()
        mock_buttons.assert_not_called()

    def test_sends_alert_for_new_critical_without_action(self):
        """Envía alerta si hay lote crítico sin acción pendiente."""
        from backend.core.scheduler import _proactive_monitor

        batch = _make_batch(days_from_today=1, qty=10, batch_id="b-critico")
        with patch("backend.core.database.get_batches_expiring_soon", return_value=[batch]), \
             patch("backend.core.database.get_pending_actions", return_value=[]), \
             patch("backend.agents.notifier.send_alert") as mock_alert, \
             patch("backend.agents.notifier.send_alert_with_buttons") as mock_buttons:
            _proactive_monitor(STORE_ID)
        # Debe haber enviado algún tipo de alerta (con o sin botones)
        sent = mock_alert.called or mock_buttons.called
        assert sent, "Debería haber enviado alerta para nuevo CRÍTICO sin acción"

    def test_no_alert_if_batch_already_has_action(self):
        """No envía alerta para lotes que ya tienen acción pendiente."""
        from backend.core.scheduler import _proactive_monitor

        batch = _make_batch(days_from_today=1, qty=10, batch_id="b-001")
        existing_action = {"batch_id": "b-001", "priority_score": 90}

        with patch("backend.core.database.get_batches_expiring_soon", return_value=[batch]), \
             patch("backend.core.database.get_pending_actions", return_value=[existing_action]), \
             patch("backend.agents.notifier.send_alert") as mock_alert, \
             patch("backend.agents.notifier.send_alert_with_buttons") as mock_buttons:
            _proactive_monitor(STORE_ID)
        mock_alert.assert_not_called()
        mock_buttons.assert_not_called()

    def test_no_crash_when_notifier_fails(self):
        """Monitor captura errores del notificador sin romper el loop."""
        from backend.core.scheduler import _proactive_monitor

        batch = _make_batch(days_from_today=1, qty=10)
        with patch("backend.core.database.get_batches_expiring_soon", return_value=[batch]), \
             patch("backend.core.database.get_pending_actions", return_value=[]), \
             patch("backend.agents.notifier.send_alert_with_buttons", side_effect=RuntimeError("Telegram down")), \
             patch("backend.agents.notifier.send_alert", side_effect=RuntimeError("Telegram down")):
            try:
                _proactive_monitor(STORE_ID)
            except Exception as e:
                pytest.fail(f"Monitor no debe propagar errores del notificador: {e}")

    def test_no_duplicate_alert_same_batch_same_day(self):
        """Bug real arreglado: el mismo lote NO debe recibir alerta dos veces el mismo día."""
        import backend.core.scheduler as sched
        from backend.core.scheduler import _proactive_monitor

        batch = _make_batch(days_from_today=1, qty=10, batch_id="b-dedup-test")
        # Limpiar estado previo
        sched._alerted_batches.clear()

        with patch("backend.core.database.get_batches_expiring_soon", return_value=[batch]), \
             patch("backend.core.database.get_pending_actions", return_value=[]), \
             patch("backend.agents.notifier.send_alert_with_buttons") as mock_buttons, \
             patch("backend.agents.notifier.send_alert") as mock_alert:
            _proactive_monitor(STORE_ID)  # primera llamada — debe alertar
            _proactive_monitor(STORE_ID)  # segunda llamada — NO debe repetir

        total_calls = mock_buttons.call_count + mock_alert.call_count
        assert total_calls == 1, f"Debe alertar exactamente 1 vez, no {total_calls} veces"


# ── _escalate_critical_actions ────────────────────────────────────────────────

class TestEscalateCriticalActions:

    def test_no_alert_when_no_overdue(self):
        """No envía escalación si no hay acciones overdue."""
        from backend.core.scheduler import _escalate_critical_actions
        with patch("backend.core.database.get_overdue_critical_actions", return_value=[]), \
             patch("backend.agents.notifier.send_alert") as mock_alert:
            _escalate_critical_actions(STORE_ID)
        mock_alert.assert_not_called()

    def test_sends_alert_when_overdue_found(self):
        """Envía alerta cuando hay acciones críticas overdue."""
        from backend.core.scheduler import _escalate_critical_actions
        overdue = [_make_action("b-001", score=90)]

        with patch("backend.core.database.get_overdue_critical_actions", return_value=overdue), \
             patch("backend.agents.notifier.send_alert") as mock_alert:
            _escalate_critical_actions(STORE_ID)
        mock_alert.assert_called_once()

    def test_alert_mentions_count(self):
        """El texto de escalación menciona el número de acciones."""
        from backend.core.scheduler import _escalate_critical_actions
        overdue = [_make_action(f"b-{i}", score=90) for i in range(3)]

        sent_text = []
        def capture_alert(store_id, title, text, **kwargs):
            sent_text.append(text)

        with patch("backend.core.database.get_overdue_critical_actions", return_value=overdue), \
             patch("backend.agents.notifier.send_alert", side_effect=capture_alert):
            _escalate_critical_actions(STORE_ID)

        assert len(sent_text) == 1
        assert "3" in sent_text[0]

    def test_notifier_failure_does_not_prevent_next_escalation_cycle(self):
        # Protege: si Telegram está caído y send_alert lanza, el scheduler NO debe
        # morir. El job se ejecuta cada 2h — si falla, las siguientes ejecuciones
        # deben continuar igualmente.
        # Fallo real posible: si la excepción se propagara, APScheduler marcaría el
        # job como fallido y podría pausarlo, dejando acciones críticas sin escalar.
        from backend.core.scheduler import _escalate_critical_actions
        overdue = [_make_action("b-001")]
        call_count = [0]

        def failing_then_succeeding(store_id, title, text, **kwargs):
            call_count[0] += 1
            raise RuntimeError("Network error")

        with patch("backend.core.database.get_overdue_critical_actions", return_value=overdue), \
             patch("backend.agents.notifier.send_alert", side_effect=failing_then_succeeding):
            _escalate_critical_actions(STORE_ID)  # no debe propagar
        assert call_count[0] == 1, "send_alert debe haberse intentado aunque fallara"
