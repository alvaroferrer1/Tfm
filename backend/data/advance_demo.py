"""
advance_demo.py — Simulación temporal completa para la defensa del TFM.

Avanza N días en Supabase simulando TODO lo que Kuine habría hecho durante esos días:
caducidades, stock, acciones, donaciones, briefs y mensajes realistas de Telegram.
Permite mostrar en 10 segundos lo que en un supermercado real tardaría días.

Uso:
    python -m backend.data.advance_demo --days 3
    python -m backend.data.advance_demo --days 1 --no-brief
    python -m backend.data.advance_demo --reset        # vuelve al estado inicial

Makefile:
    make advance N=3
    make demo-reset
"""
from __future__ import annotations

import argparse
import random
import uuid
from datetime import date, datetime, timedelta

from backend.core.database import get_admin_db as get_db

STORE_ID = "demo-store-001"

_EMPLOYEES = ["carlos@supermarinez.es", "ana@supermarinez.es", "luis@supermarinez.es"]

_MIN_CRITICO = 2
_MIN_ALTO = 3
_MIN_BAJO = 4

_MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

_WEEKDAYS_ES = {
    0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
    4: "viernes", 5: "sábado", 6: "domingo",
}


def _fmt_date(d: date) -> str:
    return f"{_WEEKDAYS_ES[d.weekday()]} {d.day} de {_MONTHS_ES[d.month]}"


def advance(days: float, store_id: str = STORE_ID, generate_brief: bool = True) -> dict:
    """
    Avanza N días en la BD simulando la actividad real de Kuine día a día.
    Envía mensajes de Telegram para cada día simulado (briefs, alertas, cierres, donaciones).
    """
    db = get_db()
    today = date.today()
    result = {
        "days": days,
        "batches_updated": 0,
        "actions_created": 0,
        "actions_completed": 0,
        "stock_reduced": 0,
        "brief_generated": False,
        "donations_suggested": 0,
        "telegram_messages_sent": 0,
    }

    n_full_days = max(1, int(days))
    msgs_sent = 0

    for day_offset in range(1, n_full_days + 1):
        sim_date = today + timedelta(days=day_offset - n_full_days)
        is_last_day = (day_offset == n_full_days)

        day_result = _simulate_one_day(db, store_id, today, timedelta(days=1), sim_date)
        result["batches_updated"] += day_result["batches_updated"]
        result["actions_created"] += day_result["actions_created"]
        result["actions_completed"] += day_result["actions_completed"]
        result["stock_reduced"] += day_result["stock_reduced"]

        try:
            sent = _send_day_telegram_messages(
                db, store_id, sim_date, day_result,
                is_last_day=is_last_day,
            )
            msgs_sent += sent
        except Exception:
            pass

    _ensure_risk_distribution(db, store_id, today)

    if generate_brief:
        try:
            _generate_simulated_brief(db, store_id, today, days)
            result["brief_generated"] = True
        except Exception:
            pass

    result["telegram_messages_sent"] = msgs_sent

    print(
        f"[advance_demo] +{days}d → "
        f"{result['batches_updated']} lotes, "
        f"{result['actions_created']} acciones nuevas, "
        f"{result['actions_completed']} completadas, "
        f"{result['stock_reduced']} uds vendidas, "
        f"{msgs_sent} mensajes Telegram"
    )
    return result


def _simulate_one_day(db, store_id: str, today: date, delta: timedelta, sim_date: date) -> dict:
    """Simula un día completo: actualiza batches, completa acciones viejas, crea nuevas."""
    result = {"batches_updated": 0, "actions_created": 0, "actions_completed": 0, "stock_reduced": 0}

    batches = db.table("batches").select("*").eq("store_id", store_id).eq("status", "active").execute()
    updated = 0
    stock_reduced = 0
    for batch in (batches.data or []):
        old_date = date.fromisoformat(batch["expiry_date"])
        new_date = old_date - delta
        new_status = "active"
        if new_date < today:
            new_status = "sold"
        update_data = {"expiry_date": new_date.isoformat(), "status": new_status}

        qty = int(batch.get("quantity", 0))
        if qty > 0 and new_status == "active":
            sold = max(0, int(qty * random.uniform(0.05, 0.18)))
            sold = min(qty - 1, sold)
            if sold > 0:
                update_data["quantity"] = qty - sold
                stock_reduced += sold

        db.table("batches").update(update_data).eq("id", batch["id"]).execute()
        updated += 1
    result["batches_updated"] = updated
    result["stock_reduced"] = stock_reduced

    pending = db.table("actions").select("*").eq("store_id", store_id).eq("status", "pending").execute()
    pending_list = pending.data or []
    to_complete = [a for a in pending_list if (a.get("priority_score") or 0) < 85]
    n_complete = max(0, int(len(to_complete) * random.uniform(0.5, 0.75)))
    completed = 0
    for action in random.sample(to_complete, min(n_complete, len(to_complete))):
        emp = random.choice(_EMPLOYEES)
        db.table("actions").update({
            "status": "completed",
            "completed_by": emp,
            "completed_at": datetime(
                sim_date.year, sim_date.month, sim_date.day,
                random.randint(9, 18), random.randint(0, 59)
            ).isoformat(),
            "notes": (action.get("notes") or "") + f" — Completada por {emp.split('@')[0]}.",
        }).eq("id", action["id"]).execute()
        completed += 1
    result["actions_completed"] = completed

    fresh = db.table("batches").select("*, products(*)").eq("store_id", store_id).eq("status", "active").execute()
    existing_pending = {
        a["batch_id"] for a in (
            db.table("actions").select("batch_id")
            .eq("store_id", store_id).eq("status", "pending").execute().data or []
        )
    }
    created = 0
    for batch in (fresh.data or []):
        if batch["id"] in existing_pending:
            continue
        exp = date.fromisoformat(batch["expiry_date"])
        days_left = (exp - today).days
        product = batch.get("products") or {}
        price_val = float(product.get("price", 0))
        cost = float(product.get("cost", 0))
        qty = int(batch.get("quantity", 1))

        if days_left <= 0:
            action_type, score, pct = "retirar", 100, 0
            new_price = None
            note = "Caduca HOY — retirar del lineal inmediatamente."
        elif days_left == 1:
            action_type, score, pct = "rebajar", 92, 50
            new_price = max(round(price_val * 0.50, 2), round(cost * 1.05, 2))
            note = f"Caduca mañana — rebajar a {new_price}€ (−50%)."
        elif days_left <= 3:
            action_type, score, pct = "rebajar", 75, 30
            new_price = max(round(price_val * 0.70, 2), round(cost * 1.05, 2))
            note = f"Caduca en {days_left}d — rebajar a {new_price}€ (−30%)."
        else:
            continue

        if qty >= 5 and days_left <= 1:
            note += f" Con {qty} uds, considera donar al banco de alimentos."

        action_id = f"adv-{uuid.uuid4().hex[:8]}"
        db.table("actions").upsert({
            "id": action_id,
            "store_id": store_id,
            "batch_id": batch["id"],
            "action_type": action_type,
            "priority_score": score,
            "price_adjustment_pct": pct,
            "new_price": new_price,
            "status": "pending",
            "notes": note,
        }, on_conflict="id").execute()
        created += 1

    result["actions_created"] = created
    return result


def _send_day_telegram_messages(
    db, store_id: str, sim_date: date, day_result: dict, is_last_day: bool
) -> int:
    """
    Envía los mensajes de Telegram que Kuine habría enviado durante ese día simulado.
    Devuelve el número de mensajes enviados.
    """
    from backend.agents import notifier

    today = date.today()
    sent = 0
    date_str = _fmt_date(sim_date)

    pending = db.table("actions").select("*, batches(*, products(*))").eq("store_id", store_id).eq("status", "pending").execute()
    pending_list = pending.data or []
    criticos = [a for a in pending_list if (a.get("priority_score") or 0) >= 85]
    altos = [a for a in pending_list if 65 <= (a.get("priority_score") or 0) < 85]

    active_batches = db.table("batches").select("*, products(*)").eq("store_id", store_id).eq("status", "active").execute()
    value_at_risk = sum(
        int(b.get("quantity", 0)) * float((b.get("products") or {}).get("price", 0))
        for b in (active_batches.data or [])
        if (date.fromisoformat(b["expiry_date"]) - today).days <= 3
    )

    # 07:30 — Brief de apertura
    brief_lines = [
        f"KUINE — Brief {date_str}",
        "",
        f"Buenos días. Análisis de apertura del Super Martínez.",
        "",
    ]
    if criticos:
        brief_lines.append(f"CRITICO ({len(criticos)} acciones urgentes):")
        for a in criticos[:3]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            name = p.get("name", "Producto")
            pasillo = p.get("pasillo", "?")
            brief_lines.append(f"  - {name} | Pasillo {pasillo} | Score {a.get('priority_score', 0)}/100")
        brief_lines.append("")
    if altos:
        brief_lines.append(f"ALTO ({len(altos)} acciones):")
        for a in altos[:2]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            brief_lines.append(f"  - {p.get('name', '?')} | Pasillo {p.get('pasillo', '?')}")
        brief_lines.append("")
    brief_lines += [
        f"Valor en riesgo: {value_at_risk:.2f}€",
        f"Acciones completadas ayer: {day_result['actions_completed']}",
        f"Ventas del día anterior: {day_result['stock_reduced']} uds",
        "",
        "Ejecutad las acciones críticas antes de las 12h.",
    ]
    if notifier.send_telegram(store_id, "\n".join(brief_lines)):
        sent += 1

    # Donaciones con botones para productos con exceso de stock
    expiring_soon = [
        b for b in (active_batches.data or [])
        if (date.fromisoformat(b["expiry_date"]) - today).days <= 1
        and int(b.get("quantity", 0)) >= 5
    ]
    for batch in expiring_soon[:2]:
        p = batch.get("products") or {}
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
            [("Banco de Alimentos", f"donate_now:banco_alimentos:{batch_id}"),
             ("Cáritas", f"donate_now:caritas:{batch_id}")],
            [("Cruz Roja", f"donate_now:cruz_roja:{batch_id}"),
             ("Mejor rebajar", f"donate_now:rebajar:{batch_id}")],
            [("Ya gestionado", f"donate_now:skip:{batch_id}")],
        ]
        if notifier.send_alert_with_buttons(store_id, text, buttons):
            sent += 1

    # 12:00 — Check de mediodía (solo si hay acciones críticas sin resolver)
    if criticos and len(criticos) >= 2:
        midday_lines = [
            f"KUINE — Revisión mediodía {date_str}",
            "",
            f"Quedan {len(criticos)} acciones CRÍTICAS sin completar.",
        ]
        for a in criticos[:2]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            midday_lines.append(f"  - {p.get('name', '?')} | Pasillo {p.get('pasillo', '?')}")
        midday_lines += [
            "",
            "Asignad a alguien del turno de tarde si no se han resuelto.",
        ]
        if notifier.send_telegram(store_id, "\n".join(midday_lines)):
            sent += 1

    # 20:00 — Cierre del día (solo en el último día o si es day_offset con número par)
    if is_last_day:
        completed_today = db.table("actions").select("id").eq("store_id", store_id).eq("status", "completed").execute()
        n_completed = len(completed_today.data or [])
        merma_evitada = value_at_risk * 0.7

        closing_lines = [
            f"KUINE — Cierre {date_str}",
            "",
            f"Resumen del día simulado:",
            f"  Acciones completadas en total: {n_completed}",
            f"  Acciones nuevas creadas hoy: {day_result['actions_created']}",
            f"  Ventas del día: {day_result['stock_reduced']} unidades",
            f"  Merma evitada estimada: {merma_evitada:.2f}€",
            "",
        ]
        if len(criticos) == 0:
            closing_lines.append("Todos los críticos resueltos. Buen trabajo al equipo.")
        else:
            closing_lines.append(f"Quedan {len(criticos)} críticos para el turno de mañana.")

        closing_lines += [
            "",
            "Mañana a las 07:30 recibiréis el brief de apertura.",
        ]
        if notifier.send_telegram(store_id, "\n".join(closing_lines)):
            sent += 1

    return sent


def _ensure_risk_distribution(db, store_id: str, today: date) -> None:
    """Garantiza al menos CRÍTICO/ALTO/BAJO visibles en el dashboard."""
    active = db.table("batches").select("expiry_date").eq("store_id", store_id).eq("status", "active").execute()
    counts = {"critico": 0, "alto": 0, "bajo": 0}
    for b in (active.data or []):
        d = (date.fromisoformat(b["expiry_date"]) - today).days
        if d <= 1:
            counts["critico"] += 1
        elif d <= 3:
            counts["alto"] += 1
        elif d <= 7:
            counts["bajo"] += 1

    warehouse = db.table("warehouse_stock").select("*, products(*)").eq("store_id", store_id).gte("quantity", 1).execute()
    pool = list(warehouse.data or [])
    random.shuffle(pool)

    refill_targets = []
    if counts["critico"] < _MIN_CRITICO:
        refill_targets.append((0, _MIN_CRITICO - counts["critico"]))
    if counts["alto"] < _MIN_ALTO:
        refill_targets.append((2, _MIN_ALTO - counts["alto"]))
    if counts["bajo"] < _MIN_BAJO:
        refill_targets.append((5, _MIN_BAJO - counts["bajo"]))

    used = 0
    for days_offset, needed in refill_targets:
        for _ in range(needed):
            if used >= len(pool):
                break
            item = pool[used]
            used += 1
            new_batch_id = f"sim-{uuid.uuid4().hex[:8]}"
            exp = (today + timedelta(days=days_offset)).isoformat()
            db.table("batches").upsert({
                "id": new_batch_id,
                "store_id": store_id,
                "product_id": item["product_id"],
                "expiry_date": exp,
                "quantity": min(int(item.get("quantity", 5)), 10),
                "status": "active",
            }, on_conflict="id").execute()


def _generate_simulated_brief(db, store_id: str, today: date, days_advanced: float) -> None:
    """Crea un brief del día simulado en la BD para que el dashboard lo muestre."""
    pending = db.table("actions").select("*").eq("store_id", store_id).eq("status", "pending").execute()
    pending_list = pending.data or []
    critical = [a for a in pending_list if (a.get("priority_score") or 0) >= 85]
    batches = db.table("batches").select("*, products(*)").eq("store_id", store_id).eq("status", "active").execute()
    value_at_risk = sum(
        int(b.get("quantity", 0)) * float((b.get("products") or {}).get("price", 0))
        for b in (batches.data or [])
        if (date.fromisoformat(b["expiry_date"]) - today).days <= 3
    )
    sim_day = today + timedelta(days=days_advanced)
    summary = (
        f"Día simulado +{days_advanced:.0f}d ({sim_day.isoformat()}). "
        f"Kuine detectó {len(pending_list)} acciones pendientes, {len(critical)} CRÍTICAS. "
        f"Valor en riesgo: {value_at_risk:.2f}€."
    )
    db.table("daily_briefs").upsert({
        "store_id": store_id,
        "date": today.isoformat(),
        "summary": summary,
        "value_at_risk": round(value_at_risk, 2),
        "actions_count": len(pending_list),
        "critical_count": len(critical),
    }, on_conflict="store_id,date").execute()


def reset(store_id: str = STORE_ID) -> None:
    """Vuelve al estado inicial: re-ejecuta seed."""
    from backend.data.seed import run as seed_run
    print("[advance_demo] Reiniciando estado del Super Martínez...")
    seed_run()
    print("[advance_demo] Reset completado — datos de hoy cargados.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Avanza el tiempo de la demo de MermaOps")
    parser.add_argument("--days", type=float, default=1.0, help="Días a avanzar (puede ser decimal)")
    parser.add_argument("--reset", action="store_true", help="Vuelve al estado inicial (re-seed)")
    parser.add_argument("--no-brief", action="store_true", help="No genera brief del día simulado")
    parser.add_argument("--store", default=STORE_ID, help="ID de la tienda")
    args = parser.parse_args()

    if args.reset:
        reset(args.store)
    else:
        advance(args.days, store_id=args.store, generate_brief=not args.no_brief)


if __name__ == "__main__":
    main()
