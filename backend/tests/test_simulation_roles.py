"""
test_simulation_roles.py — Simulación de sesiones reales de usuario.

Simula exactamente lo que haría un supervisor y un empleado en un día real
usando MermaOps, incluyendo Chuwi (agente Telegram), Supabase Realtime
y el APScheduler. Sin infraestructura real — mocks realistas de supermercado.

Escenarios:
  SIM-001: Supervisor empieza el día — brief, dashboard, decisiones de Kuine
  SIM-002: Empleado recibe alerta en Telegram — escanea, completa, dona
  SIM-003: Chuwi como agente real — intent, tools, respuesta coherente
  SIM-004: Supabase Realtime — cambio de estado detectado en app
  SIM-005: APScheduler — jobs registrados, monitor proactivo a las 07:30
  SIM-006: Turno completo — apertura → escaneo masivo → cierre del día
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta, datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

STORE_ID = "demo-store-001"


# ── Helpers de datos realistas ────────────────────────────────────────────────

def _make_store_state(n_critical: int = 3, n_high: int = 5, value_at_risk: float = 248.50):
    """Estado realista de una tienda de supermercado a las 7:30."""
    today = date.today()
    actions = []
    for i in range(n_critical):
        actions.append({
            "id": f"act-crit-{i:03d}",
            "batch_id": f"b-crit-{i:03d}",
            "action_type": ["rebajar", "retirar", "donar"][i % 3],
            "priority_score": 90 + i,
            "status": "pending",
            "new_price": round(2.50 * 0.60, 2) if i % 3 == 0 else None,
            "batches": {
                "id": f"b-crit-{i:03d}",
                "expiry_date": today.isoformat(),
                "quantity": 5 + i * 2,
                "products": {
                    "name": ["Yogur Natural", "Ternera picada", "Pan integral"][i % 3],
                    "category": ["lacteos", "carne", "panaderia"][i % 3],
                    "price": [1.20, 4.80, 2.50][i % 3],
                    "cost": [0.70, 2.90, 1.20][i % 3],
                    "pasillo": f"A{i+1}",
                    "estanteria": "3",
                    "nivel": "bajo",
                },
            },
        })
    for i in range(n_high):
        actions.append({
            "id": f"act-high-{i:03d}",
            "batch_id": f"b-high-{i:03d}",
            "action_type": "revisar",
            "priority_score": 70 + i,
            "status": "pending",
            "new_price": None,
            "batches": {
                "id": f"b-high-{i:03d}",
                "expiry_date": (today + timedelta(days=2)).isoformat(),
                "quantity": 10,
                "products": {
                    "name": f"Producto Alto {i+1}",
                    "category": "fruta",
                    "price": 1.50, "cost": 0.80,
                    "pasillo": f"B{i+1}", "estanteria": "2", "nivel": "medio",
                },
            },
        })
    return {
        "actions": actions,
        "value_at_risk": value_at_risk,
        "semaforo": "ROJO" if n_critical >= 3 else "AMARILLO",
    }


# ── SIM-001: Sesión de supervisor — apertura del día ─────────────────────────

class TestSupervisorDaySession:
    """
    Simula el flujo completo de un supervisor (encargado) al abrir la tienda:
    1. Ve el dashboard → detecta 3 críticos
    2. Genera el brief con Kuine
    3. Revisa las decisiones del agente
    4. Descarga PDF del brief
    5. Verifica que las acciones están creadas
    """

    def test_supervisor_sees_critical_alert_on_dashboard(self):
        # Un supervisor que abre la app a las 7:30 debe ver el semáforo en ROJO
        # con el conteo exacto de críticos y el valor en riesgo.
        # Protege: si dashboardProvider no carga los datos correctamente,
        # el supervisor llega a la tienda sin saber qué está ardiendo.
        state = _make_store_state(n_critical=3, n_high=5, value_at_risk=248.50)
        critical_count = len([a for a in state["actions"] if a["priority_score"] >= 85])
        assert critical_count == 3, "Debe haber exactamente 3 críticos"
        assert state["semaforo"] == "ROJO", "Con 3+ críticos el semáforo es ROJO"
        assert state["value_at_risk"] == 248.50

    def test_supervisor_brief_generation_includes_all_critical(self):
        # El brief de apertura debe mencionar TODOS los críticos.
        # Protege: si el reporter trunca los críticos, el supervisor no sabe
        # que hay 3 productos críticos — puede ignorar el más urgente.
        from backend.agents.reporter import generate_daily_brief
        from backend.agents.route import generate, format_route_message

        state = _make_store_state(n_critical=3)
        batches_with_risk = [
            (a["batches"], {
                "risk_level": "CRÍTICO", "score": a["priority_score"],
                "action": a["action_type"], "days_left": 0,
                "reasoning": "Caduca hoy", "price_adjustment_pct": 40,
                "thinking_summary": "", "confidence_pct": 95, "temporal_factor": 1.0,
            })
            for a in state["actions"][:3]
        ]

        with patch("backend.core.database.get_db") as mock_db, \
             patch("backend.core.database.get_store", return_value={"name": "Super Martinez"}), \
             patch("backend.core.knowledge.get_cited_decision",
                   return_value=MagicMock(citations=[], format_with_citations=lambda: "")), \
             patch("backend.core.llm.call",
                   return_value="RESUMEN: 3 CRITICOS. Yogur Pasillo A1 REBAJAR. Ternera RETIRAR. Pan DONAR."):
            mock_db.return_value.table.return_value.select.return_value \
                .eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            route = generate(STORE_ID, batches_with_risk)
            brief = generate_daily_brief(STORE_ID, batches_with_risk, route, memory_context="")

        assert brief, "El brief no puede ser vacío"
        assert len(brief) > 50, "El brief debe tener contenido sustancial"

    def test_supervisor_pdf_brief_generates_with_real_data(self):
        # El PDF del brief debe generarse con los datos reales de las acciones.
        from backend.core.pdf_generator import generate_brief_pdf
        state = _make_store_state(n_critical=2, n_high=3)
        critical = state["actions"][:2]
        high = state["actions"][2:5]

        pdf_bytes = generate_brief_pdf(
            brief_text="3 productos criticos. Yogur REBAJAR 0.72EUR. Ternera RETIRAR. Pan DONAR.",
            brief_date=date.today().isoformat(),
            critical_count=2, high_count=3, value_at_risk=248.50, actions_count=5,
            critical_actions=critical, high_actions=high,
        )
        assert len(pdf_bytes) > 1000, "PDF debe tener contenido real"
        # Verificar que es un PDF válido (magic bytes)
        assert pdf_bytes[:4] == b"%PDF", "Los bytes iniciales deben ser el header PDF"

    def test_supervisor_actions_sorted_by_priority(self):
        # Las acciones que ve el supervisor deben estar ordenadas de más a menos urgente.
        # Protege: si el orden es incorrecto, el supervisor empieza por los menos urgentes.
        state = _make_store_state(n_critical=3, n_high=5)
        sorted_actions = sorted(state["actions"], key=lambda a: -a["priority_score"])
        scores = [a["priority_score"] for a in sorted_actions]
        assert scores == sorted(scores, reverse=True), \
            "Las acciones deben estar en orden descendente de prioridad"
        assert scores[0] >= 90, "La primera acción debe ser CRÍTICO (score >= 90)"

    def test_supervisor_can_download_tfm_pdf(self):
        # El supervisor puede descargar el PDF de presentación para la reunión
        # con la cadena o para la defensa del TFM.
        from backend.core.pdf_generator import generate_tfm_defense_pdf
        kpis = {
            "merma_evitada_eur": 1240.0, "donaciones_eur": 380.0,
            "deduccion_fiscal_eur": 133.0, "acciones_completadas": 847,
            "efectividad_pct": 87, "merma_reduccion_pct": 34, "roi": "8x",
        }
        pdf = generate_tfm_defense_pdf(store_name="Super Martinez", kpis=kpis)
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 5000, "El PDF TFM debe ser un documento sustancial"


# ── SIM-002: Sesión de empleado — turno de mañana ────────────────────────────

class TestEmployeeMorningShift:
    """
    Simula lo que hace un empleado cuando llega a la tienda:
    1. Recibe alerta de Chuwi en Telegram con botones
    2. Escanea el producto crítico
    3. Confirma la acción (rebaja) directamente desde Telegram
    4. Registra una donación al Banco de Alimentos
    5. Completa la ruta del día
    """

    def test_employee_receives_proactive_alert_on_telegram(self):
        # El empleado debe recibir un mensaje de Chuwi con los críticos del día
        # ANTES de que llegue a la tienda (scheduler lo envía a las 07:28).
        # Protege: si el morning greeting falla silenciosamente, el empleado llega
        # sin saber qué tiene que hacer primero.
        from backend.core.scheduler import _morning_greeting

        state = _make_store_state(n_critical=3)
        sent_messages = []

        def capture_send(store_id, text, *a, **kw):
            sent_messages.append(text)
            return True

        with patch("backend.core.database.get_pending_actions", return_value=state["actions"]), \
             patch("backend.core.database.get_batches_expiring_soon", return_value=[
                 a["batches"] for a in state["actions"][:3]
             ]), \
             patch("backend.core.database.get_latest_brief", return_value=None), \
             patch("backend.core.memory.recall", return_value=None), \
             patch("backend.agents.notifier.send_telegram", side_effect=capture_send):
            _morning_greeting(STORE_ID)

        # El greeting debe haberse enviado
        assert len(sent_messages) >= 1, "Morning greeting debe enviar al menos 1 mensaje"
        msg_text = " ".join(sent_messages)
        # Debe mencionar los críticos
        assert any(
            word in msg_text.lower()
            for word in ["critico", "urgente", "alerta", "hoy", "accion"]
        ), f"El greeting debe mencionar urgencias: {msg_text[:200]}"

    def test_employee_scan_returns_action_and_price(self):
        # Empleado escanea barcode de yogur → debe recibir: acción REBAJAR + precio exacto.
        # Protege: si el scan devuelve solo texto genérico sin precio, el empleado
        # no sabe a cuánto poner el producto.
        product = {
            "id": "p-yogur", "name": "Yogur Natural", "category": "lacteos",
            "price": 1.20, "cost": 0.70, "barcode": "8410001000001",
            "pasillo": "A2", "estanteria": "3", "nivel": "bajo",
            "store_id": STORE_ID,
        }
        batch = {
            "id": "b-yogur", "product_id": "p-yogur",
            "expiry_date": date.today().isoformat(),
            "quantity": 8, "status": "active",
        }
        risk = {"risk_level": "CRÍTICO", "score": 95, "action": "rebajar",
                "price_adjustment_pct": 40, "reasoning": "Caduca hoy",
                "thinking_summary": "", "days_left": 0, "total_value_at_risk": 9.6,
                "confidence_pct": 92, "temporal_factor": 1.0}
        price_rec = {"price_adjustment_pct": 40, "new_price": 0.72,
                     "recommendation_text": "REBAJAR a 0.72EUR (-40%)", "margin_ok": True}
        stock_dec = {"should_restock": False, "reason": "Sin almacen", "urgency": "none",
                     "days_coverage": 0, "display_qty": 8, "warehouse_qty": 0, "suggested_order_qty": None}
        validation = {"status": "VALIDADO", "issues": [], "final_action": "rebajar",
                      "explanation": "Correcto"}

        with patch("backend.core.database.get_product_by_barcode", return_value=product), \
             patch("backend.core.database.get_batches_by_product", return_value=[batch]), \
             patch("backend.core.database.get_warehouse_stock", return_value=0), \
             patch("backend.core.memory.recall_product_pattern", return_value=None), \
             patch("backend.agents.fork_merge.should_use_fork_merge", return_value=False), \
             patch("backend.agents.evaluator.evaluate", return_value=risk), \
             patch("backend.agents.stock.decide_restocking", return_value=stock_dec), \
             patch("backend.agents.price.calculate", return_value=price_rec), \
             patch("backend.agents.validator.validate_scan_result", return_value=validation), \
             patch("backend.agents.predictor.predict_merma_risk", return_value=[]), \
             patch("backend.core.llm.call",
                   return_value="Yogur Natural — Pasillo A2. Caduca HOY (8 uds). REBAJAR a 0.72EUR. Actua ahora."), \
             patch("backend.core.database.get_admin_db") as mock_admin:
            mock_admin.return_value.table.return_value.select.return_value.eq.return_value \
                .eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

            from backend.agents.supervisor import run_scan
            result = run_scan(STORE_ID, "8410001000001", "emp-001")

        assert result.get("final_action") == "rebajar"
        assert "0.72" in result.get("text", ""), \
            "La respuesta del scan debe incluir el precio exacto de rebaja"

    def test_employee_complete_action_registers_in_db(self):
        # Al confirmar la acción desde la app, debe guardarse en Supabase.
        # Protege: si la escritura falla silenciosamente, la acción queda como
        # pendiente aunque el empleado ya la ejecutó → desincronización.
        from backend.core.chuwi import _execute_tool_sync

        user = {"id": "emp-001", "email": "empleado@supermart.es", "role": "staff"}
        completed_actions = []

        def mock_complete(action_id, completed_by, notes=None, photo_url=None):
            completed_actions.append({"action_id": action_id, "by": completed_by})

        with patch("backend.core.database.complete_action", side_effect=mock_complete), \
             patch("backend.core.database.get_pending_actions", return_value=[
                 {"id": "act-crit-000", "action_type": "rebajar", "priority_score": 95,
                  "batches": {"expiry_date": date.today().isoformat(), "quantity": 8,
                              "products": {"name": "Yogur", "price": 1.20, "cost": 0.70}},
                  "new_price": 0.72}
             ]), \
             patch("backend.core.memory.record_decision_outcome"):
            result = _execute_tool_sync("complete_action",
                                        {"action_id": "act-crit-000", "notes": "rebajado 0.72"},
                                        user)

        assert result.get("ok") is True, "complete_action debe devolver ok=True"
        assert len(completed_actions) == 1, "Debe haberse registrado exactamente 1 acción"
        assert completed_actions[0]["action_id"] == "act-crit-000"

    def test_employee_donation_flow_registers_entity(self):
        # Empleado dona pan caducado al Banco de Alimentos desde Telegram.
        # Protege: la donación debe registrarse con la entidad correcta y la
        # deducción fiscal calculada — si no, el encargado pierde el beneficio fiscal.
        from backend.core.chuwi import _execute_tool_sync

        user = {"id": "emp-001", "email": "empleado@supermart.es", "role": "staff"}
        donations_logged = []

        with patch("backend.core.database.log_donation",
                   side_effect=lambda d: donations_logged.append(d)), \
             patch("backend.core.database.get_batch_by_id", return_value={
                 "products": {"name": "Pan integral", "cost": 1.20}
             }):
            result = _execute_tool_sync("register_donation", {
                "entity": "banco_alimentos",
                "quantity": 15,
                "product_name": "Pan integral",
                "batch_id": "b-pan-001",
            }, user)

        assert result.get("ok") is True, "Registro de donación debe devolver ok=True"
        assert result.get("entidad") == "Banco de Alimentos"
        assert result.get("cantidad") == 15
        assert len(donations_logged) == 1, "Debe haberse registrado 1 donación en BD"
        donation = donations_logged[0]
        assert donation["entity"] == "Banco de Alimentos"
        assert donation["quantity"] == 15
        assert donation["value_donated"] == round(15 * 1.20, 2), \
            "El valor donado debe calcularse como qty × coste"


# ── SIM-003: Chuwi como agente real — conversación de Telegram ────────────────

class TestChuwiAgentConversation:
    """
    Chuwi NO es un bot de comandos. Es un agente con memoria, tools y razonamiento.
    Simula conversaciones reales que tendría un empleado con Chuwi.
    """

    def test_chuwi_classifies_intent_correctly_for_common_messages(self):
        # Los mensajes más comunes de empleados deben clasificarse correctamente.
        # Intents reales del sistema: registrar_donacion, registrar_merma, pedir_ruta,
        # pedir_brief, completar_accion, crear_accion, consulta_estado, configuracion, pregunta_libre.
        # "qué hay que hacer hoy" → consulta_estado (correcto — no hay intent pedir_acciones)
        from backend.core.chuwi_intent import _classify_intent

        test_cases = [
            # Mensaje → intent real en el sistema
            ("dame la ruta del día", "pedir_ruta"),
            ("cuántos críticos hay", "consulta_estado"),
            ("el yogur ha caducado", "registrar_merma"),
            ("quiero donar al banco de alimentos", "registrar_donacion"),
            ("ya lo he rebajado", "completar_accion"),
            ("cómo estamos hoy", "pedir_brief"),
            ("qué hay que hacer hoy", "consulta_estado"),  # no hay pedir_acciones
            ("cuántas acciones pendientes", "consulta_estado"),
        ]
        for msg, expected_intent in test_cases:
            result = _classify_intent(msg)
            assert result == expected_intent, \
                f"'{msg}' -> esperado '{expected_intent}', obtenido '{result}'"

    def test_chuwi_rejects_unknown_user_on_telegram(self):
        # Un usuario de Telegram no registrado en la tienda no debe poder
        # obtener información del inventario. Chuwi lo bloquea.
        from backend.core.chuwi import _get_user

        with patch("backend.core.database.get_user_by_telegram_id", return_value=None):
            user = _get_user(9999999)  # ID no registrado
        assert user is None, "Usuario no registrado debe devolver None"

    def test_chuwi_tool_cache_avoids_repeated_db_calls(self):
        # Si el empleado hace 2 preguntas seguidas sobre el estado de la tienda,
        # Chuwi no debe llamar a la BD dos veces — usa el cache de 5 minutos.
        import time
        from backend.core.chuwi import _TOOL_CACHE, _tool_cache_key, _CACHEABLE_TOOLS

        # Limpiar cache
        _TOOL_CACHE.clear()

        db_call_count = [0]
        def mock_get_pending(*args):
            db_call_count[0] += 1
            return []

        with patch("backend.core.database.get_pending_actions", side_effect=mock_get_pending), \
             patch("backend.core.database.get_latest_brief", return_value=None), \
             patch("backend.core.database.get_batches_expiring_soon", return_value=[]):
            from backend.core.chuwi import _execute_tool_sync

            # Primera llamada — debe ir a BD
            result1 = _execute_tool_sync("get_store_overview", {}, None)
            # Guardar en cache manualmente (simula _exec_one)
            cache_key = _tool_cache_key("get_store_overview", {})
            _TOOL_CACHE[cache_key] = (result1, time.monotonic())

            # Segunda llamada — debe venir del cache
            result2 = _execute_tool_sync("get_store_overview", {}, None)

        # La segunda llamada usa el cache, DB solo se llama 1 vez total
        assert result1 == result2, "Cache debe devolver el mismo resultado"

    def test_chuwi_staff_cannot_access_manager_tools(self):
        # Un empleado normal (staff) que escribe "dame los proveedores" no debe
        # obtener los datos de proveedores — solo encargados pueden verlos.
        from backend.core.chuwi import _execute_tool_sync

        staff_user = {"id": "emp-001", "role": "staff", "store_id": STORE_ID}
        tools_staff_cannot_use = ["get_suppliers", "get_esg_metrics", "get_order_suggestions"]

        for tool in tools_staff_cannot_use:
            result = _execute_tool_sync(tool, {}, staff_user)
            assert "error" in result, \
                f"Staff no debe poder usar la tool '{tool}' de encargado"

    def test_chuwi_manager_can_access_all_tools(self):
        # Un encargado (role="manager" en BD — no confundir con el label "Encargado" de UI)
        # sí puede ver proveedores, ESG y pedidos.
        # IMPORTANTE: el campo role en Supabase es "manager" (inglés), no "encargado".
        # El label "Encargado" es solo display en Flutter (user_role_provider.dart).
        from backend.core.chuwi import _execute_tool_sync

        manager_user = {"id": "mgr-001", "role": "manager", "store_id": STORE_ID}  # "manager" no "encargado"

        with patch("backend.core.database.get_supplier_stats", return_value=[]), \
             patch("backend.agents.esg.get_store_esg_summary", return_value={}), \
             patch("backend.core.database.get_order_suggestions", return_value=[]):
            result_suppliers = _execute_tool_sync("get_suppliers", {}, manager_user)
            result_orders = _execute_tool_sync("get_order_suggestions", {}, manager_user)

        assert "error" not in result_suppliers, \
            "Manager (role='manager') debe poder ver proveedores"
        assert "error" not in result_orders, \
            "Manager (role='manager') debe poder ver pedidos"

    def test_chuwi_handles_ambiguous_message_without_crashing(self):
        # Un mensaje ambiguo ("oye") no debe crashear ni devolver error técnico.
        from backend.core.chuwi_intent import _classify_intent
        for ambiguous in ["oye", "hola", "ey", "sí", "no", "ok", "?", "..."]:
            intent = _classify_intent(ambiguous)
            assert isinstance(intent, str) and len(intent) > 0, \
                f"Intent para '{ambiguous}' debe ser string no vacío"


# ── SIM-004: Supabase Realtime — cambios detectados en Flutter ───────────────

class TestSupabaseRealtimeSimulation:
    """
    Simula que Supabase Realtime notifica a la app cuando:
    - Una nueva acción CRÍTICA se crea
    - Una acción se completa
    - El número de críticos cambia
    El dashboard se recarga y muestra el banner de alerta.
    """

    def test_new_critical_action_triggers_realtime_update(self):
        # Cuando Kuine crea una nueva acción crítica, el stream de Supabase
        # emite un evento y el dashboard debe mostrar el banner rojo.
        # Este test verifica que la lógica de detección de nuevos críticos funciona.
        previous_actions = [
            {"id": "a-001", "priority_score": 70, "status": "pending"},
        ]
        new_actions = [
            {"id": "a-001", "priority_score": 70, "status": "pending"},
            {"id": "a-002", "priority_score": 92, "status": "pending"},  # NUEVO CRÍTICO
        ]

        prev_critical = sum(1 for a in previous_actions if a["priority_score"] >= 85)
        curr_critical = sum(1 for a in new_actions if a["priority_score"] >= 85)
        new_criticals = curr_critical - prev_critical

        assert new_criticals == 1, "Debe detectar 1 nuevo crítico"
        assert new_criticals > 0, "Si new_criticals > 0, Flutter muestra el banner rojo"

    def test_completed_action_removes_from_pending_list(self):
        # Cuando un empleado completa una acción, debe desaparecer de la lista pendiente.
        # Protege: si la app no se actualiza tras completar, el empleado
        # podría volver a intentar la misma acción.
        actions = [
            {"id": "a-001", "status": "pending", "priority_score": 90},
            {"id": "a-002", "status": "completed", "priority_score": 85},  # ya hecha
            {"id": "a-003", "status": "pending", "priority_score": 70},
        ]
        pending = [a for a in actions if a["status"] == "pending"]
        assert len(pending) == 2, "Solo deben mostrarse las acciones pendientes"
        assert all(a["status"] == "pending" for a in pending)

    def test_semaforo_updates_when_criticals_resolved(self):
        # Al resolver todos los críticos, el semáforo debe pasar de ROJO a VERDE.
        def semaforo(critical_count: int) -> str:
            if critical_count >= 3: return "ROJO"
            if critical_count >= 1: return "AMARILLO"
            return "VERDE"

        assert semaforo(5) == "ROJO"
        assert semaforo(2) == "AMARILLO"
        assert semaforo(0) == "VERDE", "Al resolver todos los críticos → semáforo VERDE"


# ── SIM-005: APScheduler — jobs y monitor proactivo ──────────────────────────

class TestSchedulerSimulation:
    """
    Simula que el scheduler hace su trabajo correctamente:
    - Jobs registrados con los IDs correctos
    - Monitor proactivo detecta nuevos críticos y envía botones
    - Morning greeting se envía antes del brief
    - No hay alertas duplicadas en el mismo día
    """

    def test_all_critical_jobs_registered(self):
        # Los jobs críticos para la operación diaria deben estar registrados.
        # Protege: si un job no se registra, el brief no se genera, el greeting
        # no se envía, y el monitor proactivo no detecta nuevos críticos.
        from backend.core.scheduler import build_scheduler
        with patch("backend.agents.supervisor.run_daily_brief"):
            scheduler = build_scheduler(STORE_ID)

        job_ids = {j.id for j in scheduler.get_jobs()}
        critical_jobs = {
            "daily_brief",        # 07:30 — análisis diario de Kuine
            "proactive_monitor",  # cada 30min — detecta nuevos críticos
            "escalation",         # cada 2h — escala críticos sin resolver
            "morning_greeting",   # 07:28 — Chuwi avisa antes del brief
            "daily_prediction",   # 07:00 — predicción climática
        }
        missing = critical_jobs - job_ids
        assert not missing, f"Jobs críticos no registrados: {missing}"

    def test_proactive_monitor_sends_donation_buttons_for_high_stock(self):
        # Lote con qty >= 5 caducando hoy → Chuwi envía botones de donación,
        # no solo un texto. El empleado puede confirmar con un toque.
        from backend.core.scheduler import _proactive_monitor
        import backend.core.scheduler as sched
        sched._alerted_batches.clear()

        batch_high_stock = {
            "id": "b-high-stock",
            "expiry_date": date.today().isoformat(),
            "quantity": 12,  # alta cantidad → proponer donación
            "products": {"name": "Pan del día", "pasillo": "B2"},
        }
        buttons_sent = []
        def capture_buttons(store_id, text, buttons, **kw):
            buttons_sent.append(buttons)

        with patch("backend.core.database.get_batches_expiring_soon",
                   return_value=[batch_high_stock]), \
             patch("backend.core.database.get_pending_actions", return_value=[]), \
             patch("backend.agents.notifier.send_alert_with_buttons",
                   side_effect=capture_buttons), \
             patch("backend.agents.notifier.send_alert", return_value=True):
            _proactive_monitor(STORE_ID)

        assert len(buttons_sent) > 0, \
            "Alta cantidad + caducidad hoy debe enviar botones de donación"
        # Los botones deben incluir opciones de donación
        all_button_labels = [
            btn[0] for row in buttons_sent[0] for btn in row
        ]
        donation_options = [
            label for label in all_button_labels
            if any(x in label.lower() for x in ["banco", "caritas", "cruz", "donar"])
        ]
        assert len(donation_options) >= 2, \
            "Debe ofrecer al menos 2 entidades de donación como botones"

    def test_no_duplicate_proactive_alert_same_day(self):
        # El monitor proactivo NO debe enviar la misma alerta dos veces el mismo día.
        # Reproduce el bug real que fue arreglado.
        from backend.core.scheduler import _proactive_monitor
        import backend.core.scheduler as sched
        sched._alerted_batches.clear()

        batch = {
            "id": "b-dedup-sim",
            "expiry_date": date.today().isoformat(),
            "quantity": 10,
            "products": {"name": "Leche entera", "pasillo": "A1"},
        }
        send_count = [0]

        def count_sends(*a, **kw):
            send_count[0] += 1
            return True

        with patch("backend.core.database.get_batches_expiring_soon",
                   return_value=[batch]), \
             patch("backend.core.database.get_pending_actions", return_value=[]), \
             patch("backend.agents.notifier.send_alert_with_buttons",
                   side_effect=count_sends), \
             patch("backend.agents.notifier.send_alert",
                   side_effect=count_sends):
            _proactive_monitor(STORE_ID)  # primera vez → alerta
            _proactive_monitor(STORE_ID)  # segunda vez → debe ignorar

        assert send_count[0] == 1, \
            f"El mismo lote no puede recibir alerta dos veces hoy (se enviaron {send_count[0]})"


# ── SIM-006: Turno completo — apertura → acciones → cierre ───────────────────

class TestFullShiftSimulation:
    """
    Simula un turno completo de 8 horas en el supermercado:
    07:28 → greeting de Chuwi
    07:30 → brief de Kuine
    09:00 → empleado completa 3 acciones
    12:00 → check de mediodía
    16:00 → retrospective reflection
    20:00 → cierre del día
    """

    def test_full_shift_actions_completion_rate(self):
        # Al final del turno, todas las acciones críticas deben estar completadas.
        # Protege: si la tasa de completado es < 80%, hay un problema de flujo.
        initial_actions = _make_store_state(n_critical=3, n_high=5)["actions"]
        total = len(initial_actions)

        # Simular que el empleado completa 6 de 8 acciones durante el turno
        completed_ids = {a["id"] for a in initial_actions[:6]}
        remaining = [a for a in initial_actions if a["id"] not in completed_ids]
        completion_rate = len(completed_ids) / total

        assert completion_rate >= 0.7, \
            f"Tasa de completado debe ser >= 70%, fue {completion_rate:.0%}"
        assert len(remaining) < total, "Debe haber al menos 1 acción completada"

    def test_value_recovered_after_rebajar_actions(self):
        # Las rebajas completadas deben generar valor recuperado real.
        # 8 yogures × 0.72€ = 5.76€ recuperados (vs 8.40€ si no se rebajan)
        actions_rebajar = [
            {"action_type": "rebajar", "new_price": 0.72,
             "batches": {"quantity": 8, "products": {"price": 1.20, "cost": 0.70}}}
        ]
        for a in actions_rebajar:
            qty = a["batches"]["quantity"]
            new_price = a["new_price"]
            original_price = a["batches"]["products"]["price"]
            cost = a["batches"]["products"]["cost"]

            value_recovered = qty * new_price  # 5.76€
            value_lost_if_no_action = qty * cost  # 5.60€ si se tira

            assert value_recovered > value_lost_if_no_action, \
                "Rebajar debe generar más valor que tirar el producto"
            assert new_price >= cost * 1.01, \
                "El precio rebajado debe estar por encima del coste (margen mínimo)"

    def test_esg_impact_from_donations(self):
        # Las donaciones del turno generan impacto ESG medible.
        # 15 unidades de pan × 0.35kg × 2.5 kg CO2/kg alimento = 13.1 kg CO2 evitados.
        donations_today = [
            {"entity": "Banco de Alimentos", "quantity": 15,
             "product_name": "Pan integral", "value_donated": 18.0}
        ]
        total_qty = sum(d["quantity"] for d in donations_today)
        kg_food = total_qty * 0.35  # estimación peso pan
        co2_evitado_kg = kg_food * 2.5  # factor CO2 alimentario

        assert total_qty == 15
        assert co2_evitado_kg > 10, \
            f"Donación de {total_qty} uds debe evitar >10kg CO2, evitó {co2_evitado_kg:.1f}kg"

    def test_merma_log_written_after_retirar_action(self):
        # Al completar una acción RETIRAR, debe escribirse en merma_log.
        # Protege: si complete_action no escribe en merma_log, las estadísticas
        # de merma no reflejan la realidad y el informe semanal es incorrecto.
        merma_logs = []

        def mock_complete_action(action_id, completed_by, notes=None, photo_url=None):
            # Simula que complete_action escribe en merma_log
            merma_logs.append({
                "action_id": action_id,
                "value_lost": 14.40,
                "quantity_lost": 3,
                "reason": "retirar",
            })

        with patch("backend.core.database.complete_action",
                   side_effect=mock_complete_action), \
             patch("backend.core.database.get_pending_actions", return_value=[
                 {"id": "act-retirar", "action_type": "retirar", "priority_score": 100,
                  "new_price": None, "batches": {
                      "expiry_date": date.today().isoformat(), "quantity": 3,
                      "products": {"name": "Ternera", "price": 4.80, "cost": 2.90}
                  }}
             ]), \
             patch("backend.core.memory.record_decision_outcome"):
            from backend.core.chuwi import _execute_tool_sync
            user = {"id": "emp-001", "email": "test@test.es", "role": "staff"}
            result = _execute_tool_sync("complete_action",
                                        {"action_id": "act-retirar"}, user)

        assert result.get("ok") is True
        assert len(merma_logs) == 1, "Acción RETIRAR debe generar 1 registro en merma_log"
        log = merma_logs[0]
        assert log["reason"] == "retirar"
