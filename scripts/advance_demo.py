"""
advance_demo.py — Simula el paso del tiempo para la demo.

Resta N días a todas las fechas de caducidad de los lotes activos,
recalcula urgencias, crea acciones nuevas para los ahora críticos.

Uso:
    python scripts/advance_demo.py --days=1
    python scripts/advance_demo.py --days=2 --brief
    python scripts/advance_demo.py --reset
"""
import argparse
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from backend.core import database

STORE_ID = os.getenv("STORE_ID", "demo-store-001")

_ORIGINAL_DATES: dict[str, str] = {}


def _score_for_days(days_left: int) -> int:
    if days_left < 0:
        return 100
    if days_left == 0:
        return 100
    if days_left == 1:
        return 90
    if days_left == 2:
        return 75
    if days_left <= 4:
        return 55
    return 30


def _action_type_for_days(days_left: int, product_name: str = "") -> str:
    name_lower = (product_name or "").lower()
    if days_left < 0:
        return "retirar"
    if days_left == 0:
        if any(k in name_lower for k in ["salmon", "carne", "pescado", "marisco"]):
            return "retirar"
        return "donar"
    if days_left <= 2:
        return "rebajar"
    return "revisar"


def advance_days(days: int, run_brief: bool = False) -> dict:
    db = database.get_db()
    today = date.today()

    batches = (
        db.table("batches")
        .select("id, expiry_date, product_id, quantity, products(name, price, cost)")
        .eq("store_id", STORE_ID)
        .eq("status", "active")
        .execute()
    )

    updated = []
    newly_critical = []
    newly_high = []

    for b in batches.data or []:
        old_date = date.fromisoformat(b["expiry_date"])
        new_date = old_date - timedelta(days=days)
        db.table("batches").update({"expiry_date": new_date.isoformat()}).eq("id", b["id"]).execute()

        days_left = (new_date - today).days
        old_days_left = (old_date - today).days
        urgency = (
            "CRITICO" if days_left <= 0 else
            "ALTO" if days_left <= 2 else
            "MEDIO" if days_left <= 5 else
            "BAJO"
        )
        product = b.get("products") or {}
        updated.append({
            "id": b["id"],
            "product": product.get("name", b["product_id"]),
            "old_date": old_date.isoformat(),
            "new_date": new_date.isoformat(),
            "days_left": days_left,
            "urgency": urgency,
        })

        # Crear acción nueva si cruzó a CRÍTICO/ALTO y no había antes
        if old_days_left > 2 and days_left <= 2:
            atype = _action_type_for_days(days_left, product.get("name", ""))
            score = _score_for_days(days_left)
            price = product.get("price", 0) or 0
            cost = product.get("cost", 0) or 0
            new_price = round(price * 0.5, 2) if atype == "rebajar" else None
            action = {
                "id": f"auto-{b['id']}-{today.isoformat()}",
                "store_id": STORE_ID,
                "batch_id": b["id"],
                "action_type": atype,
                "priority_score": score,
                "status": "pending",
                "notes": f"Generado automáticamente: caduca en {days_left} día(s)",
            }
            if new_price:
                action["new_price"] = new_price
                action["price_adjustment_pct"] = -50
            try:
                db.table("actions").upsert(action, on_conflict="id").execute()
                if days_left <= 0:
                    newly_critical.append(product.get("name", b["id"]))
                else:
                    newly_high.append(product.get("name", b["id"]))
            except Exception:
                pass

    result = {
        "days_advanced": days,
        "batches_updated": len(updated),
        "newly_critical": newly_critical,
        "newly_high": newly_high,
        "batches": updated,
    }

    if run_brief:
        try:
            from backend.agents import supervisor
            summary = supervisor.run_daily_brief(STORE_ID)
            result["brief_generated"] = True
            result["brief_summary"] = summary[:500]
        except Exception as e:
            result["brief_generated"] = False
            result["brief_error"] = str(e)

    return result


def reset_demo() -> dict:
    """Vuelve a las fechas base (hoy como referencia)."""
    db = database.get_db()
    today = date.today()

    original = {
        "sim-9a530599": today,
        "demo-a-53677049": today + timedelta(days=1),
        "sim-0ed54fbf": today + timedelta(days=1),
        "b-012": today + timedelta(days=2),
        "b-014": today + timedelta(days=3),
        "b-013": today + timedelta(days=4),
    }

    for batch_id, new_date in original.items():
        db.table("batches").update({"expiry_date": new_date.isoformat()}).eq("id", batch_id).execute()

    # Limpiar acciones auto-generadas
    db.table("actions").delete().eq("store_id", STORE_ID).like("id", "auto-%").execute()

    return {"reset": True, "batches_restored": len(original)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Avanza el tiempo de la demo MermaOps")
    parser.add_argument("--days", type=int, default=1, help="Días a avanzar")
    parser.add_argument("--brief", action="store_true", help="Generar brief tras avanzar")
    parser.add_argument("--reset", action="store_true", help="Volver a fechas base")
    args = parser.parse_args()

    if args.reset:
        r = reset_demo()
        print(f"Reset completado: {r['batches_restored']} lotes restaurados.")
    else:
        print(f"Avanzando {args.days} dia(s)...")
        r = advance_days(args.days, run_brief=args.brief)
        print(f"\n{r['batches_updated']} lotes actualizados:")
        for b in r["batches"]:
            print(f"  [{b['urgency']:7}] {b['product'][:30]:30} {b['old_date']} -> {b['new_date']} ({b['days_left']} dias)")
        if r["newly_critical"]:
            print(f"\nNuevos CRITICOS: {', '.join(r['newly_critical'])}")
        if r["newly_high"]:
            print(f"Nuevos ALTOS: {', '.join(r['newly_high'])}")
