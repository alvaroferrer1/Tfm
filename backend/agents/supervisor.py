"""
Kuine — el cerebro orquestador de MermaOps.

Kuine investiga activamente la tienda usando herramientas especializadas, razona sobre
cada producto, coordina subagentes, crea acciones operativas y aprende patrones.
No procesa datos pre-seleccionados: DECIDE qué investigar, en qué orden, y qué hacer.

Identidad: Kuine es el agente orquestador. Chuwi es la interfaz con el encargado.
"""
from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

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
        # Cachear todas las definiciones de tools hasta este punto.
        # En el loop agéntico de 20 iteraciones, la 2ª–20ª lectura cuesta 10% del precio normal.
        # Ahorro real: ~80% en tokens de tool definitions por brief.
        # Ref: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching#tool-definitions
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
                    if b.get("products", {}).get("category", "").lower() == category.lower()
                ]
            # Enriquecer con días restantes
            today = date.today()
            for b in batches:
                try:
                    b["days_left"] = (date.fromisoformat(b["expiry_date"]) - today).days
                except (ValueError, KeyError):
                    b["days_left"] = 999
            return {"batches": batches, "count": len(batches)}

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

        return {"error": f"Herramienta desconocida: {tool_name}"}

    return executor


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
            return f"Producto con código {barcode} no encontrado en tienda ni en la base de datos global."
        return (
            f"Producto no registrado en esta tienda.\n\n"
            f"Encontrado en base de datos global:\n"
            f"Nombre: {product_info.get('name', 'Desconocido')}\n"
            f"Marca: {product_info.get('brand', '-')}\n"
            f"Categoría: {product_info.get('category', '-')}\n\n"
            f"Para registrarlo, usa la opción 'Añadir producto' en la app."
        )

    batches = database.get_batches_by_product(store_id, product["id"])
    if not batches:
        return f"{product['name']} — sin lotes activos registrados."

    soonest = min(batches, key=lambda b: b.get("expiry_date", "9999-99-99"))
    try:
        days_left = (date.fromisoformat(soonest["expiry_date"]) - date.today()).days
    except (ValueError, KeyError):
        days_left = 999

    warehouse_qty = database.get_warehouse_stock(store_id, product["id"])
    historical_context = mem.recall_product_pattern(store_id, product["id"]) or ""

    # Evaluador y stock son independientes entre sí — se ejecutan en paralelo.
    # stock.decide_restocking es puro Python (<1ms). Evaluator puede usar extended thinking (2-5s).
    # Ganar: el time to first response del scan se reduce al tiempo del evaluador solo.
    risk: dict = {}
    stock_dec: dict = {}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="scan") as pool:
        f_risk = pool.submit(
            evaluator.evaluate, product, batches,
            historical_context=historical_context, warehouse_qty=warehouse_qty
        )
        f_stock = pool.submit(stock.decide_restocking, product, batches, warehouse_qty)
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

    return llm.call(
        f"Genera la respuesta de escaneo para el empleado:\n\n{scan_context}",
        system_extra=(
            "Respuesta directa para el empleado. Máximo 5 líneas. "
            "Estructura: 1) Nombre + ubicación. 2) Situación (días, cantidad). "
            "3) ACCION concreta con precio exacto si aplica. 4) Reposición si/no. "
            "5) Una línea de justificación. Sin asteriscos."
        ),
        max_tokens=300,
    )


# ── Brief diario — flujo 07:30 ───────────────────────────────────────────────

def run_daily_brief(store_id: str) -> str:
    """
    Brief de apertura de tienda. Kuine usa el loop agéntico completo:
    investiga activamente, evalúa cada producto, crea acciones en BD y genera el brief.
    """
    import time as _time
    _t0 = _time.monotonic()
    today = date.today()
    weekday = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][today.weekday()]
    memory_ctx = mem.build_memory_context(store_id)

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
        "Cuando detectes exceso de stock con caducidad inminente, sugiere proactivamente donación al banco de alimentos."
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
{memory_ctx}

Al finalizar, genera el brief completo para el encargado."""

    response, tool_trace = llm.run_agentic_loop(
        prompt=prompt,
        tools=SUPERVISOR_TOOLS,
        tool_executor=_make_executor(store_id),
        system_extra=system_brief,
        max_tokens=4096,
        max_iterations=20,
    )

    # Guardar brief en BD
    pending = database.get_pending_actions(store_id)
    batches_today = database.get_batches_expiring_soon(store_id, days=7)
    total_value = sum(
        b.get("quantity", 0) * b.get("products", {}).get("price", 0)
        for b in batches_today
    )
    database.save_daily_brief({
        "store_id": store_id,
        "date": today.isoformat(),
        "summary": response,
        "value_at_risk": round(total_value, 2),
        "actions_count": len(pending),
    })

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

    mem.record_daily_stats(
        store_id,
        value_lost=float(value_at_risk) * 0.2,  # Estimación: 20% del riesgo se materializa
        items_discarded=len(critical_pending),
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
