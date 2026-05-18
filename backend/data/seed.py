"""
Seed — datos demo realistas del Super Martinez.
Ejecutar una vez después de aplicar el schema en Supabase:
  python -m backend.data.seed
"""
from datetime import date, timedelta
from backend.core.database import get_db

STORE_ID = "demo-store-001"


def run():
    db = get_db()

    # ── Productos ────────────────────────────────────────────────────────────
    products = [
        # Panadería — Pasillo 1
        {"id": "p-001", "store_id": STORE_ID, "name": "Baguette artesana", "barcode": "8410001000001",
         "category": "panaderia", "price": 1.20, "cost": 0.45, "pasillo": "1", "estanteria": "1", "nivel": "1",
         "alert_days_1": 1, "alert_days_2": 1},
        {"id": "p-002", "store_id": STORE_ID, "name": "Pan de molde integral 500g", "barcode": "8410001000002",
         "category": "panaderia", "price": 1.85, "cost": 0.70, "pasillo": "1", "estanteria": "1", "nivel": "2",
         "alert_days_1": 3, "alert_days_2": 1},
        {"id": "p-003", "store_id": STORE_ID, "name": "Croissant mantequilla x4", "barcode": "8410001000003",
         "category": "panaderia", "price": 2.40, "cost": 0.90, "pasillo": "1", "estanteria": "2", "nivel": "1",
         "alert_days_1": 2, "alert_days_2": 1},

        # Lácteos — Pasillo 2
        {"id": "p-004", "store_id": STORE_ID, "name": "Yogur natural Danone x4", "barcode": "8410031001001",
         "category": "lacteos", "price": 1.60, "cost": 0.65, "pasillo": "2", "estanteria": "3", "nivel": "1",
         "alert_days_1": 5, "alert_days_2": 2},
        {"id": "p-005", "store_id": STORE_ID, "name": "Nata fresca 200ml", "barcode": "8410031001002",
         "category": "lacteos", "price": 1.95, "cost": 0.80, "pasillo": "2", "estanteria": "2", "nivel": "2",
         "alert_days_1": 5, "alert_days_2": 2},
        {"id": "p-006", "store_id": STORE_ID, "name": "Queso fresco Burgos 250g", "barcode": "8410031001003",
         "category": "lacteos", "price": 2.10, "cost": 0.95, "pasillo": "2", "estanteria": "1", "nivel": "1",
         "alert_days_1": 7, "alert_days_2": 3},
        {"id": "p-007", "store_id": STORE_ID, "name": "Leche fresca entera 1L", "barcode": "8410031001004",
         "category": "lacteos", "price": 1.20, "cost": 0.55, "pasillo": "2", "estanteria": "4", "nivel": "1",
         "alert_days_1": 5, "alert_days_2": 2},

        # Carne — Pasillo 3
        {"id": "p-008", "store_id": STORE_ID, "name": "Carne picada mixta 500g", "barcode": "8410031002001",
         "category": "carne", "price": 4.20, "cost": 2.10, "pasillo": "3", "estanteria": "1", "nivel": "1",
         "alert_days_1": 3, "alert_days_2": 1},
        {"id": "p-009", "store_id": STORE_ID, "name": "Pechuga de pollo 600g", "barcode": "8410031002002",
         "category": "carne", "price": 5.80, "cost": 2.90, "pasillo": "3", "estanteria": "2", "nivel": "1",
         "alert_days_1": 3, "alert_days_2": 1},
        {"id": "p-010", "store_id": STORE_ID, "name": "Lomo de cerdo filetes 400g", "barcode": "8410031002003",
         "category": "carne", "price": 6.50, "cost": 3.20, "pasillo": "3", "estanteria": "1", "nivel": "2",
         "alert_days_1": 4, "alert_days_2": 2},

        # Pescadería — Pasillo 4
        {"id": "p-011", "store_id": STORE_ID, "name": "Merluza en rodajas 500g", "barcode": "8410031003001",
         "category": "pescado", "price": 7.90, "cost": 4.20, "pasillo": "4", "estanteria": "1", "nivel": "1",
         "alert_days_1": 2, "alert_days_2": 1},
        {"id": "p-012", "store_id": STORE_ID, "name": "Salmon ahumado 100g", "barcode": "8410031003002",
         "category": "pescado", "price": 3.50, "cost": 1.80, "pasillo": "4", "estanteria": "2", "nivel": "1",
         "alert_days_1": 7, "alert_days_2": 3},

        # Frutas y verduras — Pasillo 5
        {"id": "p-013", "store_id": STORE_ID, "name": "Fresas bandeja 500g", "barcode": "8410031004001",
         "category": "fruta", "price": 2.80, "cost": 1.10, "pasillo": "5", "estanteria": "1", "nivel": "1",
         "alert_days_1": 3, "alert_days_2": 1},
        {"id": "p-014", "store_id": STORE_ID, "name": "Ensalada bolsa 200g", "barcode": "8410031004002",
         "category": "verdura", "price": 1.90, "cost": 0.75, "pasillo": "5", "estanteria": "2", "nivel": "1",
         "alert_days_1": 4, "alert_days_2": 2},
    ]

    for p in products:
        db.table("products").upsert(p, on_conflict="id").execute()

    today = date.today()

    # ── Lotes — vencimientos próximos realistas ──────────────────────────────
    batches = [
        # Críticos — vencen hoy o mañana
        {"id": "b-001", "store_id": STORE_ID, "product_id": "p-001",
         "expiry_date": today.isoformat(), "quantity": 8, "status": "active"},
        {"id": "b-002", "store_id": STORE_ID, "product_id": "p-004",
         "expiry_date": (today + timedelta(days=1)).isoformat(), "quantity": 18, "status": "active"},
        {"id": "b-003", "store_id": STORE_ID, "product_id": "p-008",
         "expiry_date": (today + timedelta(days=1)).isoformat(), "quantity": 12, "status": "active"},

        # Urgentes — 2-3 días
        {"id": "b-004", "store_id": STORE_ID, "product_id": "p-005",
         "expiry_date": (today + timedelta(days=2)).isoformat(), "quantity": 9, "status": "active"},
        {"id": "b-005", "store_id": STORE_ID, "product_id": "p-009",
         "expiry_date": (today + timedelta(days=2)).isoformat(), "quantity": 6, "status": "active"},
        {"id": "b-006", "store_id": STORE_ID, "product_id": "p-011",
         "expiry_date": (today + timedelta(days=2)).isoformat(), "quantity": 4, "status": "active"},
        {"id": "b-007", "store_id": STORE_ID, "product_id": "p-003",
         "expiry_date": (today + timedelta(days=3)).isoformat(), "quantity": 15, "status": "active"},

        # Esta semana
        {"id": "b-008", "store_id": STORE_ID, "product_id": "p-006",
         "expiry_date": (today + timedelta(days=4)).isoformat(), "quantity": 11, "status": "active"},
        {"id": "b-009", "store_id": STORE_ID, "product_id": "p-013",
         "expiry_date": (today + timedelta(days=4)).isoformat(), "quantity": 20, "status": "active"},
        {"id": "b-010", "store_id": STORE_ID, "product_id": "p-010",
         "expiry_date": (today + timedelta(days=5)).isoformat(), "quantity": 8, "status": "active"},
        {"id": "b-011", "store_id": STORE_ID, "product_id": "p-007",
         "expiry_date": (today + timedelta(days=5)).isoformat(), "quantity": 24, "status": "active"},
        {"id": "b-012", "store_id": STORE_ID, "product_id": "p-014",
         "expiry_date": (today + timedelta(days=6)).isoformat(), "quantity": 14, "status": "active"},
        {"id": "b-013", "store_id": STORE_ID, "product_id": "p-002",
         "expiry_date": (today + timedelta(days=7)).isoformat(), "quantity": 22, "status": "active"},
        {"id": "b-014", "store_id": STORE_ID, "product_id": "p-012",
         "expiry_date": (today + timedelta(days=7)).isoformat(), "quantity": 7, "status": "active"},
    ]

    for b in batches:
        db.table("batches").upsert(b, on_conflict="id").execute()

    # ── Stock almacén ─────────────────────────────────────────────────────────
    warehouse = [
        {"store_id": STORE_ID, "product_id": "p-001", "quantity": 0},
        {"store_id": STORE_ID, "product_id": "p-002", "quantity": 12},
        {"store_id": STORE_ID, "product_id": "p-003", "quantity": 8},
        {"store_id": STORE_ID, "product_id": "p-004", "quantity": 0},
        {"store_id": STORE_ID, "product_id": "p-005", "quantity": 6},
        {"store_id": STORE_ID, "product_id": "p-006", "quantity": 10},
        {"store_id": STORE_ID, "product_id": "p-007", "quantity": 48},
        {"store_id": STORE_ID, "product_id": "p-008", "quantity": 0},
        {"store_id": STORE_ID, "product_id": "p-009", "quantity": 4},
        {"store_id": STORE_ID, "product_id": "p-010", "quantity": 6},
        {"store_id": STORE_ID, "product_id": "p-011", "quantity": 0},
        {"store_id": STORE_ID, "product_id": "p-012", "quantity": 15},
        {"store_id": STORE_ID, "product_id": "p-013", "quantity": 0},
        {"store_id": STORE_ID, "product_id": "p-014", "quantity": 20},
    ]

    for w in warehouse:
        db.table("warehouse_stock").upsert(
            w, on_conflict="store_id,product_id"
        ).execute()

    # ── Proveedores ────────────────────────────────────────────────────────────
    suppliers = [
        {"id": "sup-001", "store_id": STORE_ID, "name": "Horno San Luis",
         "contact": "jose@hornosanluis.es"},
        {"id": "sup-002", "store_id": STORE_ID, "name": "Frigoríficos del Norte S.L.",
         "contact": "ventas@frigorificosnorte.es"},
        {"id": "sup-003", "store_id": STORE_ID, "name": "Distribuciones Frescas S.L.",
         "contact": "pedidos@distfrescas.es"},
        {"id": "sup-004", "store_id": STORE_ID, "name": "Lácteos Cantabria",
         "contact": "comercial@lacteoscantabria.es"},
    ]
    for s in suppliers:
        db.table("suppliers").upsert(s, on_conflict="id").execute()

    # Merma histórica por proveedor (% sobre el total suministrado)
    supplier_merma = [
        # Horno San Luis — panadería (alta merma por perecedero diario)
        {"id": "sm-001", "store_id": STORE_ID, "supplier_id": "sup-001",
         "product_id": "p-001", "merma_pct": 18.5, "period": "2025-05"},
        {"id": "sm-002", "store_id": STORE_ID, "supplier_id": "sup-001",
         "product_id": "p-002", "merma_pct": 8.2, "period": "2025-05"},
        {"id": "sm-003", "store_id": STORE_ID, "supplier_id": "sup-001",
         "product_id": "p-003", "merma_pct": 22.1, "period": "2025-05"},
        # Frigoríficos del Norte — carne y pescado
        {"id": "sm-004", "store_id": STORE_ID, "supplier_id": "sup-002",
         "product_id": "p-008", "merma_pct": 12.3, "period": "2025-05"},
        {"id": "sm-005", "store_id": STORE_ID, "supplier_id": "sup-002",
         "product_id": "p-009", "merma_pct": 9.7, "period": "2025-05"},
        {"id": "sm-006", "store_id": STORE_ID, "supplier_id": "sup-002",
         "product_id": "p-010", "merma_pct": 7.4, "period": "2025-05"},
        {"id": "sm-007", "store_id": STORE_ID, "supplier_id": "sup-002",
         "product_id": "p-011", "merma_pct": 15.8, "period": "2025-05"},
        {"id": "sm-008", "store_id": STORE_ID, "supplier_id": "sup-002",
         "product_id": "p-012", "merma_pct": 6.2, "period": "2025-05"},
        # Distribuciones Frescas — frutas y verduras
        {"id": "sm-009", "store_id": STORE_ID, "supplier_id": "sup-003",
         "product_id": "p-013", "merma_pct": 24.6, "period": "2025-05"},
        {"id": "sm-010", "store_id": STORE_ID, "supplier_id": "sup-003",
         "product_id": "p-014", "merma_pct": 11.3, "period": "2025-05"},
        # Lácteos Cantabria
        {"id": "sm-011", "store_id": STORE_ID, "supplier_id": "sup-004",
         "product_id": "p-004", "merma_pct": 7.8, "period": "2025-05"},
        {"id": "sm-012", "store_id": STORE_ID, "supplier_id": "sup-004",
         "product_id": "p-005", "merma_pct": 9.1, "period": "2025-05"},
        {"id": "sm-013", "store_id": STORE_ID, "supplier_id": "sup-004",
         "product_id": "p-006", "merma_pct": 5.6, "period": "2025-05"},
        {"id": "sm-014", "store_id": STORE_ID, "supplier_id": "sup-004",
         "product_id": "p-007", "merma_pct": 4.3, "period": "2025-05"},
    ]
    for sm in supplier_merma:
        db.table("supplier_merma").upsert(sm, on_conflict="id").execute()

    print(
        f"Seed completado: {len(products)} productos, {len(batches)} lotes, "
        f"{len(warehouse)} almacén, {len(suppliers)} proveedores"
    )

    # Crear acciones demo y brief de hoy
    from backend.data.demo_actions import run as seed_actions
    seed_actions()


if __name__ == "__main__":
    run()
