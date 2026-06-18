"""
APScheduler setup — trabajos autónomos de MermaOps.

Trabajos:
- 07:00 Predicción de merma con clima
- 07:28 Morning greeting de Chuwi (proactivo — sin que nadie pregunte)
- 07:30 Brief diario de Kuine
- 12:00 Check de mediodía
- 16:00 Retrospective reflection (revisa outcomes de hace 24h)
- 20:00 Cierre del día
- Lunes 06:00 Informe semanal
- Día 1 08:00 Informe mensual
- Cada 2h (8-20h) Escalación de críticos sin resolver
- Cada 30min (8-21h) Monitor proactivo de donaciones
"""
from __future__ import annotations
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("mermaops.scheduler")


def _escalate_critical_actions(store_id: str) -> None:
    """
    Comprueba acciones críticas (score >= 85) sin resolver en más de 4 horas.
    Si las hay, envía alerta al grupo de Telegram de la tienda.
    Se ejecuta cada 2 horas en horario comercial (8-20h).
    """
    from backend.core import database
    from backend.agents import notifier

    overdue = database.get_overdue_critical_actions(store_id, hours=4)
    if not overdue:
        return

    lines = [f"ALERTA — {len(overdue)} acción(es) CRÍTICA(S) llevan más de 4 horas sin resolver:\n"]
    for a in overdue[:6]:
        batch = a.get("batches") or {}
        product = (batch.get("products") or {}) if batch else {}
        name = product.get("name", "Producto")
        pasillo = product.get("pasillo", "?")
        score = a.get("priority_score", 0)
        action_type = (a.get("action_type") or "revisar").upper()
        lines.append(f"• {name} | Pasillo {pasillo} | {action_type} | Prioridad {score}/100")

    lines.append("\nAsignad a alguien o escalad al turno siguiente.")
    try:
        notifier.send_alert(store_id, "MermaOps — Escalación automática", "\n".join(lines), urgent=True)
        logger.warning(f"[scheduler] Escalación: {len(overdue)} críticas > 4h en tienda {store_id}")
    except Exception as exc:
        logger.error(f"[scheduler] Error enviando escalación: {exc}", exc_info=True)


def build_scheduler(store_id: str) -> BackgroundScheduler:
    """Construye y configura el scheduler con todos los trabajos autónomos."""
    from backend.agents import supervisor

    scheduler = BackgroundScheduler(timezone="Europe/Madrid")

    def _safe_run(fn_name: str, fn):
        def wrapper():
            try:
                logger.info(f"[scheduler] Iniciando {fn_name}")
                result = fn(store_id)
                logger.info(f"[scheduler] {fn_name} completado")
                return result
            except Exception as e:
                logger.error(f"[scheduler] Error en {fn_name}: {e}", exc_info=True)
        return wrapper

    # Predicción preventiva: corre a las 07:00, antes del brief (07:30)
    # Genera predicciones de merma para los próximos 7 días con datos climáticos reales
    def _run_prediction(sid):
        from backend.agents.predictor import predict_merma_risk, generate_prediction_brief
        try:
            predictions = predict_merma_risk(sid)
            if predictions:
                brief_text = generate_prediction_brief(sid)
                from backend.agents.notifier import send_telegram
                send_telegram(sid, f"🔮 Predicción del día:\n{brief_text[:500]}")
                logger.info(f"[scheduler] Predicción: {len(predictions)} productos con riesgo detectado")
        except Exception as e:
            logger.warning(f"[scheduler] Predicción fallida (no crítico): {e}")

    scheduler.add_job(
        lambda: _run_prediction(store_id),
        "cron", hour=7, minute=0, id="daily_prediction",
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_run("brief_diario", supervisor.run_daily_brief),
        "cron", hour=7, minute=30, id="daily_brief",
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_run("check_mediodia", supervisor.run_intraday_check),
        "cron", hour=12, minute=0, id="intraday_check",
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_run("cierre_dia", supervisor.run_closing),
        "cron", hour=20, minute=0, id="closing",
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_run("informe_semanal", supervisor.run_weekly_report),
        "cron", day_of_week="mon", hour=6, minute=0, id="weekly_report",
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_run("informe_mensual", supervisor.run_monthly_report),
        "cron", day=1, hour=8, minute=0, id="monthly_report",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _escalate_critical_actions(store_id),
        "cron", hour="8-20/2", minute=0, id="escalation",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _proactive_monitor(store_id),
        "cron", hour="8-21", minute="*/30", id="proactive_monitor",
        replace_existing=True,
    )
    # Morning greeting: Chuwi saluda proactivamente con resumen crítico antes del brief
    scheduler.add_job(
        lambda: _morning_greeting(store_id),
        "cron", hour=7, minute=28, id="morning_greeting",
        replace_existing=True,
    )
    # Retrospective reflection: revisa 24h después si las decisiones de ayer funcionaron
    scheduler.add_job(
        lambda: _retrospective_reflection(store_id),
        "cron", hour=16, minute=0, id="retrospective_reflection",
        replace_existing=True,
    )
    # SLA check: escala acciones críticas sin ACK en más de 30 minutos
    scheduler.add_job(
        lambda: _check_sla_violations(store_id),
        "cron", hour="8-20", minute="*/15", id="sla_check",
        replace_existing=True,
    )
    # Proactive intent triggers: evalúa condiciones guardadas por los empleados
    scheduler.add_job(
        lambda: _evaluate_intent_triggers(store_id),
        "cron", hour="8-21", minute="*/30", id="intent_triggers",
        replace_existing=True,
    )
    # Auto-brief trigger: mini-brief inmediato si spike de críticos
    scheduler.add_job(
        lambda: _auto_brief_on_spike(store_id),
        "cron", hour="8-21", minute="*/30", id="auto_brief_spike",
        replace_existing=True,
    )
    # Anomaly detection: lotes que desaparecen sin registro (21:00, tras cierre)
    scheduler.add_job(
        lambda: _detect_inventory_anomalies(store_id),
        "cron", hour=21, minute=30, id="anomaly_detection",
        replace_existing=True,
    )
    # Agent health check: detecta inconsistencias entre decisiones de subagentes
    scheduler.add_job(
        lambda: _run_health_check(store_id),
        "cron", hour="9,13,18", minute=0, id="health_check",
        replace_existing=True,
    )

    # Calibración mensual del Evaluador (día 2 de cada mes, 3am)
    scheduler.add_job(
        lambda: _calibrate_evaluator(store_id),
        "cron", day=2, hour=3, minute=0, id="evaluator_calibration",
        replace_existing=True,
    )

    # Cargar multiplicadores calibrados al arrancar
    try:
        from backend.agents.evaluator import load_calibrated_multipliers
        load_calibrated_multipliers(store_id)
        logger.info("[calibrate] Multiplicadores del Evaluador cargados desde memoria")
    except Exception as e:
        logger.debug(f"[calibrate] No hay multiplicadores guardados: {e}")

    logger.info(f"[kuine] 15 trabajos configurados para tienda {store_id}")
    return scheduler


_alerted_batches: dict[str, str] = {}  # batch_id → fecha de última alerta (ISO date)


def _proactive_monitor(store_id: str) -> None:
    """
    Kuine monitoriza la tienda cada 30 minutos.
    Para productos con exceso de stock próximos a caducar: envía botones de donación
    para que el encargado confirme con un solo toque (sin escribir nada).
    Deduplicación: no repite alerta para el mismo lote en el mismo día.
    """
    from backend.core import database
    from backend.agents import notifier
    import datetime as _dt

    try:
        today_iso = _dt.date.today().isoformat()
        batches = database.get_batches_expiring_soon(store_id, days=2)
        pending_ids = {a.get("batch_id") for a in database.get_pending_actions(store_id)}

        # Limpiar alertas de días anteriores
        stale = [k for k, v in _alerted_batches.items() if v < today_iso]
        for k in stale:
            del _alerted_batches[k]

        cutoff_iso = (_dt.date.today() + _dt.timedelta(days=2)).isoformat()
        nuevos_criticos = [
            b for b in batches
            if b.get("id") not in pending_ids
            and b.get("expiry_date", "9999") <= cutoff_iso
            and _alerted_batches.get(b.get("id", "")) != today_iso  # no repetir hoy
        ]

        if not nuevos_criticos:
            return

        # Para productos con exceso de stock: proponer donación con botones inline
        def _qty(b: dict) -> int:
            try: return int(b.get("quantity", 0) or 0)
            except (TypeError, ValueError): return 0

        donacion_candidatos = [b for b in nuevos_criticos if _qty(b) >= 5]
        sin_donacion = [b for b in nuevos_criticos if _qty(b) < 5]

        for batch in donacion_candidatos[:3]:
            p = (batch.get("products") or {})
            name = p.get("name", "Producto")
            pasillo = p.get("pasillo", "?")
            qty = _qty(batch)
            exp = batch.get("expiry_date", "?")
            batch_id = batch.get("id", "")

            text = (
                f"KUINE — Donación sugerida\n\n"
                f"{name} | Pasillo {pasillo}\n"
                f"{qty} unidades | Caduca {exp}\n\n"
                f"Stock elevado + caducidad hoy. ¿Lo donamos?"
            )
            buttons = [
                [("❤️ Banco de Alimentos", f"donate_now:banco_alimentos:{batch_id}"),
                 ("🤝 Cáritas", f"donate_now:caritas:{batch_id}")],
                [("🏥 Cruz Roja", f"donate_now:cruz_roja:{batch_id}"),
                 ("💰 Mejor rebajar", f"donate_now:rebajar:{batch_id}")],
                [("❌ Ya gestionado", f"donate_now:skip:{batch_id}")],
            ]
            notifier.send_alert_with_buttons(store_id, text, buttons)
            _alerted_batches[batch_id] = today_iso

        if sin_donacion:
            lines = ["Kuine — Nuevos productos sin acción asignada:\n"]
            for b in sin_donacion[:4]:
                p = (b.get("products") or {})
                name = p.get("name", "Producto")
                pasillo = p.get("pasillo", "?")
                qty = b.get("quantity", 0)
                exp = b.get("expiry_date", "?")
                bid = b.get("id", "")
                lines.append(f"• {name} | Pasillo {pasillo} | {qty} uds | Caduca {exp}")
                _alerted_batches[bid] = today_iso
            lines.append("\nRevisa las acciones pendientes o escribe a Chuwi.")
            notifier.send_alert(store_id, "Kuine — Alerta proactiva", "\n".join(lines), urgent=False)

        logger.info(f"[kuine] Monitor proactivo: {len(nuevos_criticos)} productos, {len(donacion_candidatos)} con botones de donación")

    except Exception as e:
        logger.warning(f"[kuine] Monitor proactivo error: {e}")


def _auto_brief_on_spike(store_id: str) -> None:
    """
    Detección de spike de críticos — si el número sube >3 en 30 minutos,
    Kuine lanza un mini-brief de emergencia sin esperar al horario programado.
    """
    from backend.core import database, memory as _mem
    import json as _json

    try:
        pending = database.get_pending_actions(store_id)
        current_critical = sum(1 for a in pending if (a.get("priority_score") or 0) >= 85)

        # Leer el último valor guardado
        _spike_key = "auto_brief_last_critical_count"
        _prev_raw = _mem.recall(store_id, _spike_key)
        _prev = int(_prev_raw) if _prev_raw and _prev_raw.isdigit() else 0

        # Guardar el actual
        _mem.remember(store_id, _spike_key, str(current_critical))

        # Spike: subió más de 3 críticos desde el último check
        if current_critical - _prev >= 3 and current_critical >= 5:
            logger.warning(f"[spike] Críticos {_prev} → {current_critical} en tienda {store_id} — mini-brief emergencia")
            from backend.agents import supervisor, notifier
            # Mini-brief rápido: solo el texto de críticos, sin el loop completo
            critical_actions = [a for a in pending if (a.get("priority_score") or 0) >= 85]
            lines = [f"⚡ ALERTA — {current_critical} acciones CRÍTICAS ({current_critical - _prev} nuevas en 30min)\n"]
            for a in critical_actions[:6]:
                batch = a.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                lines.append(
                    f"🔴 {product.get('name','?')} | Pasillo {product.get('pasillo','?')} "
                    f"| {a.get('action_type','?').upper()} | Score {a.get('priority_score',0)}"
                )
            lines.append("\nKuine ha creado las acciones. Revisar e intervenir inmediatamente.")
            notifier.send_telegram(store_id, "\n".join(lines))
    except Exception as e:
        logger.debug(f"[spike] error: {e}")


def _morning_greeting(store_id: str) -> None:
    """
    Chuwi saluda proactivamente a las 07:28 con el estado real de la tienda.
    No espera a que nadie pregunte — es un agente, no un bot.
    Formato compacto para leer en 10 segundos antes de abrir.
    """
    from backend.core import database
    from backend.agents import notifier
    import datetime as _dt

    try:
        pending = database.get_pending_actions(store_id)
        critical = [a for a in pending if (a.get("priority_score") or 0) >= 85]
        high = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
        batches_today = database.get_batches_expiring_soon(store_id, days=1)
        total_value = sum(
            (b.get("quantity") or 0) * ((b.get("products") or {}).get("price") or 0)
            for b in batches_today
        )
        weekday = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][
            _dt.date.today().weekday()
        ]

        # Semáforo
        if len(critical) >= 5:
            semaforo = "🔴 ALERTA"
        elif len(critical) >= 2:
            semaforo = "🟡 ATENCIÓN"
        elif len(critical) >= 1:
            semaforo = "🟡 PRECAUCIÓN"
        else:
            semaforo = "🟢 OK"

        lines = [
            f"Buenos días — {weekday} {_dt.date.today().strftime('%d/%m')}",
            "",
            f"{semaforo} | {len(pending)} acciones | {len(critical)} CRÍTICAS | {len(high)} altas",
        ]

        if critical:
            lines.append("")
            lines.append("Productos CRÍTICOS de hoy:")
            for a in critical[:4]:
                batch = a.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                name = product.get("name", "?")
                pasillo = product.get("pasillo", "?")
                atype = (a.get("action_type") or "revisar").upper()
                lines.append(f"  • {name} · Pasillo {pasillo} · {atype}")

        if total_value > 0:
            lines.append(f"\nValor en riesgo HOY: {round(total_value, 2):.2f}€")

        # Añadir reflexión de ayer si existe
        try:
            import json as _json
            from backend.core import memory as _mem_g
            _refl_raw = _mem_g.recall(store_id, "reflexiones_recientes")
            if _refl_raw:
                _refls = _json.loads(_refl_raw)
                if _refls:
                    _lesson = _refls[0].get("lesson", "")[:120]
                    _rdate = _refls[0].get("date", "")
                    if _lesson:
                        lines.append(f"\nKuine aprendió ayer: {_lesson}")
        except Exception:
            pass

        lines += ["", "El brief completo llega en 2 minutos. Chuwi está aquí para lo que necesites."]

        notifier.send_telegram(store_id, "\n".join(lines))
        logger.info(f"[greeting] Morning greeting enviado — {len(critical)} críticos, {len(pending)} pendientes")
    except Exception as e:
        logger.warning(f"[greeting] Error enviando morning greeting: {e}")


def _retrospective_reflection(store_id: str) -> None:
    """
    Retrospective reflection loop — el patrón más impactante de agentes que aprenden.

    Cada tarde a las 16:00, Kuine revisa:
    1. Qué decisiones tomó ayer (via agent_runs + supervisor_decisions)
    2. Qué pasó realmente (via merma_log + completions)
    3. Calcula efectividad real vs estimada
    4. Genera reflexión con Haiku: qué habría hecho diferente
    5. Guarda en memoria episódica para informar el siguiente brief

    Pattern: Retrospective reflection (NeurIPS 2023, producción 2025)
    Afresh usa el equivalente para calibrar modelos de demanda.
    """
    from backend.core import database, memory as mem, llm
    import datetime as _dt
    import json

    try:
        yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()

        # 1. Qué acciones se tomaron ayer
        try:
            db = database.get_db()
            decisions_raw = (
                db.table("supervisor_decisions")
                .select("*")
                .eq("store_id", store_id)
                .gte("created_at", f"{yesterday}T00:00:00")
                .lte("created_at", f"{yesterday}T23:59:59")
                .limit(20)
                .execute()
            )
            decisions = decisions_raw.data or []
        except Exception:
            decisions = []

        if not decisions:
            logger.debug("[reflection] Sin decisiones de ayer — saltando reflexión")
            return

        # 2. Qué merma ocurrió realmente ayer
        merma_real = database.get_merma_history(store_id, days=2)
        merma_hoy = [m for m in merma_real if (m.get("date") or "")[:10] == yesterday]
        valor_merma_real = sum(float(m.get("value_lost", 0)) for m in merma_hoy)

        # 3. Cuántas acciones se completaron
        try:
            completed_raw = (
                db.table("actions")
                .select("action_type, priority_score, completed_at")
                .eq("store_id", store_id)
                .eq("status", "completed")
                .gte("completed_at", f"{yesterday}T00:00:00")
                .lte("completed_at", f"{yesterday}T23:59:59")
                .execute()
            )
            completed = completed_raw.data or []
        except Exception:
            completed = []

        # 4. Construir contexto para reflexión con Haiku
        decisions_summary = "\n".join(
            f"- {d.get('decision_type','?').upper()} para {d.get('product_id','?')[:8]}, score {d.get('score',0)}"
            for d in decisions[:10]
        )
        reflection_prompt = (
            f"Eres Kuine, sistema de IA para reducción de merma. Reflexiona sobre ayer ({yesterday}):\n\n"
            f"DECISIONES TOMADAS ({len(decisions)} total):\n{decisions_summary}\n\n"
            f"RESULTADO REAL:\n"
            f"- Merma real: {round(valor_merma_real, 2)}€\n"
            f"- Acciones completadas: {len(completed)}/{len(decisions)}\n"
            f"- Tipos completados: {', '.join(set(c.get('action_type','') for c in completed))}\n\n"
            f"En 2-3 frases muy concretas: ¿Qué funcionó? ¿Qué habría hecho diferente? "
            f"¿Qué patrón debo recordar para mañana?"
        )

        reflection_text = llm.call_fast(reflection_prompt, max_tokens=200)

        # 5. Guardar reflexión en memoria episódica
        reflection_data = {
            "date": yesterday,
            "decisions_count": len(decisions),
            "completed_count": len(completed),
            "completion_rate": round(len(completed) / len(decisions) * 100) if decisions else 0,
            "merma_real_eur": round(valor_merma_real, 2),
            "reflection": reflection_text,
        }
        mem.remember(
            store_id,
            f"reflexion_dia_{yesterday}",
            json.dumps(reflection_data, ensure_ascii=False),
        )

        # También guardar las top-3 reflexiones recientes en memoria accesible
        existing_reflections_raw = mem.recall(store_id, "reflexiones_recientes")
        try:
            existing = json.loads(existing_reflections_raw) if existing_reflections_raw else []
        except Exception:
            existing = []
        existing.insert(0, {
            "date": yesterday,
            "lesson": reflection_text[:300],
            "completion_rate": reflection_data["completion_rate"],
        })
        mem.remember(
            store_id,
            "reflexiones_recientes",
            json.dumps(existing[:5], ensure_ascii=False),  # guardar últimas 5
        )

        logger.info(
            f"[reflection] Reflexión completada para {yesterday}: "
            f"{len(decisions)} decisiones, {len(completed)} completadas, "
            f"{round(valor_merma_real, 2)}€ merma real"
        )
    except Exception as e:
        logger.warning(f"[reflection] Error en retrospective reflection: {e}")


def _run_health_check(store_id: str) -> None:
    """Ejecuta el health check de agentes de Kuine."""
    try:
        from backend.agents import supervisor
        supervisor.run_agent_health_check(store_id)
    except Exception as e:
        logger.debug(f"[health_check] error: {e}")


def _calibrate_evaluator(store_id: str) -> None:
    """Calibración mensual de multiplicadores del Evaluador."""
    try:
        from backend.agents.evaluator import auto_calibrate_from_outcomes
        result = auto_calibrate_from_outcomes(store_id)
        if result.get("calibrated") and result.get("adjustments"):
            from backend.agents import notifier
            adj_text = ", ".join(f"{k}: {v}" for k, v in result["adjustments"].items())
            notifier.send_alert(
                store_id,
                "Kuine — Calibración mensual completada",
                f"Efectividad del mes: {result.get('effectiveness_pct', 0)}%\n"
                f"Ajustes aplicados: {adj_text}",
                urgent=False,
            )
        logger.info(f"[calibrate] Resultado: {result}")
    except Exception as e:
        logger.warning(f"[calibrate] error: {e}")


def _check_sla_violations(store_id: str) -> None:
    """Comprueba acciones críticas sin ACK en el SLA y escala si es necesario."""
    try:
        from backend.agents import notifier
        violations = notifier.check_sla_violations(store_id)
        if violations:
            notifier.send_sla_escalation(store_id, violations)
            logger.info(f"[sla] {len(violations)} violaciones de SLA escaladas en {store_id}")
        # Send follow-up DMs for unacknowledged critical alerts
        try:
            followups = notifier.check_sla_followups()
            if followups:
                logger.info(f"[sla] {followups} seguimientos enviados")
        except Exception as fe:
            logger.debug(f"[sla] check_sla_followups error: {fe}")
    except Exception as e:
        logger.debug(f"[sla] check_sla_violations error: {e}")


def _evaluate_intent_triggers(store_id: str) -> None:
    """
    Evalúa triggers de intención guardados por empleados ("avísame cuando X").
    Si una condición se cumple, envía DM al empleado que lo pidió.
    Patrón: ambient agent — actúa sin que nadie lo active.
    """
    try:
        from backend.core.chuwi_intent import evaluate_proactive_triggers
        from backend.agents import notifier
        from backend.core import database

        fired = evaluate_proactive_triggers(store_id)
        if not fired:
            return

        for trigger in fired:
            user_id = trigger.get("user_id", "")
            condition = trigger.get("condition", "")
            if not user_id or not condition:
                continue

            # Buscar telegram_user_id del empleado
            try:
                row = database.get_db().table("users").select("telegram_user_id, email").eq("id", user_id).maybe_single().execute()
                tg_id = (row.data or {}).get("telegram_user_id")
                if tg_id:
                    msg = (
                        f"🔔 Alerta que pediste:\n\n"
                        f"Se cumple: {condition}\n\n"
                        f"Escríbeme para ver el detalle o pulsa el menú."
                    )
                    notifier.send_dm(str(tg_id), msg)
                    logger.info(f"[intent_trigger] Disparado para {user_id}: '{condition[:40]}'")
            except Exception as e:
                logger.debug(f"[intent_trigger] DM error: {e}")

    except Exception as e:
        logger.warning(f"[intent_trigger] evaluate error: {e}")


def _detect_inventory_anomalies(store_id: str) -> None:
    """
    Anomaly detection en el grafo de transacciones.
    Detecta lotes que desaparecen del inventario sin un registro correspondiente
    (sin acción completada, sin merma_log, sin donación).
    Pattern: Trigo/Standard AI — cross-stream correlation.
    """
    from backend.core import database
    from backend.agents import notifier
    import datetime as _dt

    try:
        # Lotes que estaban activos hace 24h pero ya no están
        yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()

        # Obtener lotes activos actuales
        current_batches_raw = database.get_db().table("batches").select("id").eq("store_id", store_id).eq("status", "active").execute()
        current_ids = {b["id"] for b in (current_batches_raw.data or [])}

        # Obtener acciones completadas ayer (justifican desaparición)
        completed_raw = database.get_db().table("actions").select("batch_id").eq("store_id", store_id).eq("status", "completed").gte("completed_at", f"{yesterday}T00:00:00").execute()
        justified_batch_ids = {a["batch_id"] for a in (completed_raw.data or []) if a.get("batch_id")}

        # Obtener merma registrada ayer
        merma_raw = database.get_db().table("merma_log").select("batch_id").eq("store_id", store_id).gte("date", yesterday).execute()
        merma_batch_ids = {m["batch_id"] for m in (merma_raw.data or []) if m.get("batch_id")}

        # Lotes inactivos que no tienen justificación
        inactive_raw = database.get_db().table("batches").select("id, quantity, expiry_date, products(name)").eq("store_id", store_id).neq("status", "active").gte("updated_at", f"{yesterday}T00:00:00").execute()

        anomalies = []
        for batch in (inactive_raw.data or []):
            bid = batch.get("id")
            if not bid:
                continue
            if bid in justified_batch_ids or bid in merma_batch_ids:
                continue
            product_name = (batch.get("products") or {}).get("name", "?")
            qty = batch.get("quantity", 0)
            anomalies.append(f"• {product_name} ({qty} uds) — sin registro de salida")

        if anomalies:
            lines = [f"⚠️ ANOMALÍA DE INVENTARIO — {len(anomalies)} lote(s) sin justificación:", ""] + anomalies[:5]
            lines.append("\nVerifica que hay un albarán o acción registrada para estos productos.")
            notifier.send_alert(store_id, "Kuine — Anomalía de inventario", "\n".join(lines), urgent=False)
            logger.warning(f"[anomaly] {len(anomalies)} lotes sin justificación en {store_id}")

    except Exception as e:
        logger.debug(f"[anomaly] detection error: {e}")
