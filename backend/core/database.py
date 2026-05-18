import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None
_admin_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL y SUPABASE_KEY deben estar definidos en .env")
        _client = create_client(url, key)
    return _client


def get_admin_db() -> Client:
    """Cliente con service role key — bypassa RLS. Solo para seed/admin, nunca en el API."""
    global _admin_client
    if _admin_client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL y SUPABASE_SERVICE_KEY deben estar definidos en .env")
        _admin_client = create_client(url, key)
    return _admin_client


# ── Stores ──────────────────────────────────────────────────────────────────

def get_store(store_id: str) -> dict | None:
    result = get_db().table("stores").select("*").eq("id", store_id).single().execute()
    return result.data


# ── Products ─────────────────────────────────────────────────────────────────

def get_product_by_barcode(store_id: str, barcode: str) -> dict | None:
    result = (
        get_db().table("products")
        .select("*")
        .eq("store_id", store_id)
        .eq("barcode", barcode)
        .single()
        .execute()
    )
    return result.data


def get_product_by_id(product_id: str) -> dict | None:
    result = (
        get_db().table("products")
        .select("*")
        .eq("id", product_id)
        .single()
        .execute()
    )
    return result.data


def get_all_products(store_id: str) -> list[dict]:
    result = (
        get_db().table("products")
        .select("*")
        .eq("store_id", store_id)
        .execute()
    )
    return result.data or []


# ── Batches ───────────────────────────────────────────────────────────────────

def get_batches_expiring_soon(store_id: str, days: int = 7) -> list[dict]:
    from datetime import date, timedelta
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=days)).isoformat()
    result = (
        get_db().table("batches")
        .select("*, products(*)")
        .eq("store_id", store_id)
        .eq("status", "active")
        .gte("expiry_date", today)
        .lte("expiry_date", cutoff)
        .order("expiry_date")
        .execute()
    )
    return result.data or []


def get_batches_by_product(store_id: str, product_id: str) -> list[dict]:
    result = (
        get_db().table("batches")
        .select("*")
        .eq("store_id", store_id)
        .eq("product_id", product_id)
        .eq("status", "active")
        .order("expiry_date")
        .execute()
    )
    return result.data or []


# ── Warehouse stock ───────────────────────────────────────────────────────────

def get_warehouse_stock(store_id: str, product_id: str) -> int:
    result = (
        get_db().table("warehouse_stock")
        .select("quantity")
        .eq("store_id", store_id)
        .eq("product_id", product_id)
        .single()
        .execute()
    )
    return result.data["quantity"] if result.data else 0


# ── Actions ───────────────────────────────────────────────────────────────────

def create_action(action: dict) -> dict:
    result = get_db().table("actions").insert(action).execute()
    return result.data[0]


def get_pending_actions(store_id: str) -> list[dict]:
    result = (
        get_db().table("actions")
        .select("*, batches(*, products(*))")
        .eq("store_id", store_id)
        .eq("status", "pending")
        .order("priority_score", desc=True)
        .execute()
    )
    return result.data or []


def complete_action(action_id: str, completed_by: str, notes: str = "", photo_url: str = "") -> None:
    from datetime import datetime
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.table("actions").update({
        "status": "completed",
        "completed_by": completed_by,
        "completed_at": now,
        "notes": notes,
        "photo_url": photo_url,
    }).eq("id", action_id).execute()

    # Registrar en merma_log automáticamente al completar
    try:
        action_row = db.table("actions").select(
            "store_id, batch_id, action_type, donation_quantity"
        ).eq("id", action_id).single().execute().data
        if action_row and action_row.get("batch_id"):
            batch = db.table("batches").select(
                "store_id, product_id, quantity, products(price, cost)"
            ).eq("id", action_row["batch_id"]).single().execute().data
            if batch:
                qty = action_row.get("donation_quantity") or batch.get("quantity", 0)
                products = batch.get("products") or {}
                cost = float(products.get("cost", 0))
                merma_entry = {
                    "store_id": action_row["store_id"],
                    "batch_id": action_row["batch_id"],
                    "quantity_lost": qty,
                    "value_lost": round(qty * cost, 2),
                    "reason": action_row.get("action_type", "completado"),
                    "date": datetime.utcnow().date().isoformat(),
                }
                db.table("merma_log").insert(merma_entry).execute()
    except Exception:
        pass  # No bloquear el completado por error en log


# ── Merma log ─────────────────────────────────────────────────────────────────

def log_merma(entry: dict) -> None:
    get_db().table("merma_log").insert(entry).execute()


def get_merma_history(store_id: str, days: int = 7) -> list[dict]:
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = (
        get_db().table("merma_log")
        .select("*, batches(*, products(*))")
        .eq("store_id", store_id)
        .gte("date", cutoff)
        .order("date", desc=True)
        .execute()
    )
    return result.data or []


# ── Daily briefs ──────────────────────────────────────────────────────────────

def save_daily_brief(brief: dict) -> None:
    get_db().table("daily_briefs").upsert(brief, on_conflict="store_id,date").execute()


def get_latest_brief(store_id: str) -> dict | None:
    result = (
        get_db().table("daily_briefs")
        .select("*")
        .eq("store_id", store_id)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ── Agent memory (episodic) ───────────────────────────────────────────────────

def get_memory(store_id: str, pattern_key: str) -> str | None:
    result = (
        get_db().table("agent_memory")
        .select("pattern_value")
        .eq("store_id", store_id)
        .eq("pattern_key", pattern_key)
        .single()
        .execute()
    )
    return result.data["pattern_value"] if result.data else None


def set_memory(store_id: str, pattern_key: str, pattern_value: str) -> None:
    from datetime import datetime
    get_db().table("agent_memory").upsert({
        "store_id": store_id,
        "pattern_key": pattern_key,
        "pattern_value": pattern_value,
        "updated_at": datetime.utcnow().isoformat(),
    }, on_conflict="store_id,pattern_key").execute()


# ── Users ──────────────────────────────────────────────────────────────────────

def get_user_by_telegram_id(telegram_user_id: str) -> dict | None:
    result = (
        get_db().table("users")
        .select("*")
        .eq("telegram_user_id", str(telegram_user_id))
        .single()
        .execute()
    )
    return result.data


# ── Donations ─────────────────────────────────────────────────────────────────

def log_donation(donation: dict) -> None:
    get_db().table("donations").insert(donation).execute()


def get_donation_stats(store_id: str, days: int = 30) -> dict:
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = (
        get_db().table("donations")
        .select("quantity, value_donated, entity")
        .eq("store_id", store_id)
        .gte("donated_at", cutoff)
        .execute()
    )
    rows = result.data or []
    total_qty = sum(r.get("quantity", 0) for r in rows)
    total_value = sum(float(r.get("value_donated", 0)) for r in rows)
    by_entity: dict[str, int] = {}
    for r in rows:
        entity = r.get("entity", "Otra")
        by_entity[entity] = by_entity.get(entity, 0) + r.get("quantity", 0)
    return {
        "total_donations": len(rows),
        "total_quantity": total_qty,
        "total_value_donated": round(total_value, 2),
        "by_entity": by_entity,
        "period_days": days,
    }


# ── Store comparison (Feature #15) ───────────────────────────────────────────

def get_stores_comparison(store_id: str) -> list[dict]:
    """Comparativa de merma entre todas las tiendas de la cadena."""
    from datetime import date, timedelta
    period = date.today().strftime("%Y-%m")
    result = get_db().table("store_comparison").select("*").eq("period", period).execute()
    if not result.data:
        prev = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        result = get_db().table("store_comparison").select("*").eq("period", prev).execute()
    stores = result.data or []
    stores.sort(key=lambda s: float(s.get("merma_rate_pct", 999)))
    for i, s in enumerate(stores):
        s["rank"] = i + 1
        s["is_current"] = s.get("store_id") == store_id
    return stores


# ── CSV import from TPV (Feature #18) ────────────────────────────────────────

def import_batches_csv(store_id: str, csv_data: str) -> dict:
    """
    Importa lotes desde CSV de TPV.
    Columnas requeridas: barcode, quantity, expiry_date
    Formato fecha: YYYY-MM-DD
    """
    import csv
    import io
    import uuid
    from datetime import datetime

    reader = csv.DictReader(io.StringIO(csv_data.strip()))
    imported = 0
    errors: list[str] = []

    for row in reader:
        try:
            barcode = (row.get("barcode") or row.get("codigo") or "").strip()
            raw_qty = (row.get("quantity") or row.get("cantidad") or "0").strip()
            expiry = (row.get("expiry_date") or row.get("caducidad") or "").strip()

            if not barcode:
                errors.append(f"Fila sin barcode: {row}")
                continue
            try:
                quantity = int(float(raw_qty))
            except ValueError:
                errors.append(f"Cantidad inválida '{raw_qty}' para barcode {barcode}")
                continue
            if quantity <= 0:
                errors.append(f"Cantidad cero para barcode {barcode}")
                continue
            if not expiry:
                errors.append(f"Sin fecha de caducidad para barcode {barcode}")
                continue
            # Normalise date
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    expiry = datetime.strptime(expiry, fmt).date().isoformat()
                    break
                except ValueError:
                    continue

            product = get_product_by_barcode(store_id, barcode)
            if not product:
                errors.append(f"Producto no encontrado: {barcode}")
                continue

            batch = {
                "id": f"import-{uuid.uuid4().hex[:10]}",
                "store_id": store_id,
                "product_id": product["id"],
                "expiry_date": expiry,
                "quantity": quantity,
                "status": "active",
            }
            get_db().table("batches").insert(batch).execute()
            imported += 1
        except Exception as e:
            errors.append(f"Error en fila {row}: {e}")

    return {
        "imported": imported,
        "errors": len(errors),
        "error_details": errors[:10],
    }


# ── Weekly reports ────────────────────────────────────────────────────────────

def save_weekly_report(report: dict) -> None:
    """Guarda el informe semanal en la tabla weekly_reports."""
    from datetime import datetime
    if "created_at" not in report:
        report["created_at"] = datetime.utcnow().isoformat()
    get_db().table("weekly_reports").insert(report).execute()


def get_weekly_reports(store_id: str, limit: int = 8) -> list[dict]:
    result = (
        get_db().table("weekly_reports")
        .select("*")
        .eq("store_id", store_id)
        .order("week_start", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ── Monthly reports (Feature #24) ────────────────────────────────────────────

def save_monthly_report(report: dict) -> None:
    get_db().table("monthly_reports").upsert(report, on_conflict="store_id,month").execute()


def get_monthly_reports(store_id: str, limit: int = 6) -> list[dict]:
    result = (
        get_db().table("monthly_reports")
        .select("*")
        .eq("store_id", store_id)
        .order("month", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ── Order suggestions (Feature #25) ──────────────────────────────────────────

def get_order_suggestions(store_id: str) -> list[dict]:
    """
    Sugerencia de pedido semanal basada en merma histórica.
    Calcula avg_daily_loss por producto y recomienda cantidad a pedir.
    """
    logs = get_merma_history(store_id, days=30)
    by_product: dict[str, dict] = {}
    for log in logs:
        batch = (log.get("batches") or {})
        product = (batch.get("products") or {}) if batch else {}
        pid = product.get("id")
        if not pid:
            continue
        if pid not in by_product:
            by_product[pid] = {
                "product_id": pid,
                "product_name": product.get("name", "Producto"),
                "category": product.get("category", ""),
                "pasillo": product.get("pasillo", "?"),
                "price": float(product.get("price", 0)),
                "total_lost": 0,
            }
        by_product[pid]["total_lost"] += int(log.get("quantity_lost", 0))

    suggestions = []
    for pid, data in by_product.items():
        avg_daily = data["total_lost"] / 30
        suggested_weekly = round(avg_daily * 7)
        if suggested_weekly < 1:
            continue
        warehouse = get_warehouse_stock(store_id, pid)
        order_qty = max(0, suggested_weekly - warehouse)
        if order_qty == 0:
            continue
        suggestions.append({
            "product_id": pid,
            "product_name": data["product_name"],
            "category": data["category"],
            "pasillo": data["pasillo"],
            "avg_daily_loss": round(avg_daily, 2),
            "suggested_weekly_qty": suggested_weekly,
            "current_warehouse_stock": warehouse,
            "order_qty": order_qty,
            "estimated_value": round(order_qty * data["price"], 2),
        })

    suggestions.sort(key=lambda s: s["estimated_value"], reverse=True)
    return suggestions[:20]


# ── ROI / merma evitada ───────────────────────────────────────────────────────

def get_completed_actions_value(store_id: str, days: int = 7) -> dict:
    """
    Calcula el valor recuperado por acciones completadas de rebajar/donar.
    Esto es la 'merma evitada': valor que habría sido pérdida y se recuperó.
    """
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = (
        get_db().table("actions")
        .select("action_type, batches(quantity, products(price, cost))")
        .eq("store_id", store_id)
        .eq("status", "completed")
        .in_("action_type", ["rebajar", "donar"])
        .gte("completed_at", cutoff)
        .execute()
    )
    rows = result.data or []
    value_recovered = 0.0
    cost_recovered = 0.0
    for r in rows:
        batch = r.get("batches") or {}
        product = (batch.get("products") or {}) if batch else {}
        qty = int(batch.get("quantity", 0))
        price = float(product.get("price", 0))
        cost = float(product.get("cost", 0))
        value_recovered += qty * price
        cost_recovered += qty * cost
    return {
        "actions_completed": len(rows),
        "value_recovered": round(value_recovered, 2),
        "cost_recovered": round(cost_recovered, 2),
        "period_days": days,
    }


def get_overdue_critical_actions(store_id: str, hours: int = 4) -> list[dict]:
    """Acciones críticas (score >= 85) pendientes hace más de `hours` horas."""
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    result = (
        get_db().table("actions")
        .select("*, batches(*, products(*))")
        .eq("store_id", store_id)
        .eq("status", "pending")
        .gte("priority_score", 85)
        .lte("created_at", cutoff)
        .order("priority_score", desc=True)
        .execute()
    )
    return result.data or []


# ── Agent runs ────────────────────────────────────────────────────────────────

def log_agent_run(run: dict) -> str:
    """Inserta un run de agente. Devuelve el id para referencia en supervisor_decisions."""
    import uuid
    if "id" not in run:
        run["id"] = str(uuid.uuid4())
    get_db().table("agent_runs").insert(run).execute()
    return run["id"]


def get_agent_runs(store_id: str, agent_type: str | None = None, limit: int = 20) -> list[dict]:
    q = (
        get_db().table("agent_runs")
        .select("*")
        .eq("store_id", store_id)
        .order("started_at", desc=True)
        .limit(limit)
    )
    if agent_type:
        q = q.eq("agent_type", agent_type)
    return q.execute().data or []


# ── Supervisor decisions (Fase 3) ─────────────────────────────────────────────

def log_supervisor_decision(decision: dict) -> str:
    """Registra una decisión explícita de Kuine sobre un producto/lote."""
    import uuid
    if "id" not in decision:
        decision["id"] = str(uuid.uuid4())
    get_db().table("supervisor_decisions").insert(decision).execute()
    return decision["id"]


def get_supervisor_decisions(store_id: str, limit: int = 50) -> list[dict]:
    result = (
        get_db().table("supervisor_decisions")
        .select("*")
        .eq("store_id", store_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ── Supplier stats (Feature #16) ──────────────────────────────────────────────

def get_supplier_stats(store_id: str) -> list[dict]:
    """
    Ficha de proveedor con avg merma_pct y conteo de productos.
    Una sola query con JOIN en lugar de N queries individuales.
    """
    # Un solo SELECT con JOIN — O(1) queries independientemente del número de proveedores
    result = (
        get_db().table("suppliers")
        .select("id, name, contact, supplier_merma(merma_pct, product_id, period)")
        .eq("store_id", store_id)
        .execute()
    )
    suppliers = result.data or []

    stats = []
    for sup in suppliers:
        rows = sup.get("supplier_merma") or []
        avg_merma = (
            round(sum(float(r.get("merma_pct", 0)) for r in rows) / len(rows), 1)
            if rows else 0.0
        )
        stats.append({
            "id": sup["id"],
            "name": sup["name"],
            "contact": sup.get("contact", ""),
            "product_count": len(rows),
            "avg_merma_pct": avg_merma,
            "products": [r["product_id"] for r in rows if r.get("product_id")],
            "period": rows[0].get("period") if rows else None,
            "risk": "ALTO" if avg_merma > 15 else "MEDIO" if avg_merma > 8 else "BAJO",
        })

    stats.sort(key=lambda s: s["avg_merma_pct"], reverse=True)
    return stats


# ── Agent conversations (Fase 1) ──────────────────────────────────────────────

def create_agent_conversation(store_id: str, telegram_user_id: str | None = None) -> str:
    """Crea una nueva conversación. Devuelve el id."""
    import uuid
    conv_id = str(uuid.uuid4())
    get_db().table("agent_conversations").insert({
        "id": conv_id,
        "store_id": store_id,
        "telegram_user_id": str(telegram_user_id) if telegram_user_id else None,
    }).execute()
    return conv_id


def get_active_conversation(store_id: str, telegram_user_id: str) -> str | None:
    """Obtiene el id de la conversación activa del usuario (si existe)."""
    result = (
        get_db().table("agent_conversations")
        .select("id")
        .eq("store_id", store_id)
        .eq("telegram_user_id", str(telegram_user_id))
        .eq("is_active", True)
        .order("last_message_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"]
    return None


def close_agent_conversation(conversation_id: str) -> None:
    from datetime import datetime
    get_db().table("agent_conversations").update({
        "is_active": False,
    }).eq("id", conversation_id).execute()


def log_agent_message(
    conversation_id: str,
    store_id: str,
    role: str,
    content: str,
    intent_tag: str | None = None,
    tools_used: list | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    agent_source: str = "chuwi",
) -> str:
    """Inserta un mensaje en agent_messages. Actualiza contadores de la conversación."""
    import uuid
    msg_id = str(uuid.uuid4())
    get_db().table("agent_messages").insert({
        "id": msg_id,
        "conversation_id": conversation_id,
        "store_id": store_id,
        "role": role,
        "content": content[:8000],  # truncar para no exceder límite
        "intent_tag": intent_tag,
        "tools_used": tools_used or [],
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "agent_source": agent_source,
    }).execute()
    # Actualizar contadores en la conversación
    try:
        from datetime import datetime
        get_db().table("agent_conversations").update({
            "last_message_at": datetime.utcnow().isoformat(),
            "message_count": get_db().table("agent_messages")
                .select("id", count="exact")
                .eq("conversation_id", conversation_id)
                .execute().count or 0,
        }).eq("id", conversation_id).execute()
    except Exception:
        pass
    return msg_id


def get_conversation_messages(conversation_id: str, limit: int = 50) -> list[dict]:
    result = (
        get_db().table("agent_messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return result.data or []


# ── Agent sessions (Fase 1) ───────────────────────────────────────────────────

def create_agent_session(store_id: str, telegram_user_id: str | None = None) -> str:
    """Crea una sesión de agente. Devuelve el id."""
    import uuid
    session_id = str(uuid.uuid4())
    get_db().table("agent_sessions").insert({
        "id": session_id,
        "store_id": store_id,
        "telegram_user_id": str(telegram_user_id) if telegram_user_id else None,
    }).execute()
    return session_id


def close_agent_session(session_id: str, kuine_calls: int = 0, resolved: bool = False) -> None:
    from datetime import datetime
    get_db().table("agent_sessions").update({
        "session_end": datetime.utcnow().isoformat(),
        "kuine_calls": kuine_calls,
        "resolved": resolved,
    }).eq("id", session_id).execute()


def increment_session_stats(session_id: str, tools_called: int = 0, kuine_calls: int = 0) -> None:
    try:
        row = get_db().table("agent_sessions").select(
            "messages_count, tools_called, kuine_calls"
        ).eq("id", session_id).single().execute().data
        if row:
            get_db().table("agent_sessions").update({
                "messages_count": row.get("messages_count", 0) + 1,
                "tools_called": row.get("tools_called", 0) + tools_called,
                "kuine_calls": row.get("kuine_calls", 0) + kuine_calls,
            }).eq("id", session_id).execute()
    except Exception:
        pass
