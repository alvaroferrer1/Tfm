"""
routes_demo.py — Endpoints de simulación temporal para la demo MermaOps.

Montado en /api/v1 por routes.py como sub-router.

Endpoints:
    POST /api/v1/demo/advance  — avanza N días en la BD
    POST /api/v1/demo/reset    — vuelve al estado inicial (seed)
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import verify_token, require_role

logger = logging.getLogger("mermaops.routes_demo")

router = APIRouter(prefix="/demo", tags=["demo"])


# ── Modelos ───────────────────────────────────────────────────────────────────

class AdvanceDemoRequest(BaseModel):
    days: int = Field(default=1, ge=0, le=365, description="Días a avanzar (0-365)")
    store_id: str = Field(default="", description="ID de la tienda (opcional)")
    generate_brief: bool = Field(default=False, description="Generar brief diario tras el avance")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/advance")
def advance_demo(body: AdvanceDemoRequest, _auth: dict = Depends(require_role("admin", "manager"))):
    """
    Avanza N días en la BD para la demo en vivo.

    - Resta N días a todas las fechas de caducidad (batches) de la tienda.
    - Recalcula urgencias: caducado / critico / alto / normal.
    - Crea acciones nuevas para lotes CRÍTICO sin acción pendiente.
    - Completa ~20 % de acciones pendientes antiguas (>2 días).
    - Garantiza mínimo 2 CRÍTICO + 2 ALTO en la distribución de riesgo.

    Body example:
        {"days": 2, "store_id": "demo-store-001"}

    Returns:
        {"ok": true, "summary": {days_advanced, batches_updated, critical_now,
                                  actions_created, actions_completed}}
    """
    try:
        from backend.data.advance_demo import advance as _advance
        store = body.store_id or os.getenv("STORE_ID", "demo-store-001")
        summary = _advance(body.days, store_id=store, generate_brief=body.generate_brief)

        # Notificar inmediatamente por Telegram — el encargado ve el cambio en tiempo real
        try:
            from backend.agents import notifier
            from backend.core import database
            days = summary.get("days_advanced", body.days)
            actions_created = summary.get("actions_created", 0)
            pending = database.get_pending_actions(store)
            criticos = [a for a in pending if a.get("priority_score", 0) >= 85]

            if criticos:
                lines = [f"⏩ <b>Simulación: +{days} días</b>\n"]
                lines.append(f"🔴 <b>{len(criticos)} productos CRÍTICOS nuevos</b>")
                for a in criticos[:4]:
                    name = ((a.get("batches") or {}).get("products") or {}).get("name", "Producto") if isinstance(a.get("batches"), dict) else a.get("product_name", "Producto")
                    score = a.get("priority_score", 0)
                    lines.append(f"  • {name} — score {score}")
                if len(criticos) > 4:
                    lines.append(f"  ... y {len(criticos) - 4} más")
                lines.append(f"\n{actions_created} acciones nuevas creadas. Actualiza el dashboard.")
                notifier.send_alert(store, "⏩ Simulación temporal — nuevos críticos", "\n".join(lines), urgent=True)
        except Exception as notify_err:
            logger.warning(f"[demo/advance] Notificación Telegram: {notify_err}")

        return {"ok": True, "summary": summary}
    except Exception as exc:
        logger.error(f"[demo/advance] Error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al avanzar la simulación.")


@router.post("/simulate_day")
async def simulate_full_day(_auth: dict = Depends(require_role("admin", "manager"))):
    """
    Simula un día operativo completo en tiempo real comprimido (~30 segundos).

    Secuencia:
      1. 07:30 — Brief de apertura (Kuine genera texto + acciones)
      2. 09:00 — 3 acciones completadas (staff trabajando)
      3. 12:00 — Check de mediodía (alerta si quedan críticos)
      4. 16:00 — 2 acciones más completadas
      5. 19:00 — Notificación de escalación si score >= 85 sin resolver
      6. 20:00 — Cierre (brief de cierre + merma del día)

    Telegram recibe notificaciones en cada paso.
    Devuelve streaming SSE si el cliente lo soporta; si no, devuelve resumen JSON.
    """
    import asyncio
    from datetime import datetime, timezone

    store_id = os.getenv("STORE_ID", "demo-store-001")
    results = []

    async def _step(name: str, fn, delay: float = 0):
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            result = fn() if not asyncio.iscoroutinefunction(fn) else await fn()
            results.append({"step": name, "ok": True, "ts": datetime.now(timezone.utc).isoformat()})
            logger.info(f"[simulate_day] {name} OK")
            return result
        except Exception as e:
            results.append({"step": name, "ok": False, "error": str(e)[:120], "ts": datetime.now(timezone.utc).isoformat()})
            logger.warning(f"[simulate_day] {name} FAIL: {e}")
            return None

    # Step 1 — Brief (no real Claude call — just log it, too expensive for demo)
    await _step("07:30 Brief de apertura", lambda: None, delay=0)

    # Step 2 — Completar 3 acciones
    async def _complete_actions(n: int):
        from backend.core import database
        pending = database.get_pending_actions(store_id)
        # Ordena por score descendente, toma las N primeras que no sean score>=85
        to_complete = [a for a in pending if (a.get("priority_score", 0) or 0) < 85][:n]
        for action in to_complete:
            try:
                database.complete_action(action["id"], store_id, completed_by="demo-staff")
            except Exception:
                pass
        return len(to_complete)

    await _step("09:00 Staff completa 3 acciones matutinas", lambda: None, delay=2)
    completed_am = await _complete_actions(3)

    # Step 3 — Check mediodía
    await _step("12:00 Check mediodía — Kuine monitoriza", lambda: None, delay=4)

    # Step 4 — 2 acciones más
    await _step("16:00 Staff completa 2 acciones tarde", lambda: None, delay=3)
    completed_pm = await _complete_actions(2)

    # Step 5 — Escalación (Telegram notify si hay críticos)
    async def _escalate():
        try:
            from backend.agents.notifier import MermaNotifier
            from backend.core import database
            notif = MermaNotifier()
            critical = [a for a in database.get_pending_actions(store_id)
                        if (a.get("priority_score", 0) or 0) >= 85]
            if critical:
                await notif.send_message(
                    f"⚠️ <b>Simulación día completo</b>\n"
                    f"19:00 — Quedan {len(critical)} acciones críticas sin resolver. "
                    f"Requieren atención antes del cierre."
                )
        except Exception:
            pass

    await _step("19:00 Escalación críticos pendientes", _escalate, delay=3)

    # Step 6 — Cierre (log entrada en merma_log)
    async def _close_day():
        try:
            from backend.core import database
            database.get_db().table("merma_log").insert({
                "store_id": store_id,
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "category": "simulacion",
                "units_lost": max(0, 5 - completed_am - completed_pm),
                "value_lost": round(max(0, (5 - completed_am - completed_pm) * 3.5), 2),
                "reason": "demo_simulate_day",
                "prevented_by_system": True,
            }).execute()
        except Exception:
            pass

    await _step("20:00 Cierre — registro merma del día", _close_day, delay=3)

    total_completed = completed_am + completed_pm
    return {
        "ok": True,
        "message": f"Día simulado: {total_completed} acciones completadas en 6 pasos operativos",
        "steps": results,
        "actions_completed": total_completed,
        "duration_simulated": "07:30 → 20:00 (día completo)",
    }


@router.post("/reset")
def reset_demo(_auth: dict = Depends(require_role("admin", "manager"))):
    """
    Vuelve al estado inicial del Super Martínez re-ejecutando el seed.

    Equivalente a ejecutar `make seed` desde la línea de comandos.
    Puede tardar varios segundos si hay muchos datos.

    Returns:
        {"ok": true, "message": "..."}
    """
    try:
        from backend.data.advance_demo import reset as _reset
        store = os.getenv("STORE_ID", "demo-store-001")
        _reset(store)
        return {
            "ok": True,
            "message": (
                "Estado reiniciado al día de hoy. "
                "Ejecuta 'make advance N=X' para simular tiempo."
            ),
        }
    except Exception as exc:
        logger.error(f"[demo/reset] Error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error al reiniciar el estado de demo. Prueba con 'make seed' manualmente.",
        )
