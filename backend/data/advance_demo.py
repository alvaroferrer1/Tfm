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
    Simula exactamente un día realista de actividad en la tienda:

    1. Avanza fechas de caducidad (resta 1 día).
    2. Marca como "sold" los lotes caducados.
    3. Simula ventas del día en tienda (5–18% según categoría y día semana).
    4. Reduce stock en almacén por ventas (warehouse_stock).
    5. Si warehouse_stock de un producto llega a 0 → crea acción "reponer" y
       simula que llega un pedido nuevo (batch fresco con stock reabastecido).
    6. Viernes: llega pedido semanal → aumenta warehouse_stock en todos los productos.
    7. Crea acciones para nuevos CRÍTICO sin acción pendiente.
    8. Completa ~20% de acciones antiguas (personal trabajó).

    Returns:
        dict con batches_updated, actions_created, actions_completed,
              stock_reduced, warehouse_updated, restock_orders, expired_products
    """
    result: dict = {
        "batches_updated": 0,
        "actions_created": 0,
        "actions_completed": 0,
        "stock_reduced": 0,
        "warehouse_updated": 0,
        "restock_orders": [],   # productos que llegó pedido
        "expired_products": [], # productos que caducaron hoy
        "low_stock_alerts": [], # productos con stock almacén < 5 uds
    }

    # Multiplicador de ventas por día de semana (viernes/sábado venden más)
    dow = today.weekday()
    sales_mult = {0: 0.7, 1: 0.75, 2: 0.85, 3: 0.90, 4: 1.20, 5: 1.35, 6: 0.80}.get(dow, 1.0)

    # 1. Obtener lotes activos con info del producto
    try:
        batches_res = (
            db.table("batches")
            .select("id, expiry_date, product_id, quantity, products(name,category,price)")
            .eq("store_id", store_id)
            .eq("status", "active")
            .execute()
        )
        batches = batches_res.data or []
    except Exception as exc:
        logger.error(f"[advance_demo] Error obteniendo batches: {exc}")
        return result

    # 2. Obtener stock en almacén de todos los productos
    try:
        wh_res = db.table("warehouse_stock").select("product_id, quantity, id").eq("store_id", store_id).execute()
        wh_by_product = {r["product_id"]: r for r in (wh_res.data or [])}
    except Exception:
        wh_by_product = {}

    new_critical_ids: list[str] = []

    # 3. Procesar cada lote
    for batch in batches:
        try:
            old_expiry = date.fromisoformat(batch["expiry_date"])
        except (KeyError, ValueError):
            continue

        new_expiry = old_expiry - step
        days_left = (new_expiry - today).days
        product = batch.get("products") or {}
        prod_name = product.get("name", "Producto")
        category  = (product.get("category") or "general").lower()

        if new_expiry <= original_today:
            # Lote caducado → marcar como sold
            try:
                db.table("batches").update({
                    "status": "sold",
                    "expiry_date": new_expiry.isoformat(),
                }).eq("id", batch["id"]).execute()
                result["batches_updated"] += 1
                result["expired_products"].append(prod_name)
            except Exception:
                pass
        else:
            urgency = _urgency_for_days(days_left)

            # Simular ventas del día según categoría
            qty = batch.get("quantity", 0) or 0
            cat_rate = {"panaderia": 0.25, "lacteos": 0.15, "carne": 0.12,
                        "pescado": 0.10, "fruta": 0.18, "verdura": 0.16}.get(category, 0.10)
            base_reduction = int(qty * cat_rate * sales_mult)
            reduction = max(0, min(qty, base_reduction + random.randint(-1, 1)))
            new_qty = max(0, qty - reduction)

            update_data: dict = {
                "expiry_date": new_expiry.isoformat(),
                "quantity": new_qty,
                "urgency": urgency,
            }
            try:
                db.table("batches").update(update_data).eq("id", batch["id"]).execute()
                result["batches_updated"] += 1
                result["stock_reduced"] += reduction
            except Exception:
                pass

            if urgency == "critico":
                new_critical_ids.append(batch["id"])

            # 4. Reducir stock en almacén por ventas del día
            pid = batch.get("product_id", "")
            if pid and pid in wh_by_product and reduction > 0:
                wh = wh_by_product[pid]
                wh_qty = wh.get("quantity", 0) or 0
                # Almacén pierde el 30% de las ventas de tienda (el resto ya estaba en lineal)
                wh_reduction = max(0, int(reduction * 0.30))
                new_wh_qty = max(0, wh_qty - wh_reduction)
                if wh_reduction > 0:
                    try:
                        db.table("warehouse_stock").update({
                            "quantity": new_wh_qty
                        }).eq("id", wh["id"]).execute()
                        result["warehouse_updated"] += 1
                    except Exception:
                        pass
                # Alerta si stock almacén baja de 5
                if new_wh_qty < 5 and prod_name not in result["low_stock_alerts"]:
                    result["low_stock_alerts"].append(prod_name)
                wh_by_product[pid]["quantity"] = new_wh_qty  # actualizar caché

    # 5. Viernes = llega pedido semanal del proveedor
    # → Reabastece almacén de todos los productos con <10 uds
    if today.weekday() == 4:  # Viernes
        for pid, wh in wh_by_product.items():
            wh_qty = wh.get("quantity", 0) or 0
            if wh_qty < 10:
                restock_qty = random.randint(15, 30)
                try:
                    db.table("warehouse_stock").update({
                        "quantity": wh_qty + restock_qty
                    }).eq("id", wh["id"]).execute()
                    # Buscar nombre del producto
                    prod_match = next((b.get("products", {}) for b in batches
                                       if b.get("product_id") == pid), {})
                    pname = (prod_match or {}).get("name", pid[:12])
                    result["restock_orders"].append(f"{pname} +{restock_qty} uds")
                    result["warehouse_updated"] += 1
                except Exception:
                    pass

    # 6. Si hay productos con stock=0 en almacén → crear acción "mover" si hay en almacén
    for pid, wh in wh_by_product.items():
        wh_qty = wh.get("quantity", 0) or 0
        if wh_qty > 0:
            # Hay stock en almacén → crear acción de mover a tienda
            batch_match = next((b for b in batches if b.get("product_id") == pid), None)
            if batch_match:
                batch_qty = batch_match.get("quantity", 0) or 0
                if batch_qty < 3:  # lineal casi vacío
                    try:
                        db.table("actions").insert({
                            "id": str(uuid.uuid4()),
                            "store_id": store_id,
                            "product_id": pid,
                            "batch_id": batch_match["id"],
                            "action_type": "mover",
                            "status": "pending",
                            "priority_score": 55,
                            "notes": f"Lineal bajo ({batch_qty} uds). {wh_qty} uds disponibles en almacen. FEFO.",
                        }).execute()
                        result["actions_created"] += 1
                    except Exception:
                        pass

    # 7. Crear acciones para nuevos críticos sin acción pendiente
    try:
        existing_res = (
            db.table("actions")
            .select("batch_id")
            .eq("store_id", store_id)
            .eq("status", "pending")
            .execute()
        )
        existing_batch_ids = {r.get("batch_id") for r in (existing_res.data or [])} - {None}
    except Exception:
        existing_batch_ids = set()

    for bid in new_critical_ids:
        batch_row = next((b for b in batches if b["id"] == bid), {})
        product = batch_row.get("products") or {}
        try:
            if bid not in existing_batch_ids:
                db.table("actions").insert({
                    "id": str(uuid.uuid4()),
                    "store_id": store_id,
                    "product_id": batch_row.get("product_id", ""),
                    "batch_id": bid,
                    "action_type": "rebajar",
                    "status": "pending",
                    "priority_score": 90,
                    "notes": f"CRITICO: {product.get('name','?')} caduca en 1-2 dias.",
                }).execute()
                result["actions_created"] += 1
        except Exception:
            pass

    # 8. Completar ~20 % de acciones pendientes antiguas (simula trabajo del personal)
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

    # Usar IDs de productos reales de la tienda para evitar FK violations
    try:
        real_products = (
            db.table("products")
            .select("id")
            .eq("store_id", store_id)
            .limit(5)
            .execute()
        )
        product_ids = [p["id"] for p in (real_products.data or [])]
    except Exception:
        product_ids = []

    if not product_ids:
        return  # Sin productos reales no podemos crear batches válidos

    pid_critico = product_ids[0]
    pid_alto = product_ids[min(1, len(product_ids) - 1)]

    for _ in range(max(0, _MIN_CRITICO - critico_count)):
        bid = f"demo-c-{uuid.uuid4().hex[:8]}"
        expiry = (today + timedelta(days=1)).isoformat()
        try:
            db.table("batches").insert({
                "id": bid, "store_id": store_id, "product_id": pid_critico,
                "expiry_date": expiry, "quantity": 5, "status": "active",
                "urgency": "critico",
            }).execute()
            db.table("actions").insert({
                "id": str(uuid.uuid4()), "store_id": store_id, "product_id": pid_critico,
                "batch_id": bid, "action_type": "rebajar", "status": "pending",
                "priority_score": 90, "urgency_level": "critico",
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
                "id": bid, "store_id": store_id, "product_id": pid_alto,
                "expiry_date": expiry, "quantity": 8, "status": "active",
                "urgency": "alto",
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


def _send_day_telegram_messages(store_id: str, critical_count: int, days: int = 1) -> int:
    """Envía alertas Telegram sobre productos críticos nuevos. Retorna nº de mensajes enviados."""
    if critical_count == 0:
        return 0
    try:
        from backend.agents import notifier
        from backend.core import database
        batches = database.get_batches_expiring_soon(store_id, days=2)
        criticos = [b for b in batches if (b.get("urgency") or "") == "critico"][:5]

        lines = [
            f"<b>🔴 DEMO AVANZADA {days} {'día' if days == 1 else 'días'}</b>",
            f"",
            f"<b>{critical_count} producto(s) CRÍTICO(s)</b> detectados por Kuine:",
            "",
        ]
        for b in criticos:
            p = b.get("products") or {}
            name = p.get("name", "Producto")
            exp = b.get("expiry_date", "?")
            qty = b.get("quantity", 0)
            pasillo = p.get("pasillo", "?")
            lines.append(f"• <b>{name}</b> | Pasillo {pasillo} | {qty} uds | Caduca {exp}")

        lines += ["", "Usa /criticos para ver acciones pendientes."]
        msg = "\n".join(lines)

        # send_telegram handles chat_id lookup (store table → env var fallback)
        sent = notifier.send_telegram(store_id, msg)
        return 1 if sent else 0
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

    total_new_actions = 0
    all_low_stock: dict[str, dict] = {}  # product_name → alert dict (dedup)
    for i in range(n):
        sim_day = today + timedelta(days=i)
        day_result = _simulate_one_day(db, store_id, sim_day, step, sim_day)
        summary["batches_updated"] += day_result["batches_updated"]
        summary["actions_created"] += day_result["actions_created"]
        summary["actions_completed"] += day_result["actions_completed"]
        summary["stock_reduced"] += day_result.get("stock_reduced", 0)
        total_new_actions += day_result["actions_created"]
        for name in day_result.get("low_stock_alerts", []):
            if name not in all_low_stock:
                all_low_stock[name] = {
                    "product_name": name,
                    "current_qty": random.randint(2, 4),
                    "suggested_qty": random.randint(15, 30),
                }

    # Send a single Telegram summary for the full advance (not one per simulated day)
    if total_new_actions > 0:
        msgs = _send_day_telegram_messages(store_id, total_new_actions, days=n)
        summary["telegram_messages_sent"] += msgs

    # Enviar alerta de stock bajo con botón "Hacer pedido"
    if all_low_stock:
        try:
            from backend.agents import notifier as _notifier
            sent = _notifier.notify_low_stock(store_id, list(all_low_stock.values()))
            summary["telegram_messages_sent"] += sent
            summary["low_stock_alerts"] = list(all_low_stock.keys())
        except Exception as _e:
            logger.warning(f"[advance_demo] Low stock alert falló: {_e}")

    _ensure_risk_distribution(db, store_id, today, summary)

    if generate_brief:
        _generate_simulated_brief(db, store_id, n)

    # Enrichen summary with product names for demo_prep.py display
    try:
        from backend.core import database as _db
        pending = _db.get_pending_actions(store_id)
        criticos = [
            ((a.get("batches") or {}).get("products") or {}).get("name", "Producto")
            if isinstance(a.get("batches"), dict) else a.get("product_name", "Producto")
            for a in pending if a.get("priority_score", 0) >= 85
        ]
        altos = [
            ((a.get("batches") or {}).get("products") or {}).get("name", "Producto")
            if isinstance(a.get("batches"), dict) else a.get("product_name", "Producto")
            for a in pending if 65 <= a.get("priority_score", 0) < 85
        ]
        summary["newly_critical"] = criticos[:5]
        summary["newly_high"] = altos[:5]
        summary["critical_now"] = len(criticos)
        summary["days_advanced"] = n
    except Exception:
        summary["newly_critical"] = []
        summary["newly_high"] = []
        summary["critical_now"] = 0
        summary["days_advanced"] = n

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
