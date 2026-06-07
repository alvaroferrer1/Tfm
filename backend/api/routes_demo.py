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
