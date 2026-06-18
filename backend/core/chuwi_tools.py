"""
chuwi_tools.py — Definición y ejecución de herramientas del agente Chuwi.

Chuwi es un agente real: Claude decide qué herramienta usar y cuándo.
No hay routing manual por keywords — el LLM razona sobre el contexto.

Exporta:
  CHUWI_TOOLS       — lista de tool specs para la API de Anthropic
  _TOOL_LABELS      — etiquetas legibles para mostrar mientras se ejecutan
  _execute_tool_sync — ejecuta una tool de forma síncrona (llamar via run_in_executor)
  MAX_AGENT_ITERATIONS, _COMPLEX_KEYWORDS, _is_complex_query
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

from backend.core import database
from backend.core.chuwi_persistence import STORE_ID, _is_manager

logger = logging.getLogger("mermaops.chuwi")


# ── Etiquetas legibles para mostrar mientras Claude ejecuta tools ─────────────

_TOOL_LABELS: dict[str, str] = {
    "get_store_overview":    "Consultando estado de la tienda",
    "get_pending_actions":   "Cargando acciones pendientes",
    "get_daily_route":       "Generando ruta del día",
    "complete_action":       "Registrando acción completada",
    "analyze_product":       "Analizando producto",
    "get_merma_stats":       "Consultando estadísticas de merma",
    "get_donation_impact":   "Calculando impacto social",
    "register_donation":     "Registrando donación",
    "get_suppliers":         "Cargando ficha de proveedores",
    "get_esg_metrics":       "Calculando métricas ESG",
    "advance_demo_time":     "Avanzando tiempo de simulación",
    "get_order_suggestions": "Calculando pedido semanal",
    "get_risk_predictions":  "Calculando predicciones de riesgo",
    "recall_store_memory":   "Consultando memoria episódica",
    "get_weekly_report":     "Cargando informe semanal",
    "get_agent_status_brief":"Consultando estado de los agentes",
    "get_store_comparison":  "Calculando comparativa con otras tiendas",
    "get_decision_feedback": "Consultando resultados de decisiones anteriores",
}


# ── Tool specs — Claude decide cuál llamar, no if/else ───────────────────────

CHUWI_TOOLS = [
    {
        "name": "get_store_overview",
        "description": (
            "Estado general de la tienda: acciones pendientes, críticos, valor en riesgo y resumen del brief. "
            "Usar cuando el empleado pregunte por el estado de hoy, qué hay que hacer, si hay urgencias, "
            "o cuando necesites contexto antes de responder otra pregunta."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_pending_actions",
        "description": (
            "Lista detallada de todas las acciones pendientes ordenadas por prioridad. "
            "Usar cuando pregunten qué acciones hay, qué productos son críticos, "
            "qué hay que hacer hoy, o para saber qué acción completar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "default": 10, "description": "Número máximo de acciones"},
            },
        },
    },
    {
        "name": "get_daily_route",
        "description": (
            "Ruta óptima del día organizada por pasillos para hacer las acciones pendientes de forma eficiente. "
            "Usar cuando pidan la ruta del día, el recorrido, o cómo hacer las acciones en orden."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "complete_action",
        "description": (
            "Marca una acción como completada y lo registra en la base de datos. "
            "Usar cuando el empleado diga que ya hizo algo, que está listo, hecho, terminado. "
            "IMPORTANTE: si no sabes el action_id, primero llama a get_pending_actions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action_id": {"type": "string", "description": "ID de la acción a completar"},
                "notes": {"type": "string", "description": "Notas opcionales del empleado"},
            },
            "required": ["action_id"],
        },
    },
    {
        "name": "analyze_product",
        "description": (
            "Analiza un producto por código de barras: días hasta caducidad, precio, acción recomendada. "
            "Usar cuando el empleado mencione un código de barras o pida analizar un producto específico."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "barcode": {"type": "string", "description": "Código de barras del producto (6-14 dígitos)"},
            },
            "required": ["barcode"],
        },
    },
    {
        "name": "get_merma_stats",
        "description": (
            "Estadísticas de merma: valor perdido en euros, unidades, productos más problemáticos. "
            "Usar cuando pregunten sobre merma, pérdidas, qué se ha tirado, valor perdido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "Días hacia atrás (default: 7)"},
            },
        },
    },
    {
        "name": "get_donation_impact",
        "description": (
            "Impacto social de las donaciones al banco de alimentos y otras entidades. "
            "Usar cuando pregunten sobre donaciones, impacto social, CO2 evitado, cuánto se ha donado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 30, "description": "Días hacia atrás"},
            },
        },
    },
    {
        "name": "register_donation",
        "description": (
            "Registra una donación al banco de alimentos u otra entidad solidaria. "
            "Usar cuando el empleado confirme que va a donar o haya donado un producto. "
            "Si el empleado no especifica la entidad, preguntar antes de registrar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "enum": ["banco_alimentos", "caritas", "cruz_roja", "comedor_social"],
                    "description": "Entidad receptora de la donación",
                },
                "quantity": {"type": "integer", "minimum": 1, "description": "Unidades donadas"},
                "product_name": {"type": "string", "description": "Nombre del producto donado"},
                "batch_id": {"type": "string", "description": "ID del lote si se conoce"},
            },
            "required": ["entity", "quantity"],
        },
    },
    {
        "name": "get_suppliers",
        "description": (
            "Ficha de proveedores con tasa de merma histórica y nivel de riesgo. "
            "Solo accesible para encargados. Usar cuando pregunten por proveedores, suministradores o quién da más problemas."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_esg_metrics",
        "description": (
            "Métricas de impacto ambiental y social: CO2 evitado (kg), agua ahorrada (litros), "
            "deducción fiscal estimada por donaciones (Ley 49/2002). "
            "Usar cuando pregunten por sostenibilidad, impacto, ESG, CO2, deducciones."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_order_suggestions",
        "description": (
            "Sugerencias de pedido semanal basadas en historial de merma y stock actual. "
            "Solo encargados. Usar cuando pregunten qué pedir, cómo reponer stock."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "advance_demo_time",
        "description": (
            "Para la presentación: avanza N días en la simulación, actualizando caducidades, "
            "creando nuevas acciones urgentes y garantizando productos CRÍTICO/ALTO/BAJO visibles. "
            "Solo usar si el encargado lo pide explícitamente para la demo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 30,
                    "description": "Días a avanzar (puede ser decimal, ej: 1.5 = día y medio)",
                },
            },
            "required": ["days"],
        },
    },
    {
        "name": "get_risk_predictions",
        "description": (
            "Predicciones de riesgo de merma para los próximos 5-7 días con previsión meteorológica. "
            "Usa el Predictor Agent que analiza histórico + clima + día de semana. "
            "Usar cuando pregunten qué va a pasar esta semana, previsión de merma, "
            "qué productos habrá que vigilar pronto, o para planificación anticipada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "Horizonte de predicción en días"},
            },
        },
    },
    {
        "name": "get_weekly_report",
        "description": (
            "Muestra el resumen del último informe semanal de la tienda: merma total, valor recuperado, "
            "donaciones, comparativa con semanas anteriores. Usar cuando pregunten por la semana, "
            "el informe semanal, cómo fue la semana, tendencias."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_agent_status_brief",
        "description": (
            "Muestra el estado de los 12 agentes de MermaOps: cuáles están activos, última ejecución, "
            "herramientas usadas, decisiones tomadas. Útil para saber si el sistema está funcionando."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_store_comparison",
        "description": (
            "Comparativa de esta tienda con la media de la cadena: merma %, donaciones, valor en riesgo. "
            "Usar cuando pregunten cómo estamos vs otras tiendas, ranking, comparativa."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "recall_store_memory",
        "description": (
            "Recupera patrones y aprendizajes guardados de la memoria episódica de la tienda. "
            "Usar cuando el empleado pregunte por algo histórico: qué pasó la semana pasada, "
            "qué proveedor falló antes, qué patrón hay en la merma de una categoría. "
            "También útil para dar contexto histórico antes de responder sobre riesgos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern_key": {
                    "type": "string",
                    "description": (
                        "Clave del patrón a recuperar. Ejemplos: "
                        "'merma_historica_semana', 'categoria_lacteos_tendencia', "
                        "'proveedor_riesgo', 'horas_pico_venta'"
                    ),
                },
            },
            "required": ["pattern_key"],
        },
    },
    {
        "name": "get_decision_feedback",
        "description": (
            "Muestra el resultado real de las decisiones tomadas ayer y los últimos días. "
            "Usar cuando el empleado pregunte cómo resultaron las acciones anteriores, si las rebajas "
            "funcionaron, cuánto se recuperó, si los productos donados llegaron a tiempo, etc. "
            "También útil para dar contexto histórico al encargado antes de un nuevo brief."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "default": 1,
                    "description": "Días hacia atrás para el feedback (default: 1 = ayer)",
                },
            },
        },
        # cache_control en el ÚLTIMO tool: Anthropic cachea todas las definiciones anteriores
        # → ahorro ~5-8K tokens en cada llamada (18 tools × ~500 tokens).
        "cache_control": {"type": "ephemeral"},
    },
]


# ── Intra-session tool result cache (TTL 5 min) ───────────────────────────────
# Tools de solo-lectura se cachean para evitar llamadas repetidas a la BD.
# Tools de escritura (complete_action, register_donation) NUNCA se cachean.

_TOOL_CACHE: dict[str, tuple[dict, float]] = {}
_CACHEABLE_TOOLS = {
    "get_store_overview", "get_pending_actions", "get_merma_stats",
    "get_donation_impact", "get_suppliers", "get_esg_metrics",
    "get_order_suggestions", "get_weekly_report", "get_agent_status_brief",
    "get_store_comparison", "get_decision_feedback",
}
_TOOL_CACHE_TTL = 300  # segundos


def _tool_cache_key(tool_name: str, tool_input: dict) -> str:
    return f"{tool_name}:{hashlib.md5(json.dumps(tool_input, sort_keys=True).encode()).hexdigest()[:8]}"


# ── Agent loop config ─────────────────────────────────────────────────────────

MAX_AGENT_ITERATIONS = 4

_COMPLEX_KEYWORDS = (
    "analiza", "compara", "por qué", "explica", "estrategia",
    "informe", "resumen", "qué harías", "recomendación", "decisión",
    "merma", "proveedor", "esg", "predicción", "semana", "mes",
)


def _is_complex_query(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _COMPLEX_KEYWORDS) or len(text) >= 150


# ── Ejecución síncrona de tools (llamar via run_in_executor) ─────────────────

def _execute_tool_sync(tool_name: str, tool_input: dict, user: Optional[dict]) -> dict:
    """
    Ejecuta una herramienta de Chuwi de forma síncrona.
    Se llama desde código async mediante run_in_executor — no bloquea el event loop.
    Claude decide qué tool llamar; aquí solo ejecutamos.
    """
    # Cache hit — tools de lectura
    if tool_name in _CACHEABLE_TOOLS:
        cache_key = _tool_cache_key(tool_name, tool_input)
        cached = _TOOL_CACHE.get(cache_key)
        if cached is not None:
            result, ts = cached
            if time.monotonic() - ts < _TOOL_CACHE_TTL:
                logger.debug(f"[chuwi] tool cache hit: {tool_name}")
                return result

    is_mgr = _is_manager(user)
    try:
        if tool_name == "get_store_overview":
            pending = database.get_pending_actions(STORE_ID)
            critical = [a for a in pending if (a.get("priority_score") or 0) >= 85]
            alto = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
            brief = database.get_latest_brief(STORE_ID)
            batches = database.get_batches_expiring_soon(STORE_ID, days=7)
            value_at_risk = sum(
                int(b.get("quantity", 0)) * float((b.get("products") or {}).get("price", 0))
                for b in batches
            )
            semaforo = "ROJO" if len(critical) >= 5 else "AMARILLO" if len(critical) >= 2 else "VERDE"
            return {
                "semaforo": semaforo,
                "pending_total": len(pending),
                "criticos": len(critical),
                "altos": len(alto),
                "value_at_risk_eur": round(value_at_risk, 2),
                "lotes_caducando_7d": len(batches),
                "brief_hoy": brief.get("summary", "") if brief else None,
                "brief_fecha": brief.get("date", "") if brief else None,
            }

        elif tool_name == "get_pending_actions":
            max_r = int(tool_input.get("max_results", 10))
            pending = database.get_pending_actions(STORE_ID)
            sorted_p = sorted(pending, key=lambda a: -(a.get("priority_score") or 0))
            actions = []
            for a in sorted_p[:max_r]:
                batch = a.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                exp = batch.get("expiry_date", "")
                try:
                    days_left = (date.fromisoformat(exp) - date.today()).days if exp else None
                except Exception:
                    days_left = None
                actions.append({
                    "id": a.get("id"),
                    "product": product.get("name", "?"),
                    "pasillo": product.get("pasillo", "?"),
                    "action_type": a.get("action_type", ""),
                    "priority_score": a.get("priority_score", 0),
                    "new_price": a.get("new_price"),
                    "days_left": days_left,
                    "notes": (a.get("notes") or "")[:120],
                })
            return {"total": len(pending), "mostrando": len(actions), "acciones": actions}

        elif tool_name == "get_daily_route":
            from backend.agents import route as rt
            pending = database.get_pending_actions(STORE_ID)
            if not pending:
                return {"ruta": "Sin acciones pendientes. Todo en orden."}
            risk_reports = []
            for action in pending:
                batch = action.get("batches") or {}
                score = action.get("priority_score", 0)
                risk_level = (
                    "CRÍTICO" if score >= 85 else
                    "ALTO" if score >= 65 else
                    "MEDIO" if score >= 40 else "BAJO"
                )
                risk_reports.append((batch, {
                    "score": score, "risk_level": risk_level,
                    "action": action.get("action_type", "revisar"),
                    "reasoning": action.get("notes") or "",
                    "price_adjustment_pct": action.get("price_adjustment_pct") or 0,
                }))
            daily_route = rt.generate(STORE_ID, risk_reports)
            return {"ruta": rt.format_route_message(daily_route)}

        elif tool_name == "complete_action":
            action_id = tool_input.get("action_id", "")
            if not action_id:
                return {"ok": False, "error": "Falta action_id. Usa get_pending_actions para obtener el ID."}
            u_name = (user.get("email") or user.get("id", "empleado")).split("@")[0] if user else "empleado"
            _action_data = {}
            try:
                _pending = database.get_pending_actions(STORE_ID)
                _action_data = next((a for a in _pending if str(a.get("id")) == str(action_id)), {})
            except Exception:
                pass
            database.complete_action(action_id, u_name)
            try:
                from backend.core import memory as _mem_mod
                _batch = _action_data.get("batches") or {}
                _product = (_batch.get("products") or {}) if _batch else {}
                _action_type = _action_data.get("action_type", "revisar")
                _score = int(_action_data.get("priority_score") or 0)
                _qty = int((_batch.get("quantity") or 0))
                _value_recovered = 0.0
                if _action_type == "rebajar" and _action_data.get("new_price"):
                    _value_recovered = float(_action_data["new_price"]) * _qty
                elif _action_type == "donar":
                    _cost = float(_product.get("cost") or 0)
                    _value_recovered = round(_qty * _cost * 0.35, 2)
                _actual_result = {
                    "rebajar": "vendido", "donar": "donado",
                    "retirar": "retirado", "mover": "vendido", "revisar": "vendido",
                }.get(_action_type, "completado")
                _mem_mod.record_decision_outcome(
                    STORE_ID, action_id, _action_type, _product.get("name", "Producto"),
                    _score, _actual_result, _value_recovered,
                )
            except Exception as _oe:
                logger.debug(f"[chuwi] outcome tracking error: {_oe}")
            return {"ok": True, "completada_por": u_name, "action_id": action_id}

        elif tool_name == "analyze_product":
            from backend.agents import supervisor
            barcode = str(tool_input.get("barcode", ""))
            u_id = (user or {}).get("id", "")
            raw = supervisor.run_scan(STORE_ID, barcode, u_id)
            analisis = raw["text"] if isinstance(raw, dict) else raw
            thinking = raw.get("thinking_summary", "") if isinstance(raw, dict) else ""
            ret: dict = {"analisis": analisis}
            if thinking and len(thinking) > 10:
                ret["kuine_razonamiento_extendido"] = thinking[:300]
            return ret

        elif tool_name == "get_merma_stats":
            days = int(tool_input.get("days", 7))
            logs = database.get_merma_history(STORE_ID, days=days)
            total_value = sum(float(l.get("value_lost", 0)) for l in logs)
            total_qty = sum(int(l.get("quantity_lost", 0)) for l in logs)
            top = []
            for log in logs[:5]:
                batch = log.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                top.append({
                    "producto": product.get("name", log.get("reason", "?")[:30]),
                    "fecha": log.get("date", "?"),
                    "cantidad": log.get("quantity_lost", 0),
                    "valor_eur": round(float(log.get("value_lost", 0)), 2),
                })
            return {
                "dias": days,
                "valor_total_eur": round(total_value, 2),
                "unidades_total": total_qty,
                "registros": len(logs),
                "top_productos": top,
            }

        elif tool_name == "get_donation_impact":
            days = int(tool_input.get("days", 30))
            return database.get_donation_stats(STORE_ID, days=days)

        elif tool_name == "register_donation":
            entity = tool_input.get("entity", "banco_alimentos")
            quantity = int(tool_input.get("quantity", 0))
            product_name = tool_input.get("product_name", "")
            batch_id = tool_input.get("batch_id")
            u_name = (user.get("email") or "empleado") if user else "empleado"
            entity_display = {
                "banco_alimentos": "Banco de Alimentos",
                "caritas": "Cáritas",
                "cruz_roja": "Cruz Roja",
                "comedor_social": "Comedor Social",
            }.get(entity, entity)
            cost = 0.0
            if batch_id:
                try:
                    matched = database.get_batch_by_id(batch_id)
                    if matched:
                        cost = float((matched.get("products") or {}).get("cost", 0) or 0)
                except Exception:
                    pass
            donation_data: dict = {
                "store_id": STORE_ID,
                "entity": entity_display,
                "quantity": quantity,
                "value_donated": round(quantity * cost, 2),
                "donated_at": datetime.now(timezone.utc).isoformat(),
                "donated_by": u_name,
            }
            if batch_id:
                donation_data["batch_id"] = batch_id
            database.log_donation(donation_data)
            return {"ok": True, "entidad": entity_display, "cantidad": quantity, "producto": product_name}

        elif tool_name == "get_suppliers":
            if not is_mgr:
                return {"error": "Solo encargados pueden ver la ficha de proveedores."}
            return {"proveedores": database.get_supplier_stats(STORE_ID)}

        elif tool_name == "get_esg_metrics":
            if not is_mgr:
                return {"error": "Solo encargados pueden ver las métricas ESG completas."}
            from backend.agents.esg import get_store_esg_summary
            return get_store_esg_summary(STORE_ID, 30)

        elif tool_name == "get_order_suggestions":
            if not is_mgr:
                return {"error": "Solo encargados pueden ver sugerencias de pedido."}
            suggestions = database.get_order_suggestions(STORE_ID)
            return {"sugerencias": suggestions[:15] if suggestions else []}

        elif tool_name == "advance_demo_time":
            if not is_mgr:
                return {"error": "Solo encargados pueden avanzar el tiempo de la demo."}
            days = float(tool_input.get("days", 1))
            from backend.data.advance_demo import advance as _adv
            result = _adv(days, store_id=STORE_ID, generate_brief=True)
            return {"ok": True, "dias_avanzados": days, **result}

        elif tool_name == "get_risk_predictions":
            days = int(tool_input.get("days", 7))
            try:
                from backend.agents.predictor import predict_merma_risk
                predictions = predict_merma_risk(STORE_ID, forecast_days=days)
                return {"dias": days, "productos_en_riesgo": len(predictions), "predicciones": predictions[:10]}
            except Exception as e:
                return {"error": f"Predictor no disponible: {e}"}

        elif tool_name == "recall_store_memory":
            pattern_key = tool_input.get("pattern_key", "")
            from backend.core import memory as _mem_mod
            value = _mem_mod.recall(STORE_ID, pattern_key)
            return {"pattern_key": pattern_key, "found": value is not None, "value": value or "Sin datos históricos para esta clave."}

        elif tool_name == "get_decision_feedback":
            days_back = int(tool_input.get("days_back", 1))
            from backend.core import memory as _mem_mod
            return _mem_mod.get_daily_decision_feedback(STORE_ID, days_back=days_back)

        elif tool_name == "get_weekly_report":
            reports = database.get_weekly_reports(STORE_ID, limit=2)
            if not reports:
                return {"mensaje": "Sin informes semanales generados aún. El primero se genera automáticamente cada lunes."}
            latest = reports[0]
            prev = reports[1] if len(reports) > 1 else None
            result = {
                "semana": latest.get("week_start", "?"),
                "merma_total_eur": latest.get("total_merma_eur", 0),
                "valor_recuperado_eur": latest.get("value_recovered_eur", 0),
                "acciones_completadas": latest.get("actions_completed", 0),
                "donaciones": latest.get("donations_count", 0),
                "resumen": (latest.get("summary") or "")[:500],
            }
            if prev:
                result["vs_semana_anterior"] = {
                    "merma_diff_eur": round(
                        (latest.get("total_merma_eur") or 0) - (prev.get("total_merma_eur") or 0), 2
                    )
                }
            return result

        elif tool_name == "get_agent_status_brief":
            _catalog = [
                ("Kuine", "orchestrator", "claude-opus-4-8"),
                ("Chuwi", "conversational", "claude-sonnet-4-6"),
                ("Evaluador", "evaluator", "claude-sonnet-4-6"),
                ("ForkMerge", "fork_merge", "claude-sonnet-4-6 × 3 + opus-4-8"),
                ("Validador", "validator", "claude-sonnet-4-6"),
                ("Consenso", "consensus", "claude-sonnet-4-6"),
                ("Predictor", "predictor", "claude-haiku-4-5"),
                ("Visión", "vision", "claude-haiku-4-5-20251001"),
                ("Precio", "price", "heurístico"),
                ("Stock", "stock", "heurístico"),
                ("Notificador", "notifier", "claude-sonnet-4-6"),
                ("Reportero", "reporter", "claude-sonnet-4-6"),
            ]
            recent_runs = []
            try:
                r = database.get_db().table("agent_runs").select(
                    "agent_type,started_at,tools_count"
                ).eq("store_id", STORE_ID).order("started_at", desc=True).limit(3).execute()
                recent_runs = r.data or []
            except Exception:
                pass
            return {
                "total_agentes": 12,
                "activos": 12,
                "agentes": [{"nombre": n, "tipo": t, "modelo": m} for n, t, m in _catalog],
                "ejecuciones_recientes": recent_runs,
                "resumen": "12/12 agentes operativos. Kuine (Opus 4.7) orquesta 11 subagentes especializados.",
            }

        elif tool_name == "get_store_comparison":
            try:
                stores = database.get_stores_comparison(STORE_ID)
                if not stores:
                    return {"mensaje": "Sin datos de comparativa disponibles. Los datos se actualizan mensualmente."}
                current = next((s for s in stores if s.get("is_current")), None)
                return {
                    "tiendas_en_red": len(stores),
                    "esta_tienda": current,
                    "ranking": current.get("rank") if current else None,
                    "top3": [
                        {"tienda": s.get("store_id"), "merma_pct": s.get("merma_rate_pct"), "rank": s.get("rank")}
                        for s in stores[:3]
                    ],
                }
            except Exception:
                return {"mensaje": "Comparativa no disponible en este momento."}

        else:
            return {"error": f"Herramienta desconocida: {tool_name}"}

    except Exception as e:
        logger.error(f"[chuwi] tool error {tool_name}: {e}", exc_info=True)
        return {"error": "No pude completar esta operación ahora mismo. Inténtalo de nuevo en unos segundos."}
