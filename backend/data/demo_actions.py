"""
Demo data — acciones, merma, donaciones, historial y brief de ejemplo.
Se ejecuta después del seed principal.
  python -m backend.data.demo_actions
"""
from datetime import date, timedelta, datetime
from backend.core.database import get_db

STORE_ID = "demo-store-001"

# Empleados ficticios del Súper Martínez — se usan emails igual que la app real
EMPLOYEES = {
    "emp-001": "carlos@supermarinez.es",
    "emp-002": "ana@supermarinez.es",
    "emp-003": "luis@supermarinez.es",
}


def run():
    db = get_db()
    today = date.today()

    # ── Acciones pendientes ────────────────────────────────────────────────────
    pending_actions = [
        # Críticas — score >= 85
        {
            "id": "action-001",
            "store_id": STORE_ID,
            "batch_id": "b-001",
            "action_type": "rebajar",
            "priority_score": 100,
            "price_adjustment_pct": 60,
            "new_price": 0.48,
            "status": "pending",
            "notes": "Caduca HOY. Pasillo 1 — E1 N1. Colocar etiqueta de descuento urgente.",
        },
        {
            "id": "action-002",
            "store_id": STORE_ID,
            "batch_id": "b-003",
            "action_type": "rebajar",
            "priority_score": 92,
            "price_adjustment_pct": 50,
            "new_price": 2.10,
            "status": "pending",
            "notes": "Caduca mañana. Pasillo 3 — E1 N1. Cambiar etiqueta de precio.",
        },
        {
            "id": "action-003",
            "store_id": STORE_ID,
            "batch_id": "b-002",
            "action_type": "rebajar",
            "priority_score": 88,
            "price_adjustment_pct": 40,
            "new_price": 0.96,
            "status": "pending",
            "notes": "Caduca mañana. 18 unidades en tienda. Pasillo 2 — E3 N1.",
        },
        # Urgentes — 65-84
        {
            "id": "action-004",
            "store_id": STORE_ID,
            "batch_id": "b-006",
            "action_type": "rebajar",
            "priority_score": 78,
            "price_adjustment_pct": 40,
            "new_price": 4.74,
            "status": "pending",
            "notes": "2 días para caducar. Pasillo 4 — E1 N1. Prioridad alta.",
        },
        {
            "id": "action-005",
            "store_id": STORE_ID,
            "batch_id": "b-004",
            "action_type": "rebajar",
            "priority_score": 72,
            "price_adjustment_pct": 40,
            "new_price": 1.17,
            "status": "pending",
            "notes": "2 días para caducar. Pasillo 2 — E2 N2.",
        },
        {
            "id": "action-006",
            "store_id": STORE_ID,
            "batch_id": "b-005",
            "action_type": "rebajar",
            "priority_score": 70,
            "price_adjustment_pct": 40,
            "new_price": 3.48,
            "status": "pending",
            "notes": "2 días. 6 unidades. Pasillo 3 — E2 N1.",
        },
        # Media semana — 40-64
        {
            "id": "action-007",
            "store_id": STORE_ID,
            "batch_id": "b-007",
            "action_type": "rebajar",
            "priority_score": 55,
            "price_adjustment_pct": 30,
            "new_price": 1.68,
            "status": "pending",
            "notes": "3 días. 15 unidades. Pasillo 1 — E2 N1.",
        },
        {
            "id": "action-008",
            "store_id": STORE_ID,
            "batch_id": "b-009",
            "action_type": "rebajar",
            "priority_score": 50,
            "price_adjustment_pct": 20,
            "new_price": 2.24,
            "status": "pending",
            "notes": "4 días. 20 unidades. Pasillo 5 — E1 N1.",
        },
        {
            "id": "action-009",
            "store_id": STORE_ID,
            "batch_id": "b-008",
            "action_type": "revisar",
            "priority_score": 42,
            "price_adjustment_pct": 0,
            "status": "pending",
            "notes": "Revisar estado del queso fresco. 4 días. 11 unidades. Pasillo 2 — E1 N1.",
        },
    ]

    for action in pending_actions:
        db.table("actions").upsert(action, on_conflict="id").execute()

    # ── Acciones completadas — historial últimos 7 días ───────────────────────
    completed_actions = [
        {
            "id": "action-c001",
            "store_id": STORE_ID,
            "batch_id": "b-001",
            "action_type": "rebajar",
            "priority_score": 95,
            "price_adjustment_pct": 50,
            "new_price": 0.60,
            "status": "completed",
            "completed_by": EMPLOYEES["emp-001"],
            "completed_at": (datetime.now() - timedelta(days=1, hours=3)).isoformat(),
            "notes": "Rebajado al precio indicado. Etiqueta colocada.",
        },
        {
            "id": "action-c002",
            "store_id": STORE_ID,
            "batch_id": "b-002",
            "action_type": "rebajar",
            "priority_score": 88,
            "price_adjustment_pct": 40,
            "new_price": 0.96,
            "status": "completed",
            "completed_by": EMPLOYEES["emp-002"],
            "completed_at": (datetime.now() - timedelta(days=1, hours=1)).isoformat(),
            "notes": "18 yogures rebajados. Todo en orden.",
        },
        {
            "id": "action-c003",
            "store_id": STORE_ID,
            "batch_id": "b-003",
            "action_type": "retirar",
            "priority_score": 100,
            "price_adjustment_pct": 0,
            "status": "completed",
            "completed_by": EMPLOYEES["emp-001"],
            "completed_at": (datetime.now() - timedelta(days=2, hours=5)).isoformat(),
            "notes": "Carne retirada. Producto caducado ayer sin vender.",
        },
        {
            "id": "action-c004",
            "store_id": STORE_ID,
            "batch_id": "b-005",
            "action_type": "donar",
            "priority_score": 85,
            "price_adjustment_pct": 0,
            "status": "completed",
            "completed_by": EMPLOYEES["emp-003"],
            "completed_at": (datetime.now() - timedelta(days=2, hours=2)).isoformat(),
            "notes": "Donado a Cáritas — 4 uds pechuga pollo.",
            "donation_entity": "Cáritas",
            "donation_quantity": 4,
        },
        {
            "id": "action-c005",
            "store_id": STORE_ID,
            "batch_id": "b-006",
            "action_type": "rebajar",
            "priority_score": 80,
            "price_adjustment_pct": 35,
            "new_price": 5.14,
            "status": "completed",
            "completed_by": EMPLOYEES["emp-002"],
            "completed_at": (datetime.now() - timedelta(days=3, hours=4)).isoformat(),
            "notes": "Rebajado 35%. Vendido casi todo antes del cierre.",
        },
        {
            "id": "action-c006",
            "store_id": STORE_ID,
            "batch_id": "b-007",
            "action_type": "revisar",
            "priority_score": 45,
            "price_adjustment_pct": 0,
            "status": "completed",
            "completed_by": EMPLOYEES["emp-001"],
            "completed_at": (datetime.now() - timedelta(days=3, hours=1)).isoformat(),
            "notes": "Revisado. Estado correcto.",
        },
        {
            "id": "action-c007",
            "store_id": STORE_ID,
            "batch_id": "b-008",
            "action_type": "rebajar",
            "priority_score": 68,
            "price_adjustment_pct": 30,
            "new_price": 1.47,
            "status": "completed",
            "completed_by": EMPLOYEES["emp-003"],
            "completed_at": (datetime.now() - timedelta(days=4, hours=3)).isoformat(),
            "notes": "Queso rebajado. 7 unidades vendidas antes del mediodía.",
        },
        {
            "id": "action-c008",
            "store_id": STORE_ID,
            "batch_id": "b-009",
            "action_type": "rebajar",
            "priority_score": 55,
            "price_adjustment_pct": 20,
            "new_price": 2.24,
            "status": "completed",
            "completed_by": EMPLOYEES["emp-002"],
            "completed_at": (datetime.now() - timedelta(days=5, hours=2)).isoformat(),
            "notes": "Fresas rebajadas. Bien aceptadas por los clientes.",
        },
        {
            "id": "action-c009",
            "store_id": STORE_ID,
            "batch_id": "b-010",
            "action_type": "donar",
            "priority_score": 90,
            "price_adjustment_pct": 0,
            "status": "completed",
            "completed_by": EMPLOYEES["emp-001"],
            "completed_at": (datetime.now() - timedelta(days=5, hours=5)).isoformat(),
            "notes": "Donado a Banco de Alimentos de Madrid — 6 uds lomo cerdo.",
            "donation_entity": "Banco de Alimentos de Madrid",
            "donation_quantity": 6,
        },
        {
            "id": "action-c010",
            "store_id": STORE_ID,
            "batch_id": "b-011",
            "action_type": "retirar",
            "priority_score": 98,
            "price_adjustment_pct": 0,
            "status": "completed",
            "completed_by": EMPLOYEES["emp-003"],
            "completed_at": (datetime.now() - timedelta(days=6, hours=6)).isoformat(),
            "notes": "Leche fresca caducada retirada. 12 uds a merma.",
        },
    ]

    for action in completed_actions:
        db.table("actions").upsert(action, on_conflict="id").execute()

    # ── Donaciones ────────────────────────────────────────────────────────────
    donations = [
        {
            "id": "don-001",
            "store_id": STORE_ID,
            "batch_id": "b-005",
            "action_id": "action-c004",
            "entity": "Cáritas",
            "quantity": 4,
            "product_name": "Pechuga de pollo 600g",
            "value_donated": 23.20,
            "donated_by": EMPLOYEES["emp-003"],
            "donated_at": (datetime.now() - timedelta(days=2, hours=2)).isoformat(),
            "notes": "",
        },
        {
            "id": "don-002",
            "store_id": STORE_ID,
            "batch_id": "b-010",
            "action_id": "action-c009",
            "entity": "Banco de Alimentos de Madrid",
            "quantity": 6,
            "product_name": "Lomo de cerdo filetes 400g",
            "value_donated": 39.00,
            "donated_by": EMPLOYEES["emp-001"],
            "donated_at": (datetime.now() - timedelta(days=5, hours=5)).isoformat(),
            "notes": "",
        },
    ]

    for don in donations:
        db.table("donations").upsert(don, on_conflict="id").execute()

    # ── Merma log — 30 días de histórico realista ──────────────────────────────
    merma_entries = [
        # Semana actual
        {"days_ago": 0, "batch_id": "b-001", "qty": 3, "value": 3.60, "reason": "Panadería caducada sin vender"},
        {"days_ago": 1, "batch_id": "b-003", "qty": 2, "value": 8.40, "reason": "Carne caducada — lote retirado"},
        {"days_ago": 1, "batch_id": "b-002", "qty": 4, "value": 6.40, "reason": "Yogures caducados"},
        {"days_ago": 2, "batch_id": "b-006", "qty": 1, "value": 7.90, "reason": "Merluza en mal estado"},
        {"days_ago": 3, "batch_id": "b-007", "qty": 5, "value": 12.00, "reason": "Croissants no vendidos — fin de semana"},
        # Semana pasada
        {"days_ago": 5, "batch_id": "b-011", "qty": 12, "value": 14.40, "reason": "Leche fresca caducada"},
        {"days_ago": 6, "batch_id": "b-005", "qty": 3, "value": 5.85, "reason": "Nata fresca — caducidad adelantada"},
        {"days_ago": 7, "batch_id": "b-009", "qty": 8, "value": 22.40, "reason": "Fresas — daño por temperatura"},
        {"days_ago": 8, "batch_id": "b-008", "qty": 2, "value": 4.20, "reason": "Queso fresco — defecto visual"},
        {"days_ago": 9, "batch_id": "b-004", "qty": 4, "value": 7.80, "reason": "Nata fresca caducada"},
        {"days_ago": 10, "batch_id": "b-003", "qty": 3, "value": 12.60, "reason": "Carne picada — no vendida"},
        {"days_ago": 11, "batch_id": "b-001", "qty": 6, "value": 7.20, "reason": "Baguettes del domingo"},
        # Hace 2 semanas
        {"days_ago": 14, "batch_id": "b-006", "qty": 2, "value": 15.80, "reason": "Pescado en mal estado"},
        {"days_ago": 15, "batch_id": "b-010", "qty": 3, "value": 19.50, "reason": "Lomo cerdo caducado"},
        {"days_ago": 16, "batch_id": "b-002", "qty": 6, "value": 9.60, "reason": "Yogures caducados — lote antiguo"},
        {"days_ago": 17, "batch_id": "b-007", "qty": 8, "value": 19.20, "reason": "Panadería festivo"},
        {"days_ago": 18, "batch_id": "b-009", "qty": 10, "value": 28.00, "reason": "Fresas — recepción dañada"},
        {"days_ago": 20, "batch_id": "b-011", "qty": 8, "value": 9.60, "reason": "Leche fresca — nevera avería"},
        # Hace 3 semanas
        {"days_ago": 21, "batch_id": "b-003", "qty": 4, "value": 16.80, "reason": "Carne caducada fin de semana"},
        {"days_ago": 22, "batch_id": "b-005", "qty": 5, "value": 9.75, "reason": "Nata fresca sin vender"},
        {"days_ago": 24, "batch_id": "b-001", "qty": 10, "value": 12.00, "reason": "Baguettes lunes"},
        {"days_ago": 25, "batch_id": "b-006", "qty": 3, "value": 23.70, "reason": "Merluza caducada"},
        {"days_ago": 26, "batch_id": "b-008", "qty": 4, "value": 8.40, "reason": "Queso fresco expirado"},
        {"days_ago": 28, "batch_id": "b-010", "qty": 2, "value": 13.00, "reason": "Lomo cerdo — error etiquetado"},
        {"days_ago": 29, "batch_id": "b-002", "qty": 9, "value": 14.40, "reason": "Yogures lote antiguo — fin de mes"},
    ]

    for i, entry in enumerate(merma_entries):
        entry_date = (today - timedelta(days=entry["days_ago"])).isoformat()
        db.table("merma_log").upsert(
            {
                "id": f"merma-{i+1:03d}",
                "store_id": STORE_ID,
                "batch_id": entry["batch_id"],
                "quantity_lost": entry["qty"],
                "value_lost": entry["value"],
                "reason": entry["reason"],
                "date": entry_date,
            },
            on_conflict="id",
        ).execute()

    # ── Brief de hoy ──────────────────────────────────────────────────────────
    total_value_risk = round(
        8 * 1.20 + 12 * 4.20 + 18 * 1.60 + 4 * 7.90 + 9 * 1.95 + 6 * 5.80, 2
    )
    brief_text = f"""Brief de apertura — {today.strftime('%A %d de %B de %Y').capitalize()}

SITUACIÓN CRÍTICA: 3 productos requieren acción INMEDIATA hoy.

▶ CRÍTICOS (actuar antes de las 10:00):
  1. Baguette artesana | Pasillo 1-E1 | Caduca HOY | 8 uds → REBAJAR 60% → 0.48 €
  2. Carne picada 500g | Pasillo 3-E1 | Caduca mañana | 12 uds → REBAJAR 50% → 2.10 €
  3. Yogur Danone x4 | Pasillo 2-E3 | Caduca mañana | 18 uds → REBAJAR 40% → 0.96 €

▶ URGENTES (antes del mediodía):
  - Merluza 500g | Pasillo 4 | 2 días | REBAJAR 40% → 4.74 €
  - Nata fresca | Pasillo 2 | 2 días | REBAJAR 40% → 1.17 €
  - Pechuga pollo | Pasillo 3 | 2 días | REBAJAR 40% → 3.48 €

▶ RUTA DEL DÍA: Pasillo 1 → Pasillo 3 → Pasillo 2 → Pasillo 4 → Pasillo 5
  Tiempo estimado: 25 minutos | Valor en riesgo: {total_value_risk} €

Mañana es {(today + timedelta(days=1)).strftime('%A')} — anticipar reposición de lácteos (alta rotación)."""

    db.table("daily_briefs").upsert(
        {
            "store_id": STORE_ID,
            "date": today.isoformat(),
            "summary": brief_text,
            "value_at_risk": total_value_risk,
            "actions_count": len(pending_actions),
        },
        on_conflict="store_id,date",
    ).execute()

    # ── Informe semanal de la semana pasada ───────────────────────────────────
    last_monday = today - timedelta(days=today.weekday() + 7)
    weekly_content = f"""INFORME SEMANAL — Semana del {last_monday.strftime('%d/%m/%Y')}
Súper Martínez — Generado por MermaOps IA

RESUMEN EJECUTIVO:
Esta semana gestionamos 38 lotes próximos a caducar. Se aplicaron 22 descuentos,
se donaron 14 unidades a entidades sociales y la merma real fue de 67.35 €,
un 18% inferior a la semana anterior gracias a la intervención temprana en frescos.

MERMA REAL vs OBJETIVO:
  Merma registrada: 67.35 €
  Objetivo semana: 80.00 €
  Desviación: -15.8% (POR DEBAJO DEL OBJETIVO — BIEN)

CATEGORÍAS CON MAYOR MERMA:
  1. Frutas y verduras: 28.40 € (42%)
  2. Carne y aves: 21.00 € (31%)
  3. Lácteos: 11.25 € (17%)
  4. Pescadería: 6.70 € (10%)

ACCIONES TOMADAS:
  - 22 productos rebajados con éxito (media de descuento: 38%)
  - 2 donaciones al Banco de Alimentos y Cáritas (valor: 62.20 €)
  - 4 retiradas por caducidad (inevitable)
  - 0 sobrepasos de coste — todos los precios por encima del precio de compra

PATRÓN DETECTADO POR IA:
  Los martes y miércoles generan el 60% de la merma semanal en panadería.
  Recomendación: reducir el pedido del lunes en un 15% para las próximas semanas.

PRÓXIMA SEMANA:
  Atención especial a lácteos (período de alta rotación detectado)."""

    db.table("weekly_reports").upsert(
        {
            "id": "weekly-demo-001",
            "store_id": STORE_ID,
            "week_start": last_monday.isoformat(),
            "content": weekly_content,
            "stats": {
                "merma_value": 67.35,
                "merma_qty": 58,
                "actions_rebajar": 22,
                "actions_retirar": 4,
                "actions_donar": 2,
                "value_donated": 62.20,
            },
        },
        on_conflict="id",
    ).execute()

    # ── Comparativa tiendas (Feature #15) ─────────────────────────────────────
    period = today.strftime("%Y-%m")
    comparison_stores = [
        {
            "id": "sc-004", "store_id": "store-004",
            "store_name": "Fresco & Co Valencia",
            "period": period, "merma_value": 198.20, "merma_rate_pct": 3.8,
            "actions_resolved": 112, "donations_value": 95.40, "ranking": 1,
        },
        {
            "id": "sc-001", "store_id": "demo-store-001",
            "store_name": "Súper Martínez",
            "period": period, "merma_value": 342.50, "merma_rate_pct": 5.2,
            "actions_resolved": 89, "donations_value": 62.20, "ranking": 2,
        },
        {
            "id": "sc-002", "store_id": "store-002",
            "store_name": "Mercado Central Bilbao",
            "period": period, "merma_value": 521.30, "merma_rate_pct": 8.7,
            "actions_resolved": 64, "donations_value": 28.50, "ranking": 3,
        },
        {
            "id": "sc-003", "store_id": "store-003",
            "store_name": "La Paloma Supermercados",
            "period": period, "merma_value": 689.70, "merma_rate_pct": 11.4,
            "actions_resolved": 45, "donations_value": 15.80, "ranking": 4,
        },
    ]
    for cs in comparison_stores:
        db.table("store_comparison").upsert(cs, on_conflict="store_id,period").execute()

    # ── Informe mensual demo ───────────────────────────────────────────────────
    first_of_month = today.replace(day=1)
    monthly_content = """INFORME MENSUAL — MAYO 2026
Súper Martínez | Para el propietario

RESUMEN EJECUTIVO:
  En mayo se han registrado 342 euros de merma bruta, un 12% menos que en abril.
  La tasa de aprovechamiento (productos vendidos / productos gestionados) alcanza el 87%.
  Tendencia positiva: segundo mes consecutivo de mejora gracias al sistema de alertas tempranas.

MERMA POR CATEGORÍA:
  1. Panadería artesana: 128 € (37% del total) — pedido ajustado a la baja
  2. Carnicería: 89 € (26%)
  3. Lácteos: 75 € (22%)
  4. Pescadería: 50 € (15%)

IMPACTO SOCIAL:
  Donaciones a Banco de Alimentos y Cáritas: 62.20 euros de valor entregado.
  15 familias beneficiadas este mes según estimación de las entidades.
  Potencial deducción fiscal: consultar con asesor (Ley 17/2011).

PROVEEDORES:
  Horno San Luis mantiene un 18.5% de merma promedio — ALTO.
  Recomendación: reunión en junio para revisar plazos de entrega y embalaje.
  Frigoríficos del Norte: 12.3% — en línea con el sector.

ACCIONES PRIORITARIAS PARA JUNIO:
  1. Reducir pedido de pan artesano los lunes (-15 uds)
  2. Negociar condiciones con Horno San Luis (cita propuesta: 5 junio)
  3. Activar alertas tempranas para lácteos en la segunda quincena

Sistema MermaOps — generado automáticamente el 1 de mayo 2026."""

    db.table("monthly_reports").upsert(
        {
            "id": "monthly-demo-001",
            "store_id": STORE_ID,
            "month": first_of_month.isoformat(),
            "content": monthly_content,
        },
        on_conflict="store_id,month",
    ).execute()

    total_merma = sum(e["value"] for e in merma_entries)
    print(
        f"Demo data: {len(pending_actions)} acciones pendientes, "
        f"{len(completed_actions)} completadas, "
        f"{len(donations)} donaciones, "
        f"{len(merma_entries)} entradas de merma ({total_merma:.2f}€ en 30d), "
        f"brief + informe semanal + informe mensual"
    )


if __name__ == "__main__":
    run()
