"""
Kuine — el cerebro orquestador de MermaOps.

Kuine investiga activamente la tienda usando herramientas especializadas, razona sobre
cada producto, coordina subagentes, crea acciones operativas y aprende patrones.
No procesa datos pre-seleccionados: DECIDE qué investigar, en qué orden, y qué hacer.

Identidad: Kuine es el agente orquestador. Chuwi es la interfaz con el encargado.
"""
from __future__ import annotations
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

logger = logging.getLogger("mermaops.supervisor")

from backend.core import llm, database, memory as mem, knowledge
from backend.agents import evaluator, price, stock, route, reporter, notifier, validator

# Persiste el run_id del último brief por tienda para que el executor pueda asociar decisiones
_LAST_BRIEF_RUN_ID: dict[str, str] = {}


# ── Definición de herramientas para el loop agéntico ────────────────────────

SUPERVISOR_TOOLS = [
    # ── Think tool (Anthropic, 2025) ─────────────────────────────────────────
    # Permite al agente razonar explícitamente entre llamadas a herramientas,
    # especialmente útil para analizar outputs complejos antes de actuar.
    # Referencia: https://www.anthropic.com/engineering/claude-think-tool
    # Benchmark: +54% en τ-Bench airline domain (Anthropic, 2025).
    {
        "name": "think",
        "description": (
            "Piensa en voz alta antes de tomar una decisión compleja. "
            "Úsalo para: (1) analizar los resultados de una herramienta antes de actuar, "
            "(2) verificar que tu razonamiento es correcto antes de crear una acción, "
            "(3) resolver conflictos entre datos (ej: el evaluador dice CRÍTICO pero la normativa "
            "permite venta hasta mañana). No recupera datos nuevos — solo razona con lo que ya tienes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "thought": {
                    "type": "string",
                    "description": "Tu razonamiento interno. Sé específico: producto, datos, conclusión.",
                },
            },
            "required": ["thought"],
        },
    },
    {
        "name": "get_expiring_batches",
        "description": (
            "Obtiene todos los lotes activos que caducan en los próximos N días. "
            "SIEMPRE llama esto primero para ver el panorama completo del día. "
            "Incluye datos del producto (nombre, precio, coste, ubicación, categoría)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Horizonte en días. 1=solo hoy, 3=urgentes, 7=semana completa.",
                },
                "category": {
                    "type": "string",
                    "description": "Filtrar por categoría (opcional): panaderia, lacteos, carne, pescado, fruta, verdura",
                },
            },
            "required": ["days"],
        },
    },
    {
        "name": "get_warehouse_stock",
        "description": (
            "Consulta el stock disponible en almacén para un producto. "
            "Crítico para decisiones de reposición y FEFO."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "recall_memory",
        "description": (
            "Recupera un patrón aprendido de la memoria episódica. "
            "Úsalo para recordar velocidades de venta históricas, patrones de merma "
            "por categoría, o comportamientos de días anteriores similares. "
            "Claves útiles: 'categoria_panaderia_velocidad', 'merma_historica_semana', 'horas_pico_venta'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern_key": {
                    "type": "string",
                    "description": "Clave del patrón a recuperar.",
                },
            },
            "required": ["pattern_key"],
        },
    },
    {
        "name": "store_memory",
        "description": (
            "Guarda un patrón nuevo en la memoria episódica. "
            "Úsalo cuando detectes algo interesante: un producto que siempre genera merma "
            "un día concreto, una categoría con patrón inesperado, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern_key": {"type": "string"},
                "pattern_value": {
                    "type": "string",
                    "description": "Descripción clara del patrón observado.",
                },
            },
            "required": ["pattern_key", "pattern_value"],
        },
    },
    {
        "name": "evaluate_product_risk",
        "description": (
            "Evalúa el riesgo de merma de un producto con análisis profundo. "
            "Devuelve nivel de riesgo (CRÍTICO/ALTO/MEDIO/BAJO), score 0-100, "
            "acción recomendada y porcentaje de descuento óptimo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "product_name": {"type": "string"},
                "category": {"type": "string"},
                "price": {"type": "number"},
                "cost": {"type": "number"},
                "days_left": {"type": "integer"},
                "quantity": {"type": "integer"},
                "warehouse_qty": {
                    "type": "integer",
                    "description": "Stock en almacén. 0 si no se ha consultado.",
                },
                "historical_context": {
                    "type": "string",
                    "description": "Contexto histórico de la memoria episódica si está disponible.",
                },
            },
            "required": [
                "product_id", "product_name", "category",
                "price", "cost", "days_left", "quantity",
            ],
        },
    },
    {
        "name": "calculate_discount",
        "description": (
            "Calcula el descuento exacto y el nuevo precio para un producto. "
            "Respeta el margen mínimo sobre coste. "
            "Devuelve descuento%, nuevo precio, y texto de instrucción para el empleado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "product_name": {"type": "string"},
                "price": {"type": "number"},
                "cost": {"type": "number"},
                "days_left": {"type": "integer"},
                "risk_level": {
                    "type": "string",
                    "enum": ["CRÍTICO", "ALTO", "MEDIO", "BAJO"],
                },
            },
            "required": ["product_id", "product_name", "price", "cost", "days_left", "risk_level"],
        },
    },
    {
        "name": "create_action",
        "description": (
            "Crea una acción operativa en la base de datos para que el empleado la ejecute. "
            "Llama esto para CADA producto que requiera intervención. "
            "Las notas deben ser instrucciones específicas y accionables."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string"},
                "batch_id": {"type": "string"},
                "action_type": {
                    "type": "string",
                    "enum": ["rebajar", "retirar", "donar", "mover", "revisar", "reponer"],
                },
                "priority_score": {
                    "type": "integer",
                    "description": "Prioridad 0-100. CRÍTICO >= 85, ALTO 65-84, MEDIO 40-64, BAJO < 40.",
                },
                "notes": {
                    "type": "string",
                    "description": "Instrucción específica para el empleado. Incluir nuevo precio si aplica.",
                },
                "price_adjustment_pct": {
                    "type": "integer",
                    "description": "Descuento en % a aplicar (0-100). Rellenar si action_type es rebajar.",
                },
                "new_price": {
                    "type": "number",
                    "description": "Precio rebajado calculado en €. Rellenar si action_type es rebajar.",
                },
            },
            "required": ["store_id", "batch_id", "action_type", "priority_score"],
        },
    },
    {
        "name": "get_pending_actions",
        "description": "Obtiene las acciones pendientes actuales ordenadas por prioridad.",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string"},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "search_food_regulations",
        "description": (
            "Busca normativa y regulaciones de seguridad alimentaria. "
            "Úsalo cuando tengas dudas sobre si un producto debe retirarse o rebajarse, "
            "o sobre temperaturas, fechas de consumo preferente vs caducidad, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Consulta sobre normativa, ej: 'caducidad carne fresca', 'donar pescado'",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_day_context",
        "description": (
            "Obtiene el contexto del día actual: día de la semana, hora, "
            "y resumen del brief más reciente. Útil para ajustar predicciones de venta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_merma_history",
        "description": (
            "Historial de merma real de los últimos N días. "
            "Útil para comparar el riesgo de hoy con lo que realmente se perdió antes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Días hacia atrás a consultar (por defecto 7).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "evaluate_all_products_parallel",
        "description": (
            "Evalúa TODOS los lotes activos en paralelo en una sola llamada. "
            "MUCHO MÁS RÁPIDO que llamar evaluate_product_risk para cada producto individualmente. "
            "Úsalo al inicio del brief para obtener el panorama completo de golpe. "
            "Devuelve lista ordenada por score (críticos primero) con estadísticas agregadas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Horizonte en días (1-14). Usa 7 para el brief completo.",
                },
            },
            "required": ["days"],
        },
    },
    {
        "name": "get_supplier_stats",
        "description": (
            "Ficha de proveedores: merma histórica por proveedor. "
            "Muestra qué proveedor genera más merma para fundamentar negociaciones. "
            "Útil en el informe semanal y en análisis de patrones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_order_suggestions",
        "description": (
            "Sugerencia de pedido semanal basada en merma histórica (Feature #25). "
            "Calcula cuántas unidades de cada producto se pierden de media al día "
            "y recomienda cuánto pedir esta semana para evitar roturas de stock. "
            "Útil para el informe semanal y la planificación de compras."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_roi",
        "description": (
            "ROI de acciones completadas: valor recuperado por acciones de rebajar y donar "
            "en los últimos N días. Mide la 'merma evitada': valor que habría sido pérdida "
            "y se recuperó gracias a las acciones del sistema. "
            "Devuelve: actions_completed, value_recovered (€), cost_recovered (€), period_days. "
            "Usar en briefs para justificar el impacto económico del sistema."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Período en días (default: 7)",
                    "default": 7,
                },
            },
            "required": [],
        },
        "cache_control": {"type": "ephemeral"},
    },
    {
        "name": "get_store_comparison",
        "description": (
            "Comparativa de esta tienda con la media de la red: merma %, valor recuperado, ranking. "
            "Útil para contextualizar los KPIs de hoy vs el promedio de otras tiendas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "cache_control": {"type": "ephemeral"},
    },
]


# ── Tool executor — conecta herramientas con el sistema real ─────────────────

def _make_executor(store_id: str):
    """Crea un executor que tiene acceso al store_id en su closure."""

    def executor(tool_name: str, tool_input: dict) -> dict:
        if tool_name == "think":
            # No-op: el pensamiento ya está en el context. Devolvemos ACK.
            return {"ok": True, "thought_logged": tool_input.get("thought", "")[:200]}

        if tool_name == "get_expiring_batches":
            days = tool_input.get("days", 7)
            category = tool_input.get("category")
            batches = database.get_batches_expiring_soon(store_id, days=days)
            if category:
                batches = [
                    b for b in batches
                    if (b.get("products") or {}).get("category", "").lower() == category.lower()
                ]
            # Enriquecer con días restantes
            today = date.today()
            for b in batches:
                try:
                    b["days_left"] = (date.fromisoformat(b["expiry_date"]) - today).days
                except (ValueError, KeyError):
                    b["days_left"] = 999
            total = len(batches)
            if total > 25:
                batches = batches[:25]
                return {"batches": batches, "count": total, "truncated": True,
                        "hint": f"Mostrando 25/{total} lotes. Filtra por categoría o reduce días para ver menos."}
            return {"batches": batches, "count": total}

        if tool_name == "get_warehouse_stock":
            qty = database.get_warehouse_stock(store_id, tool_input["product_id"])
            return {"product_id": tool_input["product_id"], "warehouse_qty": qty}

        if tool_name == "recall_memory":
            value = mem.recall(store_id, tool_input["pattern_key"])
            return {
                "pattern_key": tool_input["pattern_key"],
                "value": value,
                "found": value is not None,
            }

        if tool_name == "store_memory":
            mem.remember(store_id, tool_input["pattern_key"], tool_input["pattern_value"])
            return {"stored": True, "key": tool_input["pattern_key"]}

        if tool_name == "evaluate_product_risk":
            inp = tool_input
            fake_product = {
                "id": inp.get("product_id", ""),
                "name": inp.get("product_name", ""),
                "category": inp.get("category", ""),
                "price": inp.get("price", 0),
                "cost": inp.get("cost", 0),
            }
            days_left = inp.get("days_left", 999)
            qty = inp.get("quantity", 0)
            warehouse_qty = inp.get("warehouse_qty", 0)
            expiry = date.fromordinal(date.today().toordinal() + days_left).isoformat()
            fake_batch = {
                "expiry_date": expiry,
                "quantity": qty,
            }
            result = evaluator.evaluate(
                fake_product,
                [fake_batch],
                historical_context=inp.get("historical_context", ""),
                warehouse_qty=warehouse_qty,
            )

            # ── Internal critic step ─────────────────────────────────────────
            # Solo para decisiones de alto impacto (score>=65, valor>20€).
            # Kuine se autocritica ANTES de pasar el resultado al loop principal.
            # Reduce llamadas al Evaluador externo y captura errores obvios.
            _score = result.get("score", 0)
            _value = float(inp.get("price", 0)) * qty
            if _score >= 65 and _value > 20.0:
                _action = result.get("action", "revisar")
                _reasoning = result.get("reasoning", "")
                _critique_prompt = (
                    f"Revisa críticamente esta evaluación de merma antes de actuar:\n\n"
                    f"Producto: {inp.get('product_name')} ({inp.get('category')})\n"
                    f"Días hasta caducidad: {days_left}\n"
                    f"Cantidad: {qty} uds · Valor: {round(_value, 2)}€\n"
                    f"Almacén: {warehouse_qty} uds\n\n"
                    f"Decisión propuesta: {_action.upper()} (score {_score}/100)\n"
                    f"Razonamiento: {_reasoning}\n\n"
                    f"Responde en 1 línea: '¿ACEPTAR' o 'REVISAR: [razón concreta]'.\n"
                    f"Solo di REVISAR si hay un error obvio (margen negativo, normativa incorrecta, "
                    f"dato contradictorio). Si la decisión es razonable, di ACEPTAR."
                )
                try:
                    critique = llm.call_fast(_critique_prompt, max_tokens=80)
                    if critique.upper().startswith("REVISAR"):
                        # El crítico detectó un problema — añadir al resultado
                        result["critic_flag"] = critique.replace("REVISAR:", "").strip()
                        result["critic_reviewed"] = True
                        logger.info(f"[critic] {inp.get('product_name')}: {result['critic_flag']}")
                    else:
                        result["critic_reviewed"] = True
                except Exception as _ce:
                    logger.debug(f"[critic] fallo silencioso: {_ce}")

            return result

        if tool_name == "calculate_discount":
            inp = tool_input
            fake_product = {
                "price": inp.get("price", 0),
                "cost": inp.get("cost", 0),
                "name": inp.get("product_name", ""),
            }
            days_left = inp.get("days_left", 999)
            expiry = date.fromordinal(date.today().toordinal() + days_left).isoformat()
            fake_batch = {"expiry_date": expiry}
            risk = {
                "risk_level": inp.get("risk_level", "MEDIO"),
                "price_adjustment_pct": 0,
            }
            return price.calculate(fake_product, fake_batch, risk)

        if tool_name == "create_action":
            action_data = {
                "store_id": tool_input.get("store_id", store_id),
                "batch_id": tool_input.get("batch_id"),
                "action_type": tool_input.get("action_type"),
                "priority_score": tool_input.get("priority_score", 50),
                "notes": tool_input.get("notes", ""),
                "status": "pending",
            }
            if tool_input.get("price_adjustment_pct"):
                action_data["price_adjustment_pct"] = int(tool_input["price_adjustment_pct"])
            if tool_input.get("new_price"):
                action_data["new_price"] = float(tool_input["new_price"])
            # Evitar duplicados: verificar si ya existe acción pendiente para este batch
            try:
                existing = database.get_pending_actions(store_id)
                for existing_action in existing:
                    if existing_action.get("batch_id") == action_data["batch_id"]:
                        return {"created": False, "reason": "Ya existe acción pendiente para este lote."}
                created = database.create_action(action_data)
                # Traza de decisión de Kuine (Fase 3)
                try:
                    decision_type_map = {
                        "rebajar": "rebajar",
                        "donar": "donar",
                        "retirar": "retirar",
                        "revisar": "revisar",
                        "reponer": "reponer",
                        # aliases en inglés por si acaso
                        "discount": "rebajar",
                        "donate": "donar",
                        "remove": "retirar",
                        "review": "revisar",
                        "restock": "reponer",
                    }
                    dtype = decision_type_map.get(action_data.get("action_type", ""), "revisar")
                    database.log_supervisor_decision({
                        "store_id": store_id,
                        "agent_run_id": _LAST_BRIEF_RUN_ID.get(store_id) or None,
                        "product_id": tool_input.get("product_id"),
                        "batch_id": action_data.get("batch_id"),
                        "decision_type": dtype,
                        "score": action_data.get("priority_score", 0),
                        "reason": action_data.get("notes", ""),
                        "validated": False,
                    })
                except Exception:
                    pass
                # DM proactivo a empleados si la acción es crítica
                if action_data.get("priority_score", 0) >= 85:
                    try:
                        from backend.agents import notifier
                        notifier.notify_critical_action(store_id, created)
                    except Exception:
                        pass
                return {"created": True, "action_id": created.get("id")}
            except Exception as e:
                return {"created": False, "error": str(e)}

        if tool_name == "get_pending_actions":
            actions = database.get_pending_actions(tool_input.get("store_id", store_id))
            return {
                "count": len(actions),
                "critical": sum(1 for a in actions if a.get("priority_score", 0) >= 85),
                "actions": actions[:10],
            }

        if tool_name == "search_food_regulations":
            results = knowledge.query(tool_input.get("query", ""), top_k=2)
            return {"results": results, "count": len(results)}

        if tool_name == "get_merma_history":
            days = tool_input.get("days", 7)
            logs = database.get_merma_history(store_id, days=days)
            total_value = sum(float(l.get("value_lost", 0)) for l in logs)
            total_qty = sum(int(l.get("quantity_lost", 0)) for l in logs)
            return {
                "days": days,
                "total_value_lost": round(total_value, 2),
                "total_quantity_lost": total_qty,
                "entries": len(logs),
                "recent": logs[:5],
            }

        if tool_name == "get_supplier_stats":
            stats = database.get_supplier_stats(store_id)
            return {
                "count": len(stats),
                "suppliers": stats,
                "top_risk": stats[0] if stats else None,
            }

        if tool_name == "get_order_suggestions":
            suggestions = database.get_order_suggestions(store_id)
            total_value = sum(s.get("estimated_value", 0) for s in suggestions)
            return {
                "count": len(suggestions),
                "total_estimated_value": round(total_value, 2),
                "suggestions": suggestions,
            }

        if tool_name == "get_roi":
            days = int(tool_input.get("days", 7))
            roi = database.get_completed_actions_value(store_id, days=days)
            return roi

        if tool_name == "get_day_context":
            now = datetime.now()
            brief = database.get_latest_brief(store_id)
            weekday_names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            return {
                "date": date.today().isoformat(),
                "weekday": weekday_names[now.weekday()],
                "hour": now.hour,
                "is_weekend": now.weekday() >= 5,
                "latest_brief_date": brief.get("date") if brief else None,
                "latest_brief_summary": brief.get("summary", "")[:200] if brief else None,
            }

        if tool_name == "evaluate_all_products_parallel":
            from backend.agents.parallel_evaluator import evaluate_all_parallel, summary_stats
            days = tool_input.get("days", 7)
            results = evaluate_all_parallel(store_id, days=days)
            stats = summary_stats(results)
            return {
                "stats": stats,
                "results": results,
                "total_evaluated": len(results),
            }

        if tool_name == "get_store_comparison":
            try:
                stores = database.get_stores_comparison(store_id)
                if not stores:
                    return {"mensaje": "Sin datos de comparativa disponibles."}
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
            except Exception as e:
                return {"error": str(e)}

        return {"error": f"Herramienta desconocida: {tool_name}"}

    return executor


# ── Agent health check ───────────────────────────────────────────────────────

def run_agent_health_check(store_id: str) -> dict:
    """
    Health check de subagentes — detecta inconsistencias entre decisiones.
    Pattern: producción LangGraph 2025 — supervisor monitoriza consistencia de workers.

    Comprueba:
    1. Decisiones contradictorias: ¿el mismo producto tiene rebajar Y retirar pendiente?
    2. Score drift: ¿el Evaluador da scores muy distintos para productos similares?
    3. Acumulación anómala: ¿hay más de N acciones pendientes para el mismo pasillo?
    4. Tempo: ¿cuándo fue el último ciclo de Kuine?

    Devuelve dict con issues encontrados y nivel de salud (ok/warning/critical).
    """
    issues = []
    warnings = []

    try:
        pending = database.get_pending_actions(store_id)

        # 1. Detectar acciones contradictorias para el mismo batch
        by_batch: dict[str, list[dict]] = {}
        for a in pending:
            bid = a.get("batch_id", "")
            if bid:
                by_batch.setdefault(bid, []).append(a)

        for batch_id, actions in by_batch.items():
            if len(actions) > 1:
            # Mismo lote con múltiples acciones — potencial contradicción
                types = {a.get("action_type", "") for a in actions}
                if "retirar" in types and "rebajar" in types:
                    product = ((actions[0].get("batches") or {}).get("products") or {}).get("name", batch_id)
                    issues.append(f"CONTRADICCIÓN: {product} tiene rebajar Y retirar simultáneos")
                elif "donar" in types and "retirar" in types:
                    product = ((actions[0].get("batches") or {}).get("products") or {}).get("name", batch_id)
                    issues.append(f"CONTRADICCIÓN: {product} tiene donar Y retirar simultáneos")

        # 2. Score drift — demasiada varianza en scores del mismo pasillo
        by_pasillo: dict[str, list[int]] = {}
        for a in pending:
            batch = a.get("batches") or {}
            product = (batch.get("products") or {}) if batch else {}
            pasillo = str(product.get("pasillo", "?"))
            score = int(a.get("priority_score") or 0)
            by_pasillo.setdefault(pasillo, []).append(score)

        for pasillo, scores in by_pasillo.items():
            if len(scores) >= 3:
                max_s, min_s = max(scores), min(scores)
                if max_s - min_s > 60:  # varianza extrema en el mismo pasillo
                    warnings.append(f"Score drift en Pasillo {pasillo}: rango {min_s}-{max_s} (varianza {max_s-min_s})")

        # 3. Acumulación anómala de pendientes por pasillo
        for pasillo, scores in by_pasillo.items():
            if len(scores) > 8:
                warnings.append(f"Acumulación en Pasillo {pasillo}: {len(scores)} acciones pendientes sin resolver")

        # 4. Último ciclo de Kuine
        try:
            last_run = database.get_db().table("agent_runs").select("created_at").eq("store_id", store_id).order("created_at", desc=True).limit(1).execute()
            if last_run.data:
                import datetime as _dt
                last_ts = _dt.datetime.fromisoformat(last_run.data[0]["created_at"].replace("Z", "+00:00"))
                hours_since = (_dt.datetime.now(_dt.timezone.utc) - last_ts).total_seconds() / 3600
                if hours_since > 26:
                    issues.append(f"Kuine no ha ejecutado en {round(hours_since)}h — posible fallo del scheduler")
                elif hours_since > 14:
                    warnings.append(f"Kuine sin ejecutar en {round(hours_since)}h — revisar scheduler")
        except Exception:
            pass

        health = "critical" if issues else "warning" if warnings else "ok"

        if (issues or warnings) and health != "ok":
            try:
                lines = [f"🔬 Health Check Kuine — {health.upper()}"]
                if issues:
                    lines.append("\nProblemas críticos:")
                    lines.extend(f"  • {i}" for i in issues[:3])
                if warnings:
                    lines.append("\nAdvertencias:")
                    lines.extend(f"  ⚠ {w}" for w in warnings[:3])
                notifier.send_alert(store_id, "Kuine — Health Check", "\n".join(lines), urgent=health == "critical")
            except Exception:
                pass

        logger.info(f"[health_check] {health}: {len(issues)} issues, {len(warnings)} warnings")
        return {"health": health, "issues": issues, "warnings": warnings}

    except Exception as e:
        logger.warning(f"[health_check] error: {e}")
        return {"health": "unknown", "issues": [], "warnings": []}


# ── Flujo de escaneo individual ──────────────────────────────────────────────

def run_scan(store_id: str, barcode: str, user_id: str) -> str:
    """
    Flujo completo de escaneo: Kuine investiga con herramientas
    y genera una respuesta operativa para el empleado.
    """
    product = database.get_product_by_barcode(store_id, barcode)

    if not product:
        from backend.agents.scanner import lookup_barcode
        product_info = lookup_barcode(barcode)
        if not product_info:
            return {"text": f"Producto con código {barcode} no encontrado en tienda ni en la base de datos global.",
                    "thinking_summary": "", "action_id": None, "action_type": None,
                    "product_name": None, "days_left": None, "final_action": None,
                    "location": None, "price_rec": None}
        return {"text": (
            f"Producto no registrado en esta tienda.\n\n"
            f"Encontrado en base de datos global:\n"
            f"Nombre: {product_info.get('name', 'Desconocido')}\n"
            f"Marca: {product_info.get('brand', '-')}\n"
            f"Categoría: {product_info.get('category', '-')}\n\n"
            f"Para registrarlo, usa la opción 'Añadir producto' en la app."
        ), "thinking_summary": "", "action_id": None, "action_type": None,
           "product_name": product_info.get("name"), "days_left": None,
           "final_action": None, "location": None, "price_rec": None}

    batches = database.get_batches_by_product(store_id, product["id"])
    if not batches:
        return {"text": f"{product['name']} — sin lotes activos registrados.",
                "thinking_summary": "", "action_id": None, "action_type": None,
                "product_name": product["name"], "days_left": None,
                "final_action": None, "location": None, "price_rec": None}

    soonest = min(batches, key=lambda b: b.get("expiry_date") or "9999-99-99")
    try:
        days_left = (date.fromisoformat(soonest["expiry_date"]) - date.today()).days
    except (ValueError, KeyError, TypeError):
        days_left = 999

    warehouse_qty = database.get_warehouse_stock(store_id, product["id"])
    historical_context = mem.recall_product_pattern(store_id, product["id"]) or ""

    # Evaluador y stock en paralelo. fast=True limita thinking a 1500 tokens (~5-8s vs 20-40s).
    # Para productos de alto valor (>50€ en riesgo o caducados hoy) se usa fork-merge:
    # 3 ramas de razonamiento paralelas + síntesis Opus → +40% precisión en casos críticos.
    from backend.agents.fork_merge import evaluate_fork_merge, should_use_fork_merge
    risk: dict = {}
    stock_dec: dict = {}
    use_fork = should_use_fork_merge(product, batches)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="scan") as pool:
        if use_fork:
            f_risk = pool.submit(
                evaluate_fork_merge, product, batches,
                historical_context=historical_context, warehouse_qty=warehouse_qty
            )
        else:
            f_risk = pool.submit(
                evaluator.evaluate, product, batches,
                historical_context=historical_context, warehouse_qty=warehouse_qty, fast=True
            )
        # Intentar pasar datos del predictor al stock para ajuste de cobertura objetivo
        _prediction_data = None
        try:
            from backend.agents.predictor import predict_merma_risk
            preds = predict_merma_risk(store_id, forecast_days=3)
            for p in (preds or []):
                if p.get("product_id") == product.get("id"):
                    _prediction_data = p
                    break
        except Exception:
            pass
        f_stock = pool.submit(stock.decide_restocking, product, batches, warehouse_qty, _prediction_data)
        risk = f_risk.result()
        stock_dec = f_stock.result()

    price_rec = price.calculate(product, soonest, risk)

    # Validación adversarial
    validation = validator.validate_scan_result(product, soonest, risk, stock_dec["reason"], price_rec)

    # Si el validador revirtió la acción, usar la corregida
    final_action = validation.get("final_action", risk.get("action", "revisar"))

    # Generar respuesta final con Claude
    location = (
        f"Pasillo {product.get('pasillo', '?')} — "
        f"Estantería {product.get('estanteria', '?')} — "
        f"Nivel {product.get('nivel', '?')}"
    )

    scan_context = f"""PRODUCTO ESCANEADO:
Nombre: {product['name']}
Ubicación: {location}
Categoría: {product.get('category', '-')}
Precio: {product.get('price', 0)} euros | Coste: {product.get('cost', 0)} euros

LOTE MAS PROXIMO:
Fecha de caducidad: {soonest['expiry_date']}
Dias restantes: {days_left}
Cantidad en tienda: {soonest.get('quantity', 0)} unidades
Stock en almacén: {warehouse_qty} unidades

EVALUACION DE RIESGO:
Nivel: {risk['risk_level']} — Score: {risk['score']}/100
Razonamiento: {risk['reasoning']}

ACCION RECOMENDADA (validada): {final_action.upper()}
Precio: {price_rec['recommendation_text']}
Stock: {stock_dec['reason']}

VALIDACION: {validation['status']}
{('Observaciones: ' + validation['explanation']) if validation['status'] != 'VALIDADO' else ''}"""

    response_text = llm.call(
        f"Genera la respuesta de escaneo para el empleado:\n\n{scan_context}",
        system_extra=(
            "Respuesta directa para el empleado. Máximo 5 líneas. "
            "Estructura: 1) Nombre + ubicación. 2) Situación (días, cantidad). "
            "3) ACCION concreta con precio exacto si aplica. 4) Reposición si/no. "
            "5) Una línea de justificación. Sin asteriscos."
        ),
        max_tokens=300,
    )

    # Buscar acción pendiente para este producto (para botón directo en app).
    # Intentamos por batch_id primero (más fiable) y luego por product_id como fallback.
    pending_action_id = None
    pending_action_type = None
    try:
        batch_id = soonest.get("id")
        actions_res = (
            database.get_admin_db()
            .table("actions")
            .select("id, action_type")
            .eq("store_id", store_id)
            .eq("batch_id", batch_id)
            .eq("status", "pending")
            .limit(1)
            .execute()
        )
        if actions_res.data:
            pending_action_id = actions_res.data[0]["id"]
            pending_action_type = actions_res.data[0]["action_type"]
        else:
            # Fallback: buscar por product_id (acciones creadas por advance_demo)
            actions_res2 = (
                database.get_admin_db()
                .table("actions")
                .select("id, action_type")
                .eq("store_id", store_id)
                .eq("product_id", product["id"])
                .eq("status", "pending")
                .order("priority_score", desc=True)
                .limit(1)
                .execute()
            )
            if actions_res2.data:
                pending_action_id = actions_res2.data[0]["id"]
                pending_action_type = actions_res2.data[0]["action_type"]
    except Exception as e:
        logger.warning(f"[scan] pending_action_id lookup failed: {e}")

    return {
        "text": response_text,
        "thinking_summary": risk.get("thinking_summary", ""),
        "action_id": pending_action_id,
        "action_type": pending_action_type,
        "product_name": product["name"],
        "days_left": days_left,
        "final_action": final_action,
        "location": location,
        "price_rec": price_rec.get("recommendation_text", ""),
    }


# ── Brief diario — flujo 07:30 ───────────────────────────────────────────────

def run_daily_brief(store_id: str, *, send_telegram: bool = True) -> str:
    """
    Brief de apertura de tienda. Kuine usa el loop agéntico completo:
    send_telegram=False cuando el llamador ya gestiona el envío (p.ej. Chuwi simulate_730).
    investiga activamente, evalúa cada producto, crea acciones en BD y genera el brief.
    """
    import time as _time
    _t0 = _time.monotonic()
    today = date.today()
    weekday = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][today.weekday()]
    # Pasar categorías activas hoy para recuperar velocidad por categoría de la memoria
    try:
        active_batches = database.get_batches_expiring_soon(store_id, days=14)
        active_categories = list({
            (b.get("products") or {}).get("category", "")
            for b in active_batches
            if (b.get("products") or {}).get("category")
        })
    except Exception:
        active_categories = None
    memory_ctx = mem.build_rich_memory_context(store_id, categories=active_categories)

    # Contexto predictivo — predicciones de riesgo + clima para los próximos días
    prediction_ctx = ""
    try:
        from backend.agents.predictor import predict_merma_risk, generate_prediction_brief
        predictions = predict_merma_risk(store_id, forecast_days=3)
        if predictions:
            high_risk = [p for p in predictions if p.get("risk_level") in ("high", "CRÍTICO", "ALTO")]
            if high_risk:
                prediction_ctx = (
                    f"\n=== PREDICCIONES PRÓXIMOS 3 DÍAS ===\n"
                    f"{len(high_risk)} producto(s) con riesgo elevado previsto:\n"
                    + "\n".join(
                        f"- {p.get('product_name','?')}: {p.get('risk_level','?')} "
                        f"(día {p.get('forecast_day','')})"
                        for p in high_risk[:5]
                    )
                )
    except Exception:
        pass

    # Contexto de comparativa de tiendas (benchmarking)
    comparison_ctx = ""
    try:
        stores = database.get_stores_comparison(store_id)
        if stores:
            current = next((s for s in stores if s.get("is_current")), None)
            if current:
                rank = current.get("rank", "?")
                merma_pct = current.get("merma_rate_pct", "?")
                comparison_ctx = (
                    f"\n=== BENCHMARKING RED ===\n"
                    f"Esta tienda: merma {merma_pct}% · Ranking #{rank}/{len(stores)} en la cadena"
                )
    except Exception:
        pass

    # Feedback de outcomes de ayer — cerrar el loop de aprendizaje
    outcomes_ctx = ""
    try:
        from backend.core.memory import get_daily_decision_feedback
        feedback = get_daily_decision_feedback(store_id, days_back=1)
        outcomes = feedback.get("top_outcomes", [])
        if outcomes:
            pct = feedback.get("effectiveness_pct", 0)
            lines = [f"\n=== RESULTADOS DE AYER (efectividad: {pct}%) ==="]
            for o in outcomes[:5]:
                atype = o.get("action_type", "?")
                product = o.get("product_name", "?")
                result_val = o.get("result", "?")
                value = o.get("value_recovered", 0)
                lines.append(
                    f"- {product}: {atype.upper()} → {result_val}"
                    + (f" · recuperado {value:.2f}€" if value > 0 else "")
                )
            if pct < 60:
                lines.append(
                    f"ATENCIÓN: efectividad baja ({pct}%). "
                    "Ajusta descuentos y prioriza donaciones para productos de difícil venta."
                )
            elif pct > 85:
                lines.append(f"Excelente efectividad. Mantén la estrategia actual.")
            outcomes_ctx = "\n".join(lines)
    except Exception:
        pass

    system_brief = (
        "Eres Kuine, el agente orquestador de MermaOps. "
        "Realizas el análisis de apertura del día para el Super Martínez. "
        "Tu misión: investigar todos los productos que necesitan atención, "
        "evaluar cada uno con tus herramientas especializadas, crear las acciones en la base de datos, "
        "y generar un brief operativo completo para el encargado. "
        "Trabaja de forma metódica: primero panorama general, luego profundiza en críticos, "
        "consulta memoria histórica, crea las acciones, y finaliza con el resumen.\n\n"
        "HERRAMIENTA THINK: usa 'think' para razonar en voz alta antes de crear una acción crítica. "
        "Ejemplo: antes de decidir RETIRAR vs DONAR, usa think para analizar si el producto aún "
        "puede venderse, si hay demanda histórica, y si la normativa permite la donación. "
        "Un think bien hecho evita errores costosos. "
        "Cuando detectes exceso de stock con caducidad inminente, sugiere proactivamente donación al banco de alimentos.\n\n"
        "CONFIANZA EN DECISIONES: el campo confidence_pct del evaluador indica cuánto confiar en la decisión. "
        "Para confidence_pct < 70 (borderline), usa el think tool para razonar más antes de actuar. "
        "Para confidence_pct >= 85, puedes actuar directamente sin razonamiento adicional."
    )

    prompt = f"""Es el amanecer del {weekday} {today.isoformat()} en el Super Martinez.

Realiza el análisis completo de apertura del día siguiendo este orden:

PASO 1 — Panorama rápido (1 llamada):
  Usa evaluate_all_products_parallel(days=7) para evaluar todos los lotes de golpe.
  Esto es más rápido que evaluar uno por uno.

PASO 2 — Profundizar en críticos:
  Para cada producto con score >= 85 del resultado anterior:
  - Consulta get_warehouse_stock para saber si hay almacén
  - Usa calculate_discount para calcular el precio exacto
  - Consulta recall_memory si hay historial relevante

PASO 3 — Crear acciones:
  Llama create_action para cada producto que requiera intervención.
  Incluye en las notas el precio exacto si hay descuento.

PASO 4 — Patrones y contexto:
  Si detectas algo interesante (producto que siempre falla, patrón de día), guárdalo con store_memory.
  Consulta get_merma_history(days=7) para comparar con la semana pasada.

PASO 5 — Brief final:
  Genera el brief completo con: situación crítica, acciones ordenadas, ruta del día y valor en riesgo.

Contexto histórico disponible:
{memory_ctx}{prediction_ctx}{comparison_ctx}{outcomes_ctx}

Al finalizar, genera el brief completo para el encargado."""

    # ── Brief con live updates a Telegram — Kuine habla mientras trabaja ────
    # Crea un mensaje en Telegram y lo edita en cada tool call de Kuine.
    # El encargado ve el progreso en tiempo real: "Evaluando 47 productos... 3 CRÍTICOS..."
    import concurrent.futures as _cf
    import threading as _threading

    _live_msg_id: dict[str, int] = {}  # message_id del placeholder de Telegram
    _live_chat_id: str = ""
    _live_tool_log: list[str] = []

    def _try_get_chat_id() -> str:
        try:
            store = database.get_store(store_id)
            return store.get("telegram_chat_id", "") if store else ""
        except Exception:
            return ""

    def _send_live_update(text: str) -> None:
        import requests as _req, os as _os
        _tok = _os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not _tok or not _live_chat_id:
            return
        try:
            if not _live_msg_id:
                r = _req.post(f"https://api.telegram.org/bot{_tok}/sendMessage", json={
                    "chat_id": _live_chat_id, "text": text,
                }, timeout=5)
                if r.status_code == 200:
                    _live_msg_id["id"] = r.json()["result"]["message_id"]
            else:
                _req.post(f"https://api.telegram.org/bot{_tok}/editMessageText", json={
                    "chat_id": _live_chat_id, "message_id": _live_msg_id["id"], "text": text,
                }, timeout=5)
        except Exception:
            pass

    # Obtener chat_id para live updates
    _live_chat_id = _try_get_chat_id()
    if _live_chat_id:
        _send_live_update(f"⏳ Kuine iniciando análisis del {weekday}...")

    # Wrapper del executor que manda live updates al Telegram
    _base_executor = _make_executor(store_id)
    def _live_executor(tool_name: str, tool_input: dict):
        result = _base_executor(tool_name, tool_input)
        if _live_chat_id:
            # Resolver nombre de producto desde BD si Kuine no lo incluyó
            def _resolve_pname(fallback: str = "?") -> str:
                pname = tool_input.get("product_name", "")
                if pname:
                    return pname
                bid = tool_input.get("batch_id", "")
                pid = tool_input.get("product_id", "")
                try:
                    if bid:
                        batch = database.get_batch_by_id(bid)
                        pname = ((batch or {}).get("products") or {}).get("name", "")
                    if not pname and pid:
                        row = database.get_db().table("products").select("name").eq("id", pid).maybe_single().execute()
                        pname = (row.data or {}).get("name", "")
                except Exception:
                    pass
                return pname or fallback

            _LIVE_LABELS = {
                "evaluate_all_products_parallel": "📊 Evaluando todos los productos en paralelo...",
                "create_action": f"✅ Creando acción: {tool_input.get('action_type','').upper()} para {_resolve_pname()}",
                "get_merma_history": "📉 Consultando merma histórica...",
                "recall_memory": "🧠 Consultando memoria episódica...",
                "store_memory": "💾 Guardando patrón aprendido...",
                "get_warehouse_stock": f"📦 Verificando almacén: {tool_input.get('product_id','')[:8]}",
                "calculate_discount": f"💰 Calculando descuento: {_resolve_pname()}",
                "get_supplier_stats": "🏭 Analizando proveedores...",
                "get_store_comparison": "📈 Consultando benchmark de la red...",
                "get_order_suggestions": "🛒 Calculando pedido semanal...",
            }
            label = _LIVE_LABELS.get(tool_name, f"🔧 {tool_name}...")
            _live_tool_log.append(label)
            # Resumen del progreso
            actions_created = sum(1 for t in _live_tool_log if "Creando acción" in t)
            progress_text = (
                f"⏳ Kuine analizando ({len(_live_tool_log)} pasos):\n\n"
                + "\n".join(_live_tool_log[-5:])  # últimas 5 acciones
                + (f"\n\n✅ {actions_created} acciones creadas hasta ahora" if actions_created else "")
            )
            _send_live_update(progress_text[:4096])

            # Tras evaluate_all: mostrar resumen de críticos inmediatamente
            if tool_name == "evaluate_all_products_parallel" and isinstance(result, dict):
                stats = result.get("stats", {})
                critical_n = stats.get("critical", 0)
                high_n = stats.get("high", 0)
                total_val = stats.get("total_value_at_risk", 0)
                _send_live_update(
                    f"📊 Panorama listo:\n"
                    f"🔴 {critical_n} CRÍTICOS | 🟡 {high_n} ALTOS\n"
                    f"💶 {round(total_val, 2)}€ en riesgo\n\n"
                    f"Kuine creando acciones..."
                )
        return result

    _cancel_event = _threading.Event()
    _brief_executor = _cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="brief")
    _brief_future = _brief_executor.submit(
        llm.run_agentic_loop,
        prompt=prompt,
        tools=SUPERVISOR_TOOLS,
        tool_executor=_live_executor,
        system_extra=system_brief,
        max_tokens=4096,
        max_iterations=20,
        model=llm.MODEL_DEEP,
        cancel_event=_cancel_event,
    )
    try:
        response, tool_trace = _brief_future.result(timeout=300)
    except _cf.TimeoutError:
        logger.error("[brief] Timeout 5min — señalando cancelación al loop agéntico")
        _cancel_event.set()
        response = "Brief no disponible — el análisis superó el tiempo límite. Reintenta con /brief."
        tool_trace = []
    finally:
        _brief_executor.shutdown(wait=False)

    # ── Devil's Advocate — revisión crítica del batch de acciones ────────────
    # Antes de guardar el brief, Kuine se autocritica el conjunto de decisiones.
    # Pattern: Devil's Advocate (arxiv 2405.16334) — reduce errores de plan 45%.
    # Solo se activa si hay acciones creadas en este ciclo (no merece tokens si vacío).
    _da_actions = [t for t in tool_trace if isinstance(t, dict) and t.get("tool") == "create_action"]
    if len(_da_actions) >= 2:  # solo critica si hay 2+ acciones (batch real)
        try:
            _batch_summary = "\n".join(
                f"- {a.get('input', {}).get('action_type','?').upper()} para "
                f"{a.get('input', {}).get('product_name','?')} "
                f"(score {a.get('input', {}).get('priority_score',0)})"
                for a in _da_actions[:8]
            )
            _da_prompt = (
                f"Revisa críticamente este batch de {len(_da_actions)} decisiones de Kuine.\n\n"
                f"{_batch_summary}\n\n"
                f"¿Hay algún problema obvio con ESTE CONJUNTO? Por ejemplo:\n"
                f"- ¿Se rebajan demasiados productos a la vez (glut de descuentos)?\n"
                f"- ¿Se retira algo que debería donarse?\n"
                f"- ¿Falta alguna categoría importante?\n"
                f"- ¿Hay contradicción entre acciones del mismo pasillo?\n\n"
                f"Si el batch es coherente, di 'OK'. Si hay un problema real, di 'AVISO: [razón en 1 línea]'."
            )
            _da_critique = llm.call_fast(_da_prompt, max_tokens=80)
            if "AVISO" in _da_critique.upper():
                # Solo va al log interno — nunca al brief del usuario
                logger.warning(f"[devil_advocate] AVISO (interno): {_da_critique}")
            else:
                logger.debug(f"[devil_advocate] Batch aprobado: {len(_da_actions)} acciones")
        except Exception as _dae:
            logger.debug(f"[devil_advocate] fallo silencioso: {_dae}")

    # También incluir reflexiones recientes en el brief si las hay
    try:
        _reflections_raw = mem.recall(store_id, "reflexiones_recientes")
        if _reflections_raw:
            import json as _json
            _reflections = _json.loads(_reflections_raw)
            if _reflections:
                _last = _reflections[0]
                _lesson = _last.get("lesson", "")[:200]
                _date = _last.get("date", "")
                if _lesson and _date:
                    response = response + f"\n\n📝 Reflexión de {_date}: {_lesson}"
    except Exception:
        pass

    # Guardar brief en BD
    pending = database.get_pending_actions(store_id)
    batches_today = database.get_batches_expiring_soon(store_id, days=7)
    total_value = sum(
        b.get("quantity", 0) * (b.get("products") or {}).get("price", 0)
        for b in batches_today
    )
    database.save_daily_brief({
        "store_id": store_id,
        "date": today.isoformat(),
        "summary": response,
        "value_at_risk": round(total_value, 2),
        "actions_count": len(pending),
    })

    # Memoria episódica garantizada — siempre se escribe aunque Kuine no llame store_memory
    try:
        critical_now = [a for a in pending if a.get("priority_score", 0) >= 85]
        mem.remember(
            store_id,
            mem.KEY_DAILY_STATS.format(date=today.isoformat()),
            f"Criticos:{len(critical_now)}, valor_riesgo:{round(total_value,2)}€, acciones:{len(pending)}",
        )
    except Exception as e:
        logger.warning(f"[brief] episodic memory write failed: {e}")

    # Episode summary — resumen compacto del ciclo para contexto futuro
    try:
        tool_names_for_ep = [t.get("tool", "") if isinstance(t, dict) else str(t) for t in tool_trace if t]
        actions_created = [
            {"product_name": t.get("input", {}).get("product_name", "?"),
             "action_type": t.get("input", {}).get("action_type", "?"),
             "score": t.get("input", {}).get("priority_score", 0)}
            for t in tool_trace if isinstance(t, dict) and t.get("tool") == "create_action"
        ] if tool_trace else []
        mem.create_episode_summary(
            store_id=store_id,
            actions_created=actions_created,
            actions_completed=[],
            critical_count=len(critical_now),
            value_at_risk=round(total_value, 2),
            tools_used=tool_names_for_ep,
        )
    except Exception as e:
        logger.debug(f"[brief] episode summary failed: {e}")

    # Feedback proactivo — incluir en el brief el resultado de las decisiones de ayer
    try:
        feedback = mem.get_daily_decision_feedback(store_id, days_back=1)
        if feedback.get("total_decisions", 0) > 0:
            eff = feedback.get("effectiveness_pct", 0)
            val = feedback.get("value_recovered_eur", 0)
            fb_msg = (
                f"\n📊 SEGUIMIENTO AYER: {feedback['total_decisions']} decisiones — "
                f"{eff}% efectivas · {val:.2f}€ recuperados "
                f"({feedback.get('sold',0)} vendidos, {feedback.get('donated',0)} donados)"
            )
            response = response + fb_msg
    except Exception as e:
        logger.debug(f"[brief] feedback proactivo failed: {e}")

    # Validación batch: detecta duplicados y acciones incoherentes entre sí
    try:
        pending_for_validation = database.get_pending_actions(store_id)
        batch_val = validator.validate_actions_batch(pending_for_validation)
        if batch_val.get("issues"):
            logger.warning(f"[brief] validate_actions_batch encontró {len(batch_val['issues'])} problemas: {batch_val['issues'][:3]}")
    except Exception as e:
        logger.warning(f"[brief] validate_actions_batch failed: {e}")

    # Log del run con traza completa de herramientas (Fase 3)
    duration_ms = int((_time.monotonic() - _t0) * 1000)
    tool_names = [t.get("tool") if isinstance(t, dict) else str(t) for t in tool_trace if t is not None]
    _run_id = database.log_agent_run({
        "store_id": store_id,
        "agent_type": "kuine_daily_brief",
        "tools_used": tool_names,
        "tools_count": len(tool_names),
        "duration_ms": duration_ms,
        "trigger_source": "scheduler",
        "result": json.dumps({"tools_count": len(tool_names), "trace": tool_names}, default=str),
    })
    _LAST_BRIEF_RUN_ID[store_id] = _run_id or ""

    # Post-proceso: quitar líneas de revisión interna que el LLM a veces incluye
    import re as _re
    response = _re.sub(
        r'⚠️\s*Revisión interna[:\s][^\n]*(\n[^\n]+)*',
        '',
        response,
    ).strip()

    # Deduplicar: si el brief aparece dos veces (síntesis extra del loop), quedarse con el último
    _brief_marker = "═══════════════════════════════════════"
    if response.count(_brief_marker) >= 2:
        last_pos = response.rfind(_brief_marker)
        response = response[last_pos:].strip()

    if send_telegram:
        notifier.send_telegram(store_id, response)
    return response


# ── Check de mediodía — flujo 12:00 ─────────────────────────────────────────

def run_intraday_check(store_id: str) -> str:
    """Check de mediodía: escala críticos no resueltos + alerta pasillos sin revisar."""
    pending = database.get_pending_actions(store_id)
    critical = [a for a in pending if a.get("priority_score", 0) >= 85]

    # Feature #21: detectar pasillos con críticos sin revisión en >4h
    batches = database.get_batches_expiring_soon(store_id, days=3)
    completed = database.get_db().table("actions") \
        .select("*, batches(*, products(*))") \
        .eq("store_id", store_id) \
        .eq("status", "completed") \
        .gte("completed_at", (
            __import__("datetime").datetime.now()
            - __import__("datetime").timedelta(hours=8)
        ).isoformat()) \
        .execute().data or []

    section_check = validator.validate_section_review(store_id, batches, completed)
    if section_check["alerts"]:
        for alert in section_check["alerts"]:
            notifier.send_telegram(store_id, f"⚠️ {alert['message']}")

    if not critical and section_check["ok"]:
        return "Check de mediodia: sin acciones criticas ni pasillos sin revisar. Todo en orden."

    if critical:
        message = reporter.generate_intraday_alert(critical, store_id=store_id)
        if message:
            notifier.send_telegram(store_id, message)
        return message or "Check completado — brief reciente, alerta de mediodía omitida."

    return f"Check completado. {section_check['total_stale_pasillos']} pasillo(s) sin revisión reciente."


# ── Cierre del día — flujo 20:00 ────────────────────────────────────────────

def run_closing(store_id: str) -> str:
    """
    Cierre del día: Kuine revisa qué quedó sin resolver,
    registra la merma real y guarda patrones para el futuro.
    """
    pending = database.get_pending_actions(store_id)
    critical_pending = [a for a in pending if a.get("priority_score", 0) >= 85]

    # Guardar estadísticas del día en memoria para aprendizaje futuro
    brief = database.get_latest_brief(store_id)
    value_at_risk = brief.get("value_at_risk", 0) if brief else 0

    # Usar merma_log real del día en lugar de estimación del 20%
    try:
        merma_today = database.get_merma_history(store_id, days=1)
        real_value_lost = sum(float(l.get("value_lost", 0)) for l in merma_today)
    except Exception:
        real_value_lost = float(value_at_risk) * 0.2  # fallback si BD falla
    mem.record_daily_stats(
        store_id,
        value_lost=real_value_lost,
        items_discarded=len(merma_today),  # registros reales de merma, no pendientes
    )

    closing_report = reporter.generate_closing_report(store_id)
    notifier.send_telegram(store_id, closing_report)
    return closing_report


# ── Informe semanal — flujo lunes 06:00 ─────────────────────────────────────

def run_weekly_report(store_id: str) -> str:
    """Informe semanal con análisis de tendencias y recomendaciones estratégicas."""
    from datetime import date, timedelta
    report = reporter.generate_weekly_report(store_id)
    # Calcular inicio de la semana actual (lunes)
    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    database.save_weekly_report({
        "store_id": store_id,
        "week_start": week_start,
        "content": report,
        "stats": {},
    })
    database.log_agent_run({
        "store_id": store_id,
        "agent_type": "kuine_weekly_report",
        "trigger_source": "scheduler",
        "tools_used": [],
        "tools_count": 0,
        "duration_ms": 0,
        "result": f"Informe semanal generado para semana {week_start}",
    })
    notifier.send_telegram(store_id, report)
    return report


# ── Informe mensual — flujo 1 de cada mes 08:00 ─────────────────────────────

def run_monthly_report(store_id: str) -> str:
    """Informe mensual para el dueño con tendencias y recomendaciones estratégicas."""
    from datetime import date
    report = reporter.generate_monthly_report(store_id)
    # Guardar en BD
    database.save_monthly_report({
        "store_id": store_id,
        "month": date.today().replace(day=1).isoformat(),
        "content": report,
    })
    notifier.send_telegram(store_id, report)
    return report


# ── Consulta libre de Chuwi ──────────────────────────────────────────────────

def run_free_query(store_id: str, query: str, chat_history: list) -> str:
    """
    Responde preguntas libres del encargado usando el loop agéntico completo.
    Kuine puede consultar datos en tiempo real — no responde de memoria.
    """
    pending = database.get_pending_actions(store_id)
    brief = database.get_latest_brief(store_id)
    memory_ctx = mem.build_memory_context(store_id)

    system_query = (
        "Eres Kuine, el agente orquestador de MermaOps. "
        "El encargado del Super Martínez te pregunta algo. "
        "Usa tus herramientas para consultar datos reales antes de responder. "
        "NO inventes datos — si no sabes algo, dilo y busca la información. "
        "Sé directo y operativo. Máximo 5 líneas en la respuesta final. Sin asteriscos."
    )

    prompt = (
        f"Tienda: Super Martínez ({store_id})\n"
        f"Fecha: {date.today().isoformat()}\n"
        f"Acciones pendientes ahora: {len(pending)} "
        f"({sum(1 for a in pending if a.get('priority_score', 0) >= 85)} críticas)\n"
        f"Último brief: {brief.get('summary', 'Sin brief hoy')[:200] if brief else 'Sin brief hoy'}\n"
        f"Memoria histórica: {memory_ctx[:300] if memory_ctx else 'Sin historial'}\n\n"
        f"Pregunta del encargado: {query}\n\n"
        "Consulta los datos que necesites con tus herramientas y responde con precisión."
    )

    response, _ = llm.run_agentic_loop(
        prompt=prompt,
        tools=SUPERVISOR_TOOLS,
        tool_executor=_make_executor(store_id),
        system_extra=system_query,
        max_tokens=1024,
        max_iterations=6,
    )
    return response
