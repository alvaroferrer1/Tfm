"""
advance_demo.py — Simulador de paso del tiempo para la demo MermaOps.

Resta N días a las fechas de caducidad de la tienda, recalcula urgencias
y garantiza al menos 2 CRÍTICO + 2 ALTO para la demo en vivo.

Uso:
    python -m backend.data.advance_demo --days 2    # simula 2 días
    python -m backend.data.advance_demo --reset     # vuelve al estado inicial

Makefile:
    make advance N=2
    make demo-reset

Importable:
    from backend.data.advance_demo import advance
    summary = advance(days=2, store_id="demo-store-001")
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import uuid
from datetime import date, timedelta

from backend.core.database import get_admin_db as get_db

logger = logging.getLogger("mermaops.advance_demo")

STORE_ID = os.getenv("STORE_ID", "demo-store-001")

_MIN_CRITICO = 2
_MIN_ALTO = 2

_MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}
_DAYS_ES = {
    0: "lunes", 1: "martes", 2: "miercoles", 3: "jueves",
    4: "viernes", 5: "sabado", 6: "domingo",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_date(d: date) -> str:
    """Formatea una fecha en español: 'miercoles, 20 de mayo de 2026'."""
    weekday = _DAYS_ES[d.weekday()]
    month = _MONTHS_ES[d.month]
    return f"{weekday}, {d.day} de {month} de {d.year}"


def _urgency_for_days(days_left: int) -> str:
    if days_left <= 0:
        return "caducado"
    if days_left <= 2:
        return "critico"
    if days_left <= 5:
        return "alto"
    return "normal"


def _priority_score_for_days(days_left: int) -> int:
    if days_left <= 0:
        return 95
    if days_left == 1:
        return 90
    if days_left == 2:
        return 80
    if days_left <= 4:
        return 65
    return 40


# ── Núcleo de simulación diaria ───────────────────────────────────────────────

def _simulate_one_day(
    db,
    store_id: str,
    today: date,
    step: timedelta,
    original_today: date,
) -> dict:
    """
    Simula exactamente un día de paso del tiempo sobre los lotes activos.

    - Resta `step` a las fechas de caducidad.
    - Marca como "sold" los lotes cuya nueva caducidad <= original_today.
    - Reduce stock de lotes no expirados (ventas simuladas).
    - Crea acciones para nuevos lotes CRÍTICO sin acción pendiente.
    - Completa ~20 % de acciones antiguas (personal trabajó).

    Returns:
        dict con batches_updated, actions_created, actions_completed, stock_reduced
    """
    result: dict = {
        "batches_updated": 0,
        "actions_created": 0,
        "actions_completed": 0,
        "stock_reduced": 0,
    }

    # 1. Obtener lotes activos
    try:
        batches_res = (
            db.table("batches")
            .select("id, expiry_date, product_id, quantity")
            .eq("store_id", store_id)
            .eq("status", "active")
            .execute()
        )
        batches = batches_res.data or []
    except Exception as exc:
        logger.error(f"[advance_demo] Error obteniendo batches: {exc}")
        return result

    new_critical_ids: list[str] = []

    for batch in batches:
        try:
            old_expiry = date.fromisoformat(batch["expiry_date"])
        except (KeyError, ValueError):
            continue

        new_expiry = old_expiry - step
        days_left = (new_expiry - today).days

        if new_expiry <= original_today:
            # Lote caducado → marcar como sold
            try:
                db.table("batches").update({
                    "status": "sold",
                    "expiry_date": new_expiry.isoformat(),
                }).eq("id", batch["id"]).execute()
                result["batches_updated"] += 1
            except Exception:
                pass
        else:
            urgency = _urgency_for_days(days_left)

            # Simular ventas del día (5–15 % del stock)
            qty = batch.get("quantity", 0) or 0
            reduction = max(1, int(qty * random.uniform(0.05, 0.15))) if qty > 1 else 0
            new_qty = max(0, qty - reduction)

            update_data: dict = {
                "expiry_date": new_expiry.isoformat(),
                "quantity": new_qty,
            }
            try:
                db.table("batches").update(update_data).eq("id", batch["id"]).execute()
                result["batches_updated"] += 1
                result["stock_reduced"] += reduction
            except Exception:
                pass

            if urgency == "critico":
                new_critical_ids.append(batch["id"])

    # 2. Crear acciones para nuevos críticos sin acción pendiente
    for bid in new_critical_ids:
        batch_row = next((b for b in batches if b["id"] == bid), {})
        try:
            existing_res = (
                db.table("actions")
                .select("id")
                .eq("store_id", store_id)
                .eq("status", "pending")
                .execute()
            )
            existing_batch_ids = {r.get("batch_id") for r in (existing_res.data or [])}
            if bid not in existing_batch_ids:
                db.table("actions").insert({
                    "id": str(uuid.uuid4()),
                    "store_id": store_id,
                    "product_id": batch_row.get("product_id", ""),
                    "batch_id": bid,
                    "action_type": "rebajar",
                    "status": "pending",
                    "priority_score": 90,
                }).execute()
                result["actions_created"] += 1
        except Exception:
            pass

    # 3. Completar ~20 % de acciones pendientes antiguas (simula trabajo del personal)
    try:
        old_res = (
            db.table("actions")
            .select("id")
            .eq("store_id", store_id)
            .eq("status", "pending")
            .execute()
        )
        old_pending = old_res.data or []
        to_complete = random.sample(old_pending, max(0, len(old_pending) // 5))
        for action in to_complete:
            try:
                db.table("actions").update({"status": "completed"}).eq("id", action["id"]).execute()
                result["actions_completed"] += 1
            except Exception:
                pass
    except Exception:
        pass

    return result


# ── Garantía de distribución de riesgo ────────────────────────────────────────

def _ensure_risk_distribution(db, store_id: str, today: date, summary: dict) -> None:
    """
    Garantiza mínimo _MIN_CRITICO batches CRÍTICO y _MIN_ALTO ALTO activos.
    Inserta entradas dummy si faltan — la demo siempre tiene algo que gestionar.
    """
    try:
        active_res = (
            db.table("batches")
            .select("id, expiry_date")
            .eq("store_id", store_id)
            .eq("status", "active")
            .execute()
        )
        active = active_res.data or []
    except Exception:
        return

    critico_count = 0
    alto_count = 0
    for b in active:
        try:
            dl = (date.fromisoformat(b["expiry_date"]) - today).days
        except (KeyError, ValueError):
            continue
        u = _urgency_for_days(dl)
        if u == "critico":
            critico_count += 1
        elif u == "alto":
            alto_count += 1

    for _ in range(max(0, _MIN_CRITICO - critico_count)):
        bid = f"demo-c-{uuid.uuid4().hex[:8]}"
        expiry = (today + timedelta(days=1)).isoformat()
        try:
            db.table("batches").insert({
                "id": bid, "store_id": store_id, "product_id": "p-001",
                "expiry_date": expiry, "quantity": 5, "status": "active",
            }).execute()
            db.table("actions").insert({
                "id": str(uuid.uuid4()), "store_id": store_id, "product_id": "p-001",
                "batch_id": bid, "action_type": "rebajar", "status": "pending",
                "priority_score": 90,
            }).execute()
            summary["batches_updated"] += 1
            summary["actions_created"] += 1
        except Exception:
            pass

    for _ in range(max(0, _MIN_ALTO - alto_count)):
        bid = f"demo-a-{uuid.uuid4().hex[:8]}"
        expiry = (today + timedelta(days=4)).isoformat()
        try:
            db.table("batches").insert({
                "id": bid, "store_id": store_id, "product_id": "p-002",
                "expiry_date": expiry, "quantity": 8, "status": "active",
            }).execute()
            summary["batches_updated"] += 1
        except Exception:
            pass


def _generate_simulated_brief(db, store_id: str, days_advanced: int) -> None:
    """Genera un brief del día simulado si el supervisor está disponible."""
    try:
        from backend.agents.supervisor import run_daily_brief
        run_daily_brief(store_id)
    except Exception:
        pass


def _send_day_telegram_messages(store_id: str, critical_count: int) -> int:
    """Envía alertas Telegram sobre productos críticos nuevos. Retorna nº de mensajes enviados."""
    if critical_count == 0:
        return 0
    try:
        from backend.core import database
        chat_id = database.get_memory(store_id, "telegram_chat_id")
        if not chat_id:
            return 0
        import asyncio
        import telegram
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return 0
        bot = telegram.Bot(token=token)
        msg = (
            f"🔴 DEMO: {critical_count} producto(s) CRÍTICO(s) nuevo(s).\n"
            "Usa /criticos para ver el listado completo."
        )
        asyncio.run(bot.send_message(chat_id=chat_id, text=msg))
        return 1
    except Exception:
        return 0


# ── Función principal ─────────────────────────────────────────────────────────

def advance(
    days: int | float,
    store_id: str = STORE_ID,
    generate_brief: bool = False,
) -> dict:
    """
    Simula el paso de N días completos. Llama a _simulate_one_day N veces.

    Returns dict:
        days, batches_updated, actions_created, actions_completed,
        stock_reduced, telegram_messages_sent
    """
    db = get_db()
    today = date.today()
    step = timedelta(days=1)

    summary: dict = {
        "days": days,
        "batches_updated": 0,
        "actions_created": 0,
        "actions_completed": 0,
        "stock_reduced": 0,
        "telegram_messages_sent": 0,
    }

    n = int(days)

    if n == 0:
        _print_summary(summary)
        return summary

    for _ in range(n):
        day_result = _simulate_one_day(db, store_id, today, step, today)
        summary["batches_updated"] += day_result["batches_updated"]
        summary["actions_created"] += day_result["actions_created"]
        summary["actions_completed"] += day_result["actions_completed"]
        summary["stock_reduced"] += day_result.get("stock_reduced", 0)

        msgs = _send_day_telegram_messages(store_id, day_result["actions_created"])
        summary["telegram_messages_sent"] += msgs

    _ensure_risk_distribution(db, store_id, today, summary)

    if generate_brief:
        _generate_simulated_brief(db, store_id, n)

    _print_summary(summary)
    return summary


# ── Reset ─────────────────────────────────────────────────────────────────────

def reset(store_id: str = STORE_ID) -> None:
    """Vuelve al estado inicial ejecutando el seed completo."""
    print("\nReseteando demo al estado inicial (seed)...")
    from backend.data.seed import run as seed_run
    seed_run()
    print("Demo reseteada.\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _print_summary(t: dict) -> None:
    days = t["days"]
    unit = "dia" if days == 1 else "dias"
    print(f"\n{'=' * 50}")
    print(f"  DEMO AVANZADA {days} {unit.upper()}")
    print(f"{'=' * 50}")
    print(f"  Lotes actualizados   : {t['batches_updated']}")
    print(f"  Acciones nuevas      : {t['actions_created']}")
    print(f"  Acciones completadas : {t['actions_completed']}")
    print(f"  Stock reducido       : {t['stock_reduced']} uds")
    print(f"  Mensajes Telegram    : {t['telegram_messages_sent']}")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulacion temporal MermaOps")
    parser.add_argument("--days", type=float, default=1.0)
    parser.add_argument("--store-id", default=STORE_ID)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--brief", action="store_true", help="Generar brief al finalizar")
    args = parser.parse_args()

    if args.reset:
        reset(args.store_id)
    else:
        advance(int(args.days), store_id=args.store_id, generate_brief=args.brief)
