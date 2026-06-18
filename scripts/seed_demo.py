"""
seed_demo.py — Datos demo realistas para MermaOps.

Limpia lotes activos e inserta batches con distribución realista de caducidades.
También inserta merma_log (últimos 7 días) para que el área chart del dashboard
muestre datos reales, y donations para que aparezca el impact card.

Uso:
    python scripts/seed_demo.py
    python scripts/seed_demo.py --dry-run
"""
import argparse
import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()

try:
    from supabase import create_client
except ImportError:
    print("ERROR: pip install supabase")
    sys.exit(1)

TODAY = date.today()   # siempre relativo a la fecha real de ejecución


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def past(days: int) -> str:
    return (TODAY - timedelta(days=days)).isoformat()


STORE_ID = "demo-store-001"

# 28 lotes con distribución realista
BATCHES = [
    # ── CRÍTICOS — hoy/mañana ────────────────────────────────────────────────
    {"product_id": "p-013", "expiry_date": d(0),  "quantity": 8,  "status": "active"},
    {"product_id": "p-008", "expiry_date": d(0),  "quantity": 4,  "status": "active"},
    {"product_id": "p-011", "expiry_date": d(1),  "quantity": 5,  "status": "active"},
    # ── URGENTES — 2-4 días ──────────────────────────────────────────────────
    {"product_id": "p-001", "expiry_date": d(2),  "quantity": 12, "status": "active"},
    {"product_id": "p-004", "expiry_date": d(2),  "quantity": 15, "status": "active"},
    {"product_id": "p-014", "expiry_date": d(3),  "quantity": 10, "status": "active"},
    {"product_id": "p-005", "expiry_date": d(3),  "quantity": 6,  "status": "active"},
    {"product_id": "p-009", "expiry_date": d(4),  "quantity": 8,  "status": "active"},
    # ── MEDIOS — 5-10 días ───────────────────────────────────────────────────
    {"product_id": "p-002", "expiry_date": d(5),  "quantity": 20, "status": "active"},
    {"product_id": "p-006", "expiry_date": d(6),  "quantity": 12, "status": "active"},
    {"product_id": "p-003", "expiry_date": d(6),  "quantity": 8,  "status": "active"},
    {"product_id": "p-010", "expiry_date": d(7),  "quantity": 10, "status": "active"},
    {"product_id": "p-007", "expiry_date": d(8),  "quantity": 25, "status": "active"},
    {"product_id": "p-012", "expiry_date": d(9),  "quantity": 6,  "status": "active"},
    {"product_id": "p-013", "expiry_date": d(9),  "quantity": 15, "status": "active"},
    # ── NORMALES — 11-20 días ────────────────────────────────────────────────
    {"product_id": "p-001", "expiry_date": d(11), "quantity": 30, "status": "active"},
    {"product_id": "p-004", "expiry_date": d(12), "quantity": 24, "status": "active"},
    {"product_id": "p-002", "expiry_date": d(13), "quantity": 18, "status": "active"},
    {"product_id": "p-007", "expiry_date": d(15), "quantity": 40, "status": "active"},
    {"product_id": "p-011", "expiry_date": d(16), "quantity": 12, "status": "active"},
    {"product_id": "p-006", "expiry_date": d(17), "quantity": 16, "status": "active"},
    {"product_id": "p-009", "expiry_date": d(18), "quantity": 20, "status": "active"},
    {"product_id": "p-003", "expiry_date": d(19), "quantity": 24, "status": "active"},
    # ── FRESCOS — 21+ días ───────────────────────────────────────────────────
    {"product_id": "p-012", "expiry_date": d(26), "quantity": 30, "status": "active"},
    {"product_id": "p-010", "expiry_date": d(29), "quantity": 15, "status": "active"},
    {"product_id": "p-005", "expiry_date": d(31), "quantity": 20, "status": "active"},
    {"product_id": "p-014", "expiry_date": d(33), "quantity": 25, "status": "active"},
    {"product_id": "p-008", "expiry_date": d(36), "quantity": 18, "status": "active"},
]

# Merma registrada los últimos 7 días (para el área chart del dashboard)
MERMA_LOGS = [
    {"date": past(6), "value_lost": 47.20, "quantity_lost": 6,  "reason": "caducidad"},
    {"date": past(5), "value_lost": 23.80, "quantity_lost": 4,  "reason": "caducidad"},
    {"date": past(4), "value_lost": 61.50, "quantity_lost": 8,  "reason": "caducidad"},
    {"date": past(3), "value_lost": 18.90, "quantity_lost": 3,  "reason": "caducidad"},
    {"date": past(3), "value_lost": 34.00, "quantity_lost": 5,  "reason": "caducidad"},
    {"date": past(2), "value_lost": 12.40, "quantity_lost": 2,  "reason": "caducidad"},
    {"date": past(1), "value_lost": 55.60, "quantity_lost": 7,  "reason": "caducidad"},
    {"date": past(1), "value_lost": 28.75, "quantity_lost": 4,  "reason": "caducidad"},
    {"date": past(0), "value_lost": 9.30,  "quantity_lost": 1,  "reason": "caducidad"},
]

# Donaciones recientes (para el impact card)
DONATIONS = [
    {"quantity": 8,  "value_donated": 14.40, "entity": "Banco de Alimentos Madrid", "donated_at": f"{past(5)}T10:30:00"},
    {"quantity": 12, "value_donated": 8.76,  "entity": "Cruz Roja",                  "donated_at": f"{past(4)}T09:15:00"},
    {"quantity": 5,  "value_donated": 18.50, "entity": "Banco de Alimentos Madrid",  "donated_at": f"{past(3)}T11:00:00"},
    {"quantity": 10, "value_donated": 5.90,  "entity": "Cáritas",                    "donated_at": f"{past(2)}T08:45:00"},
    {"quantity": 4,  "value_donated": 11.20, "entity": "Cruz Roja",                  "donated_at": f"{past(1)}T16:20:00"},
]


def main(dry_run: bool = False) -> None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL y SUPABASE_SERVICE_KEY requeridos en .env")
        sys.exit(1)

    sb = create_client(url, key)

    print(f"{'[DRY RUN] ' if dry_run else ''}MermaOps Demo Seed — {STORE_ID}")
    print(f"Fecha referencia: {TODAY.isoformat()}\n")

    # 1. Lotes: marcar activos anteriores como sold
    existing = sb.table("batches").select("id").eq("store_id", STORE_ID).eq("status", "active").execute()
    if existing.data:
        ids = [r["id"] for r in existing.data]
        print(f"Marcando {len(ids)} lotes activos como 'sold'...")
        if not dry_run:
            sb.table("batches").update({"status": "sold"}).in_("id", ids).execute()

    for b in BATCHES:
        b["store_id"] = STORE_ID

    criticos = [b for b in BATCHES if (date.fromisoformat(b["expiry_date"]) - TODAY).days <= 1]
    urgentes = [b for b in BATCHES if 2 <= (date.fromisoformat(b["expiry_date"]) - TODAY).days <= 4]
    medios   = [b for b in BATCHES if 5 <= (date.fromisoformat(b["expiry_date"]) - TODAY).days <= 10]
    normales = [b for b in BATCHES if 11 <= (date.fromisoformat(b["expiry_date"]) - TODAY).days <= 20]
    frescos  = [b for b in BATCHES if (date.fromisoformat(b["expiry_date"]) - TODAY).days > 20]

    print(f"Insertando {len(BATCHES)} lotes:")
    print(f"  [!!] Criticos  (0-1d):   {len(criticos)}")
    print(f"  [!]  Urgentes  (2-4d):   {len(urgentes)}")
    print(f"  [~]  Medios    (5-10d):  {len(medios)}")
    print(f"  [ok] Normales  (11-20d): {len(normales)}")
    print(f"  [ok] Frescos   (21+d):   {len(frescos)}")

    if not dry_run:
        result = sb.table("batches").insert(BATCHES).execute()
        print(f"  -> {len(result.data)} lotes insertados\n")

    # 2. Merma log: limpiar últimos 30 días y reinsertar
    cutoff = past(30)
    existing_logs = sb.table("merma_log").select("id").eq("store_id", STORE_ID).gte("date", cutoff).execute()
    if existing_logs.data:
        ids = [r["id"] for r in existing_logs.data]
        print(f"Eliminando {len(ids)} entradas de merma_log recientes...")
        if not dry_run:
            sb.table("merma_log").delete().in_("id", ids).execute()

    for m in MERMA_LOGS:
        m["store_id"] = STORE_ID

    total_merma = sum(m["value_lost"] for m in MERMA_LOGS)
    print(f"Insertando {len(MERMA_LOGS)} entradas merma_log (total: {total_merma:.2f} €)")
    if not dry_run:
        sb.table("merma_log").insert(MERMA_LOGS).execute()
        print("  -> OK\n")

    # 3. Donations: limpiar recientes y reinsertar
    existing_don = sb.table("donations").select("id").eq("store_id", STORE_ID).gte("donated_at", f"{cutoff}T00:00:00").execute()
    if existing_don.data:
        ids = [r["id"] for r in existing_don.data]
        print(f"Eliminando {len(ids)} donaciones recientes...")
        if not dry_run:
            sb.table("donations").delete().in_("id", ids).execute()

    for don in DONATIONS:
        don["store_id"] = STORE_ID

    total_don = sum(d["quantity"] for d in DONATIONS)
    total_val = sum(d["value_donated"] for d in DONATIONS)
    print(f"Insertando {len(DONATIONS)} donaciones ({total_don} uds · {total_val:.2f} € · deducción 35% = {total_val*0.35:.2f} €)")
    if not dry_run:
        sb.table("donations").insert(DONATIONS).execute()
        print("  -> OK\n")

    # 4. Limpiar acciones pendientes viejas (fechas expiradas)
    old_actions = sb.table("actions").select("id").eq("store_id", STORE_ID).eq("status", "pending").execute()
    if old_actions.data:
        ids = [r["id"] for r in old_actions.data]
        print(f"Eliminando {len(ids)} acciones pendientes antiguas (se regenerarán con los nuevos lotes)...")
        if not dry_run:
            sb.table("actions").update({"status": "cancelled"}).in_("id", ids).execute()

    if not dry_run:
        print("\n✓ Seed completado.")
        print(f"  Batches:    {len(BATCHES)} (criticos={len(criticos)}, urgentes={len(urgentes)})")
        print(f"  Merma 7d:   {total_merma:.2f} €")
        print(f"  Donaciones: {total_don} uds, {total_val:.2f} € donados")
        print("\nArranca el backend para que Kuine regenere las acciones:")
        print("  make start   (o python -m uvicorn backend.main:app --port 8001)")
    else:
        print("\n[DRY RUN] Nada insertado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
