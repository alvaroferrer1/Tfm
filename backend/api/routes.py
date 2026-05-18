"""
Endpoints REST — usados por la app Flutter y por Chuwi para acciones en BD.
"""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel

from backend.core import database
from backend.agents import supervisor
from backend.api.auth import verify_token, optional_token
from backend.api.limiter import limiter

router = APIRouter()
logger = logging.getLogger("mermaops.api")
STORE_ID = os.getenv("STORE_ID", "demo-store-001")


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/ping")
def ping():
    return {"pong": True}


@router.get("/health")
def health():
    """
    Health check con comprobación de BD.
    Devuelve 200 si el sistema está operativo, 503 si hay problemas.
    Usado por monitorización y despliegues.
    """
    import time
    status = {"api": "ok", "db": "unknown", "store_id": STORE_ID}
    t0 = time.monotonic()
    try:
        # Consulta mínima para verificar conectividad con Supabase
        database.get_db().table("stores").select("id").limit(1).execute()
        status["db"] = "ok"
        status["db_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    except Exception as e:
        status["db"] = "error"
        status["db_error"] = str(e)[:100]
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=status)
    return status


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard():
    """KPIs en tiempo real para la app Flutter."""
    try:
        pending = database.get_pending_actions(STORE_ID)
        brief = database.get_latest_brief(STORE_ID)
        batches = database.get_batches_expiring_soon(STORE_ID, days=7)

        total_value_at_risk = sum(
            b.get("quantity", 0) * (b.get("products") or {}).get("price", 0)
            for b in batches
        )
        critical_count = sum(1 for a in pending if a.get("priority_score", 0) >= 85)

        return {
            "pending_actions": len(pending),
            "critical_count": critical_count,
            "value_at_risk": round(total_value_at_risk, 2),
            "expiring_count": len(batches),
            "latest_brief": brief,
        }
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Scan ──────────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    barcode: str
    user_id: str = ""


@router.post("/scan")
@limiter.limit("30/minute")
def scan_product(request: Request, body: ScanRequest, _auth: dict = Depends(verify_token)):
    """Escaneo completo: evaluación + descuento + validación + respuesta IA."""
    if not body.barcode or not body.barcode.strip():
        raise HTTPException(status_code=400, detail="barcode requerido")
    barcode = body.barcode.strip()
    # Validar que parece un barcode real (solo dígitos, 6-14 chars)
    if not barcode.isdigit() or not (6 <= len(barcode) <= 14):
        raise HTTPException(status_code=400, detail=f"Barcode inválido: {barcode!r}")
    try:
        result = supervisor.run_scan(STORE_ID, barcode, body.user_id)
        return {"result": result, "barcode": barcode}
    except Exception as e:
        logger.error(f"Scan error ({barcode}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Actions ───────────────────────────────────────────────────────────────────

@router.get("/actions")
def get_actions():
    """Lista de acciones pendientes ordenadas por prioridad."""
    try:
        return database.get_pending_actions(STORE_ID)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CompleteActionRequest(BaseModel):
    action_id: str
    completed_by: str
    notes: str = ""
    photo_url: str = ""


@router.post("/actions/complete")
def complete_action(body: CompleteActionRequest, _auth: dict = Depends(verify_token)):
    """Marca una acción como completada."""
    if not body.action_id or not body.completed_by:
        raise HTTPException(status_code=400, detail="action_id y completed_by son requeridos")
    try:
        database.complete_action(
            body.action_id, body.completed_by, body.notes, body.photo_url
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products/expiring")
def get_expiring(days: int = 7):
    """Productos que caducan en los próximos N días."""
    try:
        return database.get_batches_expiring_soon(STORE_ID, days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/reports/daily")
def get_daily_brief():
    """Brief diario más reciente."""
    brief = database.get_latest_brief(STORE_ID)
    if not brief:
        raise HTTPException(status_code=404, detail="Sin brief para hoy")
    return brief


@router.post("/reports/weekly")
def trigger_weekly_report(background_tasks: BackgroundTasks):
    """Dispara el informe semanal en background."""
    background_tasks.add_task(supervisor.run_weekly_report, STORE_ID)
    return {"status": "generando", "message": "El informe semanal se está generando"}


# ── Brief manual ─────────────────────────────────────────────────────────────

@router.post("/brief/run")
@limiter.limit("5/minute")
def run_brief(request: Request, background_tasks: BackgroundTasks, _auth: dict = Depends(verify_token)):
    """Genera el brief diario ahora (sin esperar las 07:30). Corre en background."""
    background_tasks.add_task(supervisor.run_daily_brief, STORE_ID)
    return {"status": "generando", "message": "Brief en proceso. Chuwi te avisará cuando esté listo."}


@router.post("/brief/run/sync")
def run_brief_sync():
    """Versión síncrona para testing — puede tardar hasta 60s."""
    try:
        result = supervisor.run_daily_brief(STORE_ID)
        return {"brief": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Evaluación paralela ───────────────────────────────────────────────────────

@router.get("/evaluate/parallel")
def evaluate_parallel(days: int = 7):
    """
    Evalúa todos los lotes activos en paralelo.
    Más rápido que el loop agéntico para dashboards que solo necesitan los scores.
    """
    try:
        from backend.agents.parallel_evaluator import evaluate_all_parallel, summary_stats
        results = evaluate_all_parallel(STORE_ID, days=days)
        stats = summary_stats(results)
        return {"stats": stats, "results": results}
    except Exception as e:
        logger.error(f"Parallel evaluate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Stats para Flutter ────────────────────────────────────────────────────────

@router.get("/stats/suppliers")
def get_supplier_stats():
    """Ficha de proveedor: merma histórica por proveedor (Feature #16)."""
    try:
        return {"suppliers": database.get_supplier_stats(STORE_ID)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/donations")
def get_donation_stats(days: int = 30):
    """Estadísticas de donaciones para los últimos N días."""
    try:
        return database.get_donation_stats(STORE_ID, days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/comparison")
def get_stores_comparison():
    """Comparativa de merma entre tiendas de la cadena (Feature #15)."""
    try:
        return {"stores": database.get_stores_comparison(STORE_ID)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ImportBatchesRequest(BaseModel):
    csv_data: str


@router.post("/import/batches")
def import_batches(body: ImportBatchesRequest, _auth: dict = Depends(verify_token)):
    """
    Importa lotes desde CSV de TPV (Feature #18).
    CSV columns: barcode, quantity, expiry_date (YYYY-MM-DD)
    """
    if not body.csv_data.strip():
        raise HTTPException(status_code=400, detail="csv_data requerido")
    # Límite de tamaño para evitar abuso
    if len(body.csv_data) > 500_000:
        raise HTTPException(status_code=413, detail="CSV demasiado grande (máx 500KB)")
    try:
        result = database.import_batches_csv(STORE_ID, body.csv_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/monthly")
def get_monthly_reports():
    """Informes mensuales para el dueño (Feature #24)."""
    try:
        return {"reports": database.get_monthly_reports(STORE_ID)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/monthly/run")
def run_monthly_report(background_tasks: BackgroundTasks):
    """Dispara el informe mensual en background."""
    background_tasks.add_task(supervisor.run_monthly_report, STORE_ID)
    return {"status": "generando", "message": "Informe mensual en proceso."}


@router.get("/stats/order-suggestions")
def get_order_suggestions():
    """Sugerencia de pedido semanal basada en velocidad de merma histórica (Feature #25)."""
    try:
        return {"suggestions": database.get_order_suggestions(STORE_ID)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Vinculación cuenta Telegram ──────────────────────────────────────────────

class LinkTelegramRequest(BaseModel):
    telegram_user_id: str


@router.post("/user/link-telegram")
def link_telegram(body: LinkTelegramRequest, auth: dict = Depends(verify_token)):
    """
    Vincula el ID de Telegram del usuario autenticado con su cuenta en la app.
    El usuario copia su Telegram ID (que Chuwi le muestra al escribir /start)
    y lo pega en la app. Este endpoint lo guarda en la tabla users.
    """
    if not body.telegram_user_id or not body.telegram_user_id.strip().isdigit():
        raise HTTPException(status_code=400, detail="telegram_user_id debe ser numérico")
    user_id = auth.get("sub")
    if not user_id or auth.get("dev_mode"):
        raise HTTPException(status_code=401, detail="Autenticación real requerida")
    try:
        get_db = database.get_db
        get_db().table("users").update({
            "telegram_user_id": body.telegram_user_id.strip()
        }).eq("id", user_id).execute()
        return {"ok": True, "telegram_user_id": body.telegram_user_id.strip()}
    except Exception as e:
        logger.error(f"link_telegram error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/user/link-telegram")
def unlink_telegram(auth: dict = Depends(verify_token)):
    """Desvincula el Telegram del usuario (para privacidad o cambio de cuenta)."""
    user_id = auth.get("sub")
    if not user_id or auth.get("dev_mode"):
        raise HTTPException(status_code=401, detail="Autenticación real requerida")
    try:
        database.get_db().table("users").update({
            "telegram_user_id": None
        }).eq("id", user_id).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/me")
def get_current_user(auth: dict = Depends(verify_token)):
    """Devuelve el perfil del usuario autenticado incluyendo si tiene Telegram vinculado."""
    user_id = auth.get("sub")
    if not user_id or auth.get("dev_mode"):
        return {"id": "dev", "role": "admin", "telegram_linked": False}
    try:
        result = database.get_db().table("users").select(
            "id, email, role, store_id, telegram_user_id"
        ).eq("id", user_id).single().execute()
        user = result.data or {}
        user["telegram_linked"] = bool(user.get("telegram_user_id"))
        return user
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── ESG / Impacto ambiental ───────────────────────────────────────────────────

@router.get("/stats/esg")
def get_esg_stats(days: int = 30):
    """Métricas ESG: CO2 evitado, agua ahorrada, puntuación de sostenibilidad."""
    try:
        from backend.agents.esg import get_store_esg_summary
        return get_store_esg_summary(STORE_ID, days=days)
    except Exception as e:
        logger.error(f"ESG stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/esg/report")
def get_esg_report(days: int = 30):
    """Genera el informe ESG completo en lenguaje natural para el dueño."""
    try:
        from backend.agents.esg import generate_esg_report
        report = generate_esg_report(STORE_ID, days=days)
        return {"report": report, "period_days": days}
    except Exception as e:
        logger.error(f"ESG report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Predicción predictiva de merma ────────────────────────────────────────────

@router.get("/predict/risk")
def get_risk_predictions(days: int = 7):
    """
    Predicciones de merma para los próximos N días.
    Combina historial, clima (Open-Meteo) y patrones de día de semana.
    """
    try:
        from backend.agents.predictor import predict_merma_risk
        predictions = predict_merma_risk(STORE_ID, forecast_days=days)
        return {"predictions": predictions, "forecast_days": days, "count": len(predictions)}
    except Exception as e:
        logger.error(f"Predict risk error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predict/brief")
def get_prediction_brief(days: int = 5):
    """Brief predictivo en lenguaje natural (incluye previsión meteorológica)."""
    try:
        from backend.agents.predictor import generate_prediction_brief
        brief = generate_prediction_brief(STORE_ID, forecast_days=days)
        return {"brief": brief, "forecast_days": days}
    except Exception as e:
        logger.error(f"Predict brief error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Análisis visual de producto ───────────────────────────────────────────────

class VisionAnalysisRequest(BaseModel):
    image_base64: str
    product_name: str = ""
    days_left: int = -1
    category: str = ""
    media_type: str = "image/jpeg"


@router.post("/scan/vision")
@limiter.limit("20/minute")
def scan_vision(request: Request, body: VisionAnalysisRequest, _auth: dict = Depends(verify_token)):
    """
    Analiza visualmente una foto de producto con Claude Vision.
    Detecta frescura, daños, fecha visible en etiqueta.
    La imagen se envía en base64. Sin barcode necesario.
    """
    if not body.image_base64:
        raise HTTPException(status_code=400, detail="image_base64 requerido")
    if len(body.image_base64) > 10_000_000:  # ~7.5MB de imagen
        raise HTTPException(status_code=413, detail="Imagen demasiado grande")
    try:
        from backend.agents.vision import analyze_product_photo
        result = analyze_product_photo(
            image_base64=body.image_base64,
            product_name=body.product_name,
            days_left=body.days_left,
            category=body.category,
            media_type=body.media_type,
        )
        return result
    except Exception as e:
        logger.error(f"Vision scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Demo temporal — avanza el tiempo en la BD para la presentación ───────────

class AdvanceDemoRequest(BaseModel):
    days: float = 1.0
    store_id: str = ""
    generate_brief: bool = True


@router.post("/demo/advance")
def advance_demo(body: AdvanceDemoRequest, _auth: dict = Depends(verify_token)):
    """
    Avanza N días en la BD para la demo en vivo.
    Actualiza caducidades, crea acciones urgentes y garantiza distribución de riesgo.
    Uso: POST /api/v1/demo/advance  {"days": 2}
    """
    try:
        from backend.data.advance_demo import advance as _advance
        store = body.store_id or os.getenv("STORE_ID", "demo-store-001")
        result = _advance(body.days, store_id=store, generate_brief=body.generate_brief)
        return {"ok": True, **result}
    except Exception as e:
        logger.error(f"advance_demo error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/demo/reset")
def reset_demo(_auth: dict = Depends(verify_token)):
    """Vuelve al estado inicial del Super Martínez (re-seed)."""
    try:
        from backend.data.advance_demo import reset as _reset
        store = os.getenv("STORE_ID", "demo-store-001")
        _reset(store)
        return {"ok": True, "message": "Estado reiniciado al día de hoy."}
    except Exception as e:
        logger.error(f"demo_reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/merma")
def get_merma_stats(days: int = 30):
    """Estadísticas de merma para el gráfico de la app."""
    try:
        logs = database.get_merma_history(STORE_ID, days=days)
        total_value = sum(float(l.get("value_lost", 0)) for l in logs)
        total_qty = sum(int(l.get("quantity_lost", 0)) for l in logs)
        return {
            "period_days": days,
            "total_value_lost": round(total_value, 2),
            "total_quantity_lost": total_qty,
            "entries": len(logs),
            "logs": logs,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
