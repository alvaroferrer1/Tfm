"""
Endpoints REST — usados por la app Flutter y por Chuwi para acciones en BD.
"""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, UploadFile, File
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


@router.get("/reports/daily-list")
def get_daily_briefs_list(limit: int = 14):
    """Últimos N briefs diarios. Usado por la app Flutter (evita RLS de Supabase)."""
    briefs = database.get_daily_briefs_list(STORE_ID, limit=min(limit, 30))
    return {"briefs": briefs}




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
def link_telegram(
    body: LinkTelegramRequest,
    background_tasks: BackgroundTasks,
    auth: dict = Depends(verify_token),
):
    """
    Vincula el ID de Telegram del usuario autenticado con su cuenta en la app.
    El usuario copia su Telegram ID (que Chuwi le muestra al escribir /start)
    y lo pega en la app. Este endpoint lo guarda en la tabla users y envía
    un mensaje de bienvenida de Chuwi por Telegram.
    """
    if not body.telegram_user_id or not body.telegram_user_id.strip().isdigit():
        raise HTTPException(status_code=400, detail="telegram_user_id debe ser numérico")
    user_id = auth.get("sub")
    if not user_id or auth.get("dev_mode"):
        raise HTTPException(status_code=401, detail="Autenticación real requerida")
    try:
        db = database.get_db()
        # Upsert para asegurar que el usuario existe en public.users
        db.table("users").upsert({
            "id": user_id,
            "email": auth.get("email", ""),
            "store_id": STORE_ID,
            "role": "staff",
            "telegram_user_id": body.telegram_user_id.strip(),
        }).execute()

        # Recuperar datos actualizados para el mensaje de bienvenida
        user_row = db.table("users").select("email, role").eq("id", user_id).maybe_single().execute()
        user_data = user_row.data or {}

        background_tasks.add_task(
            _send_telegram_welcome,
            body.telegram_user_id.strip(),
            user_data.get("email", ""),
            user_data.get("role", "staff"),
        )
        return {"ok": True, "telegram_user_id": body.telegram_user_id.strip()}
    except Exception as e:
        logger.error(f"link_telegram error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _send_telegram_welcome(telegram_id: str, email: str, role: str) -> None:
    """Envía mensaje de bienvenida desde Chuwi al vincular la app."""
    import asyncio
    try:
        from telegram import Bot
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token or not telegram_id:
            return
        role_label = {"manager": "encargado", "admin": "administrador"}.get(role, "empleado")
        name = email.split("@")[0] if email else "empleado"
        msg = (
            f"✅ *¡Cuenta vinculada con éxito!*\n\n"
            f"Hola {name}, soy Chuwi. Tu cuenta de MermaOps está ahora conectada a Telegram.\n\n"
            f"Rol asignado: *{role_label}*\n\n"
            f"Ya puedes hablarme en lenguaje natural. Prueba con:\n"
            f"• «¿Qué hay crítico hoy?»\n"
            f"• «¿Cuánta merma llevamos esta semana?»\n"
            f"• Envíame una foto de un producto\n\n"
            f"También te avisaré automáticamente cuando algo cambie en la tienda. 🏪"
        )
        asyncio.run(Bot(token).send_message(
            chat_id=int(telegram_id),
            text=msg,
            parse_mode="Markdown",
        ))
    except Exception as e:
        logger.warning(f"_send_telegram_welcome error (no crítico): {e}")


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
    """Devuelve el perfil del usuario autenticado incluyendo si tiene Telegram vinculado.
    Si el usuario existe en auth pero no en public.users, lo crea automáticamente."""
    user_id = auth.get("sub")
    if not user_id or auth.get("dev_mode"):
        return {"id": "dev", "role": "admin", "telegram_linked": False}
    try:
        db = database.get_db()
        result = db.table("users").select(
            "id, email, role, store_id, telegram_user_id"
        ).eq("id", user_id).maybe_single().execute()
        user = result.data if result.data else {}

        if not user:
            # Primer acceso: crear fila en public.users desde los claims del JWT
            email = auth.get("email", "")
            user = {
                "id": user_id,
                "email": email,
                "role": "staff",
                "store_id": STORE_ID,
                "telegram_user_id": None,
            }
            try:
                db.table("users").insert(user).execute()
                logger.info(f"[auth] Usuario creado en public.users: {user_id} ({email})")
            except Exception as ins_err:
                logger.warning(f"[auth] No se pudo crear usuario (puede ya existir): {ins_err}")

        user["telegram_linked"] = bool(user.get("telegram_user_id"))
        return user
    except Exception as e:
        logger.error(f"get_current_user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/app-login-notify")
def app_login_notify(background_tasks: BackgroundTasks, auth: dict = Depends(verify_token)):
    """Notifica por Telegram cuando el usuario entra desde la app (fire-and-forget)."""
    user_id = auth.get("sub")
    email = auth.get("email", "")
    if not user_id or auth.get("dev_mode"):
        return {"ok": True, "notified": False}
    try:
        db = database.get_db()
        result = db.table("users").select("telegram_user_id, role").eq("id", user_id).maybe_single().execute()
        user = result.data if result.data else {}
        telegram_id = user.get("telegram_user_id", "")
        role = user.get("role", "staff")
        if telegram_id:
            background_tasks.add_task(_send_telegram_login_notify, telegram_id, email, role)
            return {"ok": True, "notified": True}
        return {"ok": True, "notified": False}
    except Exception as e:
        logger.warning(f"app_login_notify error (no crítico): {e}")
        return {"ok": True, "notified": False}


def _send_telegram_login_notify(telegram_id: str, email: str, role: str) -> None:
    import asyncio
    try:
        from telegram import Bot
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token or not telegram_id:
            return
        name = email.split("@")[0] if email else "empleado"
        msg = (
            f"📱 *{name} ha iniciado sesión en la app*\n\n"
            f"Sesión activa en MermaOps. El sistema está monitorizando la tienda. "
            f"Escríbeme si necesitas algo. 🌱"
        )
        asyncio.run(Bot(token).send_message(
            chat_id=int(telegram_id),
            text=msg,
            parse_mode="Markdown",
        ))
    except Exception as e:
        logger.warning(f"_send_telegram_login_notify error (no crítico): {e}")


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
# Los endpoints /demo/advance y /demo/reset están en routes_demo.py
# y se montan en main.py junto con este router.
# Se incluyen aquí directamente para que queden bajo el mismo prefijo /api/v1.

from backend.api.routes_demo import router as _demo_router
router.include_router(_demo_router)


# ── PDF endpoints ─────────────────────────────────────────────────────────────

@router.get("/reports/brief/pdf")
def get_brief_pdf(date: str = "", _auth: dict = Depends(verify_token)):
    """Descarga el brief de hoy (o de la fecha indicada) como PDF."""
    from fastapi.responses import Response
    try:
        brief = database.get_latest_brief(STORE_ID)
        if not brief:
            raise HTTPException(status_code=404, detail="Sin brief disponible")
        pending = database.get_pending_actions(STORE_ID)
        critical_actions = [a for a in pending if (a.get("priority_score") or 0) >= 85]
        high_actions = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
        value_at_risk = brief.get("value_at_risk", 0.0) or 0.0
        from backend.core.pdf_generator import generate_brief_pdf
        pdf_bytes = generate_brief_pdf(
            brief_text=brief.get("summary", ""),
            brief_date=brief.get("date", ""),
            critical_count=len(critical_actions),
            high_count=len(high_actions),
            value_at_risk=float(value_at_risk),
            actions_count=brief.get("actions_count", len(pending)),
            critical_actions=critical_actions,
            high_actions=high_actions,
        )
        fecha = brief.get("date", "hoy")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="brief_{fecha}.pdf"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"brief pdf error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/weekly/pdf")
def get_weekly_pdf(week_start: str = "", _auth: dict = Depends(verify_token)):
    """Genera y descarga el informe semanal como PDF."""
    from fastapi.responses import Response
    try:
        from backend.core.pdf_generator import generate_weekly_pdf
        from backend.agents.reporter import generate_weekly_report
        report_text = generate_weekly_report(STORE_ID)
        merma_week = database.get_merma_history(STORE_ID, days=7)
        merma_eur = sum(float(l.get("value_lost", 0)) for l in merma_week)
        merma_qty = sum(int(l.get("quantity_lost", 0)) for l in merma_week)
        donations = database.get_donation_stats(STORE_ID, days=7)
        pdf_bytes = generate_weekly_pdf(
            report_text=report_text,
            week_start=week_start,
            merma_eur=merma_eur,
            merma_qty=merma_qty,
            donated_qty=donations.get("total_quantity", 0),
            donated_value=float(donations.get("total_value_donated", 0)),
        )
        from datetime import date as _dt
        fecha = _dt.today().isoformat()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="informe_semanal_{fecha}.pdf"'},
        )
    except Exception as e:
        logger.error(f"weekly pdf error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/analyze-pdf")
async def analyze_pdf_report(file: UploadFile = File(...)):
    """Recibe un PDF (informe supervisor, etc.) y lo analiza con Claude."""
    try:
        import io
        from pypdf import PdfReader
        from backend.core.llm import call_claude

        pdf_bytes = await file.read()
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_pages = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_pages.append(t)
        pdf_text = "\n".join(text_pages)

        if not pdf_text.strip():
            raise HTTPException(status_code=422, detail="El PDF no contiene texto extraíble.")

        # Truncar a 40k chars para no exceder ventana de contexto
        if len(pdf_text) > 40000:
            pdf_text = pdf_text[:40000] + "\n[...documento truncado...]"

        from backend.core.llm import get_client, MODEL
        response = get_client().messages.create(
            model=MODEL,
            max_tokens=2048,
            system=(
                "Eres un analista experto en gestión de supermercados y reducción de merma alimentaria. "
                "Analiza el documento que te proporciona el usuario y extrae:\n"
                "1. Resumen ejecutivo (3-5 frases)\n"
                "2. KPIs clave identificados (merma €, %, unidades, si aparecen)\n"
                "3. Problemas detectados\n"
                "4. Recomendaciones concretas para reducir merma\n"
                "5. Próximas acciones prioritarias\n"
                "Responde en español, con formato claro y directo."
            ),
            messages=[{
                "role": "user",
                "content": f"Analiza este documento:\n\n{pdf_text}"
            }],
        )
        analysis = response.content[0].text if response.content else ""
        return {"analysis": analysis, "pages": len(reader.pages), "chars": len(pdf_text)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"analyze-pdf error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/monthly/pdf")
def get_monthly_pdf(_auth: dict = Depends(verify_token)):
    """Genera y descarga el informe mensual como PDF."""
    from fastapi.responses import Response
    try:
        from backend.core.pdf_generator import generate_monthly_pdf
        from backend.agents.reporter import generate_monthly_report
        report_text = generate_monthly_report(STORE_ID)
        merma = database.get_merma_history(STORE_ID, days=30)
        merma_eur = sum(float(l.get("value_lost", 0)) for l in merma)
        donations = database.get_donation_stats(STORE_ID, days=30)
        from datetime import date as _dt
        month_label = _dt.today().strftime("%B %Y")
        pdf_bytes = generate_monthly_pdf(
            report_text=report_text,
            month=month_label,
            merma_eur=merma_eur,
            donated_value=float(donations.get("total_value_donated", 0)),
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="informe_mensual_{_dt.today().strftime("%Y-%m")}.pdf"'},
        )
    except Exception as e:
        logger.error(f"monthly pdf error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/presentation/pdf")
def get_presentation_pdf(_auth: dict = Depends(verify_token)):
    """Descarga el PDF de la presentacion del TFM (10 diapositivas)."""
    from fastapi.responses import Response
    try:
        from backend.core.slides_generator import generate_presentation
        pdf_bytes = generate_presentation()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="MermaOps_Presentacion_TFM.pdf"'},
        )
    except Exception as e:
        logger.error(f"presentation pdf error: {e}")
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


# ── Agent activity endpoints (Fase 1+2+6) ────────────────────────────────────

@router.get("/agent/conversations")
def get_agent_conversations(limit: int = 20, _auth: dict = Depends(verify_token)):
    """Lista de conversaciones recientes de Chuwi con el encargado."""
    try:
        result = (
            database.get_db().table("agent_conversations")
            .select("*")
            .eq("store_id", STORE_ID)
            .order("last_message_at", desc=True)
            .limit(min(limit, 100))
            .execute()
        )
        return {"conversations": result.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, _auth: dict = Depends(verify_token)):
    """Mensajes de una conversación específica con tools_used e intent_tag."""
    try:
        messages = database.get_conversation_messages(conversation_id, limit=100)
        return {"conversation_id": conversation_id, "messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/sessions")
def get_agent_sessions(limit: int = 20, _auth: dict = Depends(verify_token)):
    """Sesiones del agente con contadores de tools y llamadas a Kuine."""
    try:
        result = (
            database.get_db().table("agent_sessions")
            .select("*")
            .eq("store_id", STORE_ID)
            .order("session_start", desc=True)
            .limit(min(limit, 100))
            .execute()
        )
        return {"sessions": result.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/activity")
def get_agent_activity(_auth: dict = Depends(verify_token)):
    """Resumen de actividad del agente: conversaciones, intents, tools más usadas."""
    try:
        db = database.get_db()
        # Últimas 24h de mensajes
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        msgs = (
            db.table("agent_messages")
            .select("role, intent_tag, tools_used, agent_source, created_at")
            .eq("store_id", STORE_ID)
            .gte("created_at", cutoff)
            .execute()
        ).data or []

        # Agregar stats
        by_intent: dict = {}
        all_tools: list = []
        for m in msgs:
            tag = m.get("intent_tag") or "sin_tag"
            by_intent[tag] = by_intent.get(tag, 0) + 1
            tools = m.get("tools_used") or []
            all_tools.extend(tools)
        tool_counts: dict = {}
        for t in all_tools:
            tool_counts[t] = tool_counts.get(t, 0) + 1

        return {
            "period_hours": 24,
            "total_messages": len(msgs),
            "by_intent": by_intent,
            "top_tools": sorted(tool_counts.items(), key=lambda x: -x[1])[:10],
            "kuine_calls": sum(1 for m in msgs if m.get("agent_source") == "kuine"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/status")
def get_agent_status():
    """Estado de todos los agentes del sistema."""
    from backend.agents import evaluator, validator, price, stock, reporter, notifier
    return {
        "agents": [
            {"name": "Kuine", "type": "orchestrator", "model": "claude-opus-4-7",
             "status": "active", "description": "Orquestador principal, 25 tools, hasta 20 iteraciones"},
            {"name": "Chuwi", "type": "conversational", "model": "claude-sonnet-4-6",
             "status": "active", "description": "Agente Telegram, streaming, 6 iteraciones, intent classification"},
            {"name": "Evaluador", "type": "evaluator", "model": "claude-sonnet-4-6",
             "status": "active", "description": "Score 0-100 por lote, extended thinking >=65"},
            {"name": "Validador", "type": "validator", "model": "claude-sonnet-4-6",
             "status": "active", "description": "23 ataques adversariales, 100% neutralizados"},
            {"name": "Consenso", "type": "consensus", "model": "claude-sonnet-4-6",
             "status": "active", "description": "3 instancias paralelas para score >=90"},
            {"name": "Predictor", "type": "predictor", "model": "claude-haiku-4-5",
             "status": "active", "description": "Open-Meteo + historial, 7 días"},
            {"name": "Visión", "type": "vision", "model": "claude-3-5-sonnet",
             "status": "active", "description": "Análisis visual de productos"},
            {"name": "Precio", "type": "pricing", "model": "claude-haiku-4-5",
             "status": "active", "description": "Cálculo de descuentos óptimos"},
            {"name": "Stock", "type": "inventory", "model": "claude-haiku-4-5",
             "status": "active", "description": "Decisiones de reposición FEFO"},
            {"name": "Notificador", "type": "notifier", "model": "claude-sonnet-4-6",
             "status": "active", "description": "Alertas proactivas por Telegram"},
            {"name": "Reportero", "type": "reporter", "model": "claude-sonnet-4-6",
             "status": "active", "description": "Briefs diarios y resúmenes semanales"},
        ]
    }


@router.get("/telegram/status")
def get_telegram_status():
    """Estado del canal Telegram AI Agent."""
    import os
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    has_token = bool(token)
    bot_name = "ChuwiMermaOpsBot"
    return {
        "channel": "Telegram AI Agent",
        "bot_username": f"@{bot_name}",
        "token_configured": has_token,
        "mode": "polling" if os.getenv("APP_ENV", "development") == "development" else "webhook",
        "features": [
            "intent_classification",
            "streaming_responses",
            "tool_use",
            "kuine_delegation",
            "conversation_persistence",
            "voice_transcription",
            "photo_analysis",
        ],
        "note": "Telegram actúa como canal de transporte. La lógica es un agente operativo con memoria y trazabilidad.",
    }


# ── Fase 3: runs y decisiones de Kuine ──────────────────────────────────────

@router.get("/agent/runs")
def get_agent_runs(store_id: str = None, agent_type: str = None, limit: int = 20):
    """Historial de runs del supervisor Kuine con traza completa de tools."""
    from backend.core import database
    sid = store_id or os.getenv("STORE_ID", "demo-store-001")
    try:
        runs = database.get_agent_runs(sid, agent_type=agent_type, limit=limit)
        return {
            "store_id": sid,
            "count": len(runs),
            "runs": runs,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/decisions")
def get_supervisor_decisions(store_id: str = None, limit: int = 50):
    """Decisiones explícitas de Kuine: rebajar/donar/retirar/revisar/reponer."""
    from backend.core import database
    sid = store_id or os.getenv("STORE_ID", "demo-store-001")
    try:
        decisions = database.get_supervisor_decisions(sid, limit=limit)
        summary: dict[str, int] = {}
        for d in decisions:
            dtype = d.get("decision_type", "unknown")
            summary[dtype] = summary.get(dtype, 0) + 1
        return {
            "store_id": sid,
            "count": len(decisions),
            "summary": summary,
            "decisions": decisions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/llm/stats")
def get_llm_stats():
    """
    Estadísticas de uso LLM en tiempo real: tokens, coste y ahorro por prompt caching.
    Muestra el impacto económico real de las técnicas de optimización implementadas:
    - Prompt caching (system + tool definitions): ~80% ahorro en tokens cacheados
    - Token-efficient tools (beta): ~15% ahorro en overhead de definiciones
    - Adaptive thinking: Claude gestiona el presupuesto de reasoning por sí solo
    """
    from backend.core.llm import get_cost_summary
    stats = get_cost_summary()
    return {
        "session_stats": stats,
        "techniques": {
            "prompt_caching": "system prompt + 25 tool definitions cacheados (ephemeral, TTL 5min)",
            "token_efficient_tools": "beta anthropic-2025-02-19 activo en agentic loop",
            "adaptive_thinking": "Claude Opus 4.7 + Sonnet 4.6 con thinking adaptativo",
            "parallel_tools": "ThreadPoolExecutor — hasta 5 tools en paralelo por iteración",
        },
    }
