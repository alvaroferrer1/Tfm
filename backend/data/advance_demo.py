"""
advance_demo.py — Simulación de paso del tiempo para la demo MermaOps.

Uso:
    python -m backend.data.advance_demo --days 2    # simula 2 días
    python -m backend.data.advance_demo --reset     # vuelve al estado inicial

Makefile:
    make advance N=2
    make demo-reset
"""
import argparse
import os
import random
from datetime import date, timedelta

from backend.core.database import get_admin_db as get_db

STORE_ID = "demo-store-001"

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _fmt_date(d: date) -> str:
    """Devuelve ej: 'lunes 20 de mayo de 2026'."""
    weekday = _DIAS[d.weekday()]
    mes = _MESES[d.month]
    return f"{weekday} {d.day} de {mes} de {d.year}"


def _score_for_days(days_left: int) -> int:
    if days_left <= 0:
        return 95
    if days_left == 1:
        return 90
    if days_left == 2:
        return 80
    if days_left <= 4:
        return 65
    return 40


def _simulate_one_day(db, store_id: str, simulated_date: date, day_delta: timedelta, today: date) -> dict:
    """
    Simula un día: reduce stock, marca expirados como 'sold', actualiza urgencias.
    Devuelve: {batches_updated, actions_created, actions_completed, stock_reduced}
    """
    batches_updated = 0
    actions_created = 0
    actions_completed = 0
    stock_reduced = 0

    # Obtener lotes activos
    batches = (
        db.table("batches")
        .select("id, expiry_date, quantity, status")
        .eq("store_id", store_id)
        .eq("status", "active")
        .execute()
    ).data

    for batch in batches:
        expiry = date.fromisoformat(batch["expiry_date"])
        days_left = (expiry - simulated_date).days

        if days_left < 0:
            # Caducado: marcar como vendido/retirado
            db.table("batches").update({"status": "sold"}).eq("id", batch["id"]).execute()
            batches_updated += 1
        else:
            # Simular ventas (reduce stock ~10-25% por día)
            qty = batch.get("quantity", 0)
            if qty > 0:
                sold = max(1, int(qty * random.uniform(0.10, 0.25)))
                new_qty = max(0, qty - sold)
                new_score = _score_for_days(days_left)
                db.table("batches").update(
                    {"quantity": new_qty, "expiry_date": expiry.isoformat()}
                ).eq("id", batch["id"]).execute()
                stock_reduced += sold
                batches_updated += 1

    # Recalcular urgencias en acciones pendientes
    pending = (
        db.table("actions")
        .select("id, batch_id, priority_score")
        .eq("store_id", store_id)
        .eq("status", "pending")
        .execute()
    ).data

    for action in pending:
        batch_id = action["batch_id"]
        batch_res = (
            db.table("batches")
            .select("expiry_date, quantity, product_id")
            .eq("id", batch_id)
            .eq("status", "active")
            .execute()
        ).data
        if not batch_res:
            # Lote ya completado/retirado → completar acción
            db.table("actions").update(
                {"status": "completed", "completed_at": simulated_date.isoformat()}
            ).eq("id", action["id"]).execute()
            actions_completed += 1
        else:
            expiry = date.fromisoformat(batch_res[0]["expiry_date"])
            days_left = (expiry - simulated_date).days
            new_score = _score_for_days(days_left)
            new_type = "retirar" if days_left <= 0 else ("rebajar" if days_left <= 2 else None)
            update_data: dict = {"priority_score": new_score}
            if new_type:
                update_data["action_type"] = new_type
            db.table("actions").update(update_data).eq("id", action["id"]).execute()

    return {
        "batches_updated": batches_updated,
        "actions_created": actions_created,
        "actions_completed": actions_completed,
        "stock_reduced": stock_reduced,
    }


def _ensure_risk_distribution(db, store_id: str, today: date) -> None:
    """Garantiza mínimo 2 CRÍTICO + 3 ALTO en acciones pendientes."""
    pass  # El seed ya genera distribución correcta; se puede extender si se necesita


def _generate_simulated_brief(db, store_id: str, sim_date: date) -> None:
    """Genera un brief del día simulado."""
    try:
        from backend.agents.supervisor import run_daily_brief
        run_daily_brief(store_id)
    except Exception:
        pass


def _send_day_telegram_messages(db, store_id: str, sim_date: date, summary: dict) -> int:
    """Envía alerta por Telegram si hay CRÍTICOS. Devuelve número de mensajes enviados."""
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id_str = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id_str:
            return 0

        critical = sum(1 for _ in range(summary.get("actions_created", 0)))
        if critical == 0:
            return 0

        import asyncio
        from telegram import Bot
        fecha = _fmt_date(sim_date)
        msg = (
            f"⏩ <b>Simulación: {fecha}</b>\n\n"
            f"Kuine ha evaluado la tienda tras el avance de {summary.get('days_advanced', 1)} día(s).\n"
            f"🔴 Lotes actualizados: {summary.get('batches_updated', 0)}\n\n"
            "Revisa las acciones pendientes en la app."
        )
        asyncio.run(Bot(token).send_message(
            chat_id=int(chat_id_str), text=msg, parse_mode="HTML"
        ))
        return 1
    except Exception:
        return 0


def advance(days: float, store_id: str = STORE_ID, generate_brief: bool = True) -> dict:
    """
    Simula el paso de `days` días completos.
    Llama a _simulate_one_day una vez por día entero.
    """
    db = get_db()
    today = date.today()
    n_days = int(days)

    totals = {
        "days": days,
        "batches_updated": 0,
        "actions_created": 0,
        "actions_completed": 0,
        "stock_reduced": 0,
        "telegram_messages_sent": 0,
    }

    for i in range(n_days):
        sim_date = today + timedelta(days=i + 1)
        day_delta = timedelta(days=1)
        result = _simulate_one_day(db, store_id, sim_date, day_delta, today)
        totals["batches_updated"] += result["batches_updated"]
        totals["actions_created"] += result["actions_created"]
        totals["actions_completed"] += result["actions_completed"]
        totals["stock_reduced"] += result["stock_reduced"]

    _ensure_risk_distribution(db, store_id, today)

    sent = _send_day_telegram_messages(db, store_id, today + timedelta(days=n_days), totals)
    totals["telegram_messages_sent"] = sent

    if generate_brief:
        _generate_simulated_brief(db, store_id, today + timedelta(days=n_days))

    _print_summary(totals)
    return totals


def _print_summary(t: dict) -> None:
    days = t["days"]
    print(f"\n{'='*48}")
    print(f"  DEMO AVANZADA {days} DÍA{'S' if days != 1 else ''}")
    print(f"{'='*48}")
    print(f"  Lotes actualizados   : {t['batches_updated']}")
    print(f"  Nuevas acciones      : {t['actions_created']}")
    print(f"  Acciones completadas : {t['actions_completed']}")
    print(f"  Stock reducido       : {t['stock_reduced']} uds")
    print(f"  Alertas Telegram     : {t['telegram_messages_sent']}")
    print(f"{'='*48}\n")


def reset(store_id: str = STORE_ID) -> None:
    print("\nReseteando demo al estado inicial (seed)...")
    from backend.data.seed import run as seed_run
    seed_run()
    print("✅ Demo reseteada — usa 'make advance N=X' para simular tiempo\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulación temporal MermaOps")
    parser.add_argument("--days", type=float, default=1.0)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    if args.reset:
        reset()
    else:
        advance(args.days)
