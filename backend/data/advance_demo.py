"""
advance_demo.py — Simulación temporal para la defensa del TFM.

Avanza N días en la base de datos Supabase: actualiza caducidades, crea acciones
urgentes, completa acciones viejas y garantiza distribución realista de riesgo.
Permite mostrar en 10 segundos lo que en un super real tardaría días.

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
from datetime import date, datetime, timedelta

from backend.core.database import get_db

STORE_ID = "demo-store-001"

# Empleados ficticios
_EMPLOYEES = ["carlos@supermarinez.es", "ana@supermarinez.es", "luis@supermarinez.es"]

# Distribución de riesgo garantizada tras advance
_MIN_CRITICO = 2   # expiry ≤ 1 día
_MIN_ALTO = 3      # expiry 2-3 días
_MIN_BAJO = 4      # expiry 4-7 días


def advance(days: float, store_id: str = STORE_ID, generate_brief: bool = True) -> dict:
    """
    Avanza N días en la BD. Devuelve resumen de cambios.
    días puede ser decimal (0.5 = medio día).
    """
    db = get_db()
    today = date.today()
    delta = timedelta(days=days)
    result = {"days": days, "batches_updated": 0, "actions_created": 0,
              "actions_completed": 0, "brief_generated": False}

    # 1. Actualizar fechas de caducidad de batches activos
    batches = db.table("batches").select("*").eq("store_id", store_id).eq("status", "active").execute()
    updated = 0
    for batch in (batches.data or []):
        old_date = date.fromisoformat(batch["expiry_date"])
        new_date = old_date - delta
        new_status = "active"
        if new_date < today:
            new_status = "sold"  # caducó — marcar como vendido/retirado
        db.table("batches").update({
            "expiry_date": new_date.isoformat(),
            "status": new_status,
        }).eq("id", batch["id"]).execute()
        updated += 1
    result["batches_updated"] = updated

    # 2. Marcar algunas acciones pending como completadas (simula trabajo del personal)
    pending = db.table("actions").select("*").eq("store_id", store_id).eq("status", "pending").execute()
    pending_list = pending.data or []
    # Completar ~60% de las acciones que NO sean CRÍTICO (score < 85)
    to_complete = [a for a in pending_list if (a.get("priority_score") or 0) < 85]
    n_complete = max(0, int(len(to_complete) * 0.6))
    completed = 0
    for action in random.sample(to_complete, n_complete):
        emp = random.choice(_EMPLOYEES)
        db.table("actions").update({
            "status": "completed",
            "completed_by": emp,
            "completed_at": (datetime.now() - timedelta(hours=random.randint(1, int(days * 12) + 1))).isoformat(),
            "notes": (action.get("notes") or "") + " — Acción completada por el equipo.",
        }).eq("id", action["id"]).execute()
        completed += 1
    result["actions_completed"] = completed

    # 3. Obtener batches actualizados y crear acciones para los nuevos urgentes
    fresh = db.table("batches").select("*, products(*)").eq("store_id", store_id).eq("status", "active").execute()
    existing_pending = {
        a["batch_id"] for a in (db.table("actions").select("batch_id")
                                 .eq("store_id", store_id).eq("status", "pending").execute().data or [])
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
            action_type, score, pct, note = "retirar", 100, 0, "Caduca HOY — retirar del lineal inmediatamente."
            new_price = 0.0
        elif days_left == 1:
            action_type, score, pct = "rebajar", 92, 50
            new_price = max(round(price_val * 0.50, 2), round(cost * 1.05, 2))
            note = f"Caduca mañana — rebajar a {new_price}€ (−50%)."
        elif days_left <= 3:
            action_type, score, pct = "rebajar", 75, 30
            new_price = max(round(price_val * 0.70, 2), round(cost * 1.05, 2))
            note = f"Caduca en {days_left}d — rebajar a {new_price}€ (−30%)."
        else:
            continue  # no urgente

        # Sugerir donación si hay exceso de stock (qty >= 5 y caduca hoy/mañana)
        if qty >= 5 and days_left <= 1:
            note += f" Con {qty} uds en stock, considera donar parte al banco de alimentos."

        import uuid
        action_id = f"adv-{uuid.uuid4().hex[:8]}"
        db.table("actions").upsert({
            "id": action_id,
            "store_id": store_id,
            "batch_id": batch["id"],
            "action_type": action_type,
            "priority_score": score,
            "price_adjustment_pct": pct,
            "new_price": new_price if action_type != "retirar" else None,
            "status": "pending",
            "notes": note,
        }, on_conflict="id").execute()
        created += 1

    result["actions_created"] = created

    # 4. Garantizar distribución mínima de riesgo para la demo
    _ensure_risk_distribution(db, store_id, today)

    # 5. Generar brief del nuevo "día simulado"
    if generate_brief:
        try:
            _generate_simulated_brief(db, store_id, today, days)
            result["brief_generated"] = True
        except Exception:
            pass

    print(
        f"[advance_demo] +{days}d → "
        f"{result['batches_updated']} lotes, "
        f"{result['actions_created']} acciones nuevas, "
        f"{result['actions_completed']} completadas"
    )
    return result


def _ensure_risk_distribution(db, store_id: str, today: date) -> None:
    """
    Garantiza que siempre hay al menos CRÍTICO/ALTO/BAJO visibles en el dashboard.
    Si faltan, activa batches del almacén y los pone con caducidad ajustada.
    """
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

    # Traer productos del almacén si faltan niveles de riesgo
    warehouse = db.table("warehouse_stock").select("*, products(*)").eq("store_id", store_id).gte("quantity", 1).execute()
    pool = list(warehouse.data or [])
    random.shuffle(pool)

    import uuid as _uuid
    refill_targets = []
    if counts["critico"] < _MIN_CRITICO:
        refill_targets.extend([(0, _MIN_CRITICO - counts["critico"])])
    if counts["alto"] < _MIN_ALTO:
        refill_targets.extend([(2, _MIN_ALTO - counts["alto"])])
    if counts["bajo"] < _MIN_BAJO:
        refill_targets.extend([(5, _MIN_BAJO - counts["bajo"])])

    used = 0
    for days_offset, needed in refill_targets:
        for _ in range(needed):
            if used >= len(pool):
                break
            item = pool[used]
            used += 1
            product = item.get("products") or {}
            new_batch_id = f"sim-{_uuid.uuid4().hex[:8]}"
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
    """Vuelve al estado inicial: re-ejecuta seed + demo_actions."""
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
