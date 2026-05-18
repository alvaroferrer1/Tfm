"""
APScheduler setup — trabajos autónomos de MermaOps.
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
    notifier.send_alert(store_id, "MermaOps — Escalación automática", "\n".join(lines), urgent=True)
    logger.warning(f"[scheduler] Escalación: {len(overdue)} críticas > 4h en tienda {store_id}")


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

    logger.info(f"[kuine] 7 trabajos configurados para tienda {store_id}")
    return scheduler


def _proactive_monitor(store_id: str) -> None:
    """
    Kuine monitoriza la tienda cada 30 minutos.
    Para productos con exceso de stock próximos a caducar: envía botones de donación
    para que el encargado confirme con un solo toque (sin escribir nada).
    """
    from backend.core import database
    from backend.agents import notifier
    import datetime as _dt

    try:
        today_iso = _dt.date.today().isoformat()
        batches = database.get_batches_expiring_soon(store_id, days=2)
        pending_ids = {a.get("batch_id") for a in database.get_pending_actions(store_id)}

        nuevos_criticos = [
            b for b in batches
            if b.get("id") not in pending_ids
            and b.get("expiry_date", "9999") <= today_iso
        ]

        if not nuevos_criticos:
            return

        # Para productos con exceso de stock: proponer donación con botones inline
        donacion_candidatos = [b for b in nuevos_criticos if int(b.get("quantity", 0)) >= 5]
        sin_donacion = [b for b in nuevos_criticos if int(b.get("quantity", 0)) < 5]

        for batch in donacion_candidatos[:3]:
            p = (batch.get("products") or {})
            name = p.get("name", "Producto")
            pasillo = p.get("pasillo", "?")
            qty = int(batch.get("quantity", 0))
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

        if sin_donacion:
            lines = ["Kuine — Nuevos productos sin acción asignada:\n"]
            for b in sin_donacion[:4]:
                p = (b.get("products") or {})
                name = p.get("name", "Producto")
                pasillo = p.get("pasillo", "?")
                qty = b.get("quantity", 0)
                exp = b.get("expiry_date", "?")
                lines.append(f"• {name} | Pasillo {pasillo} | {qty} uds | Caduca {exp}")
            lines.append("\nRevisa las acciones pendientes o escribe a Chuwi.")
            notifier.send_alert(store_id, "Kuine — Alerta proactiva", "\n".join(lines), urgent=False)

        logger.info(f"[kuine] Monitor proactivo: {len(nuevos_criticos)} productos, {len(donacion_candidatos)} con botones de donación")

    except Exception as e:
        logger.debug(f"[kuine] Monitor proactivo: {e}")
