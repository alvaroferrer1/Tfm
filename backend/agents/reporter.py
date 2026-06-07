"""
Reporter Agent — genera briefs, informes y alertas con contexto histórico.
Usa memoria episódica para comparar con periodos anteriores.
"""
from __future__ import annotations
from datetime import date
from backend.core import llm, database
from backend.agents.route import format_route_message


def generate_daily_brief(
    store_id: str,
    risk_reports: list[tuple],
    daily_route: dict,
    memory_context: str = "",
) -> str:
    today = date.today()
    total_value = sum(
        batch.get("quantity", 0) * (batch.get("products") or {}).get("price", 0)
        for batch, _ in risk_reports
    )

    def _level(risk):
        if isinstance(risk, dict):
            return risk.get("risk_level", "")
        return str(risk)

    critical = [(b, r) for b, r in risk_reports if "CRÍTICO" in _level(r)]
    high = [(b, r) for b, r in risk_reports if "ALTO" in _level(r)]
    route_text = format_route_message(daily_route)

    # Detalle de críticos
    critical_lines = []
    for batch, risk in critical[:8]:
        product = batch.get("products") or {}
        action = risk.get("action", "revisar") if isinstance(risk, dict) else "revisar"
        days = risk.get("days_left", "?") if isinstance(risk, dict) else "?"
        reasoning = risk.get("reasoning", "") if isinstance(risk, dict) else str(risk)[:100]
        critical_lines.append(
            f"- {product.get('name', '')} | Pasillo {product.get('pasillo', '?')} "
            f"| {days} dias | ACCION: {action.upper()} | {reasoning}"
        )

    # Tendencia automática respecto al día anterior (sin coste de LLM)
    trend_line = ""
    try:
        all_briefs = database.get_db().table("daily_briefs") \
            .select("date,critical_count,value_at_risk") \
            .eq("store_id", store_id) \
            .order("date", desc=True) \
            .limit(2) \
            .execute()
        briefs_data = all_briefs.data or []
        if len(briefs_data) >= 1:
            prev = briefs_data[0]  # el más reciente (ayer o antes)
            prev_critical = prev.get("critical_count", 0) or 0
            prev_value = float(prev.get("value_at_risk", 0) or 0)
            delta_critical = len(critical) - prev_critical
            trend_symbol = "↑" if delta_critical > 0 else ("↓" if delta_critical < 0 else "=")
            trend_line = (
                f"\nTENDENCIA vs dia anterior: {len(critical)} criticos hoy {trend_symbol} "
                f"(antes: {prev_critical}) | Valor en riesgo: {round(total_value, 2)}€ "
                f"{'(sube)' if total_value > prev_value else '(baja)' if total_value < prev_value else '(igual)'}"
            )
    except Exception:
        pass  # Tendencia opcional, no bloquea el brief

    context = f"""Fecha: {today.strftime('%A %d de %B de %Y')}
Total productos a gestionar hoy: {len(risk_reports)}
Situacion critica: {len(critical)} productos (requieren accion inmediata)
Situacion alta: {len(high)} productos (requieren accion antes del mediodia)
Valor total en riesgo: {round(total_value, 2)} euros
Tiempo estimado de ruta: {daily_route.get('estimated_minutes', 0)} minutos{trend_line}

PRODUCTOS CRITICOS HOY:
{chr(10).join(critical_lines) if critical_lines else "Ninguno"}

RUTA PROPUESTA:
{route_text}

CONTEXTO HISTORICO (patrones anteriores):
{memory_context or "Sin historial disponible todavia."}"""

    store_name = (database.get_store(store_id) or {}).get("name", "la tienda")
    brief_text = llm.call(
        f"Genera el brief de apertura para el encargado de {store_name}:\n\n{context}",
        system_extra=(
            "Eres Kuine generando el brief. Habla como si le explicaras la situación "
            "al encargado mientras toma un café antes de abrir. Se lee en 30 segundos.\n"
            "ESTRUCTURA CONVERSACIONAL (no tablas, no listas largas):\n"
            "1. Una frase de resumen: 'Hoy abrimos con X críticos en [sección], [sección] bien cubierta.'\n"
            "2. CRÍTICOS: guión por producto. Nombre, pasillo, acción, precio si hay. Sin tablas.\n"
            "3. Resto del día: qué hacer antes del mediodía y qué puede esperar.\n"
            "4. Cierre económico: 'Ayer se salvaron X€ en rebajas y las donaciones a Cáritas salieron a tiempo.'\n"
            "Máximo 250 palabras. Sin asteriscos. Sin markdown. Sin negritas.\n"
            "Jerga de tienda española: lineal, frescos, flejes, picar merma, FEFO, pasillo frío.\n"
            "MAYÚSCULAS solo para: REBAJAR, RETIRAR, DONAR, URGENTE."
        ),
        max_tokens=800,
    )

    # Añadir justificación normativa citada para el producto más crítico
    if critical:
        try:
            from backend.core import knowledge
            top_batch, top_risk = critical[0]
            top_product = top_batch.get("products") or {}
            top_name = top_product.get("name", "Producto crítico")
            top_cat = top_product.get("category", "general")
            top_days = top_risk.get("days_left", 0) if isinstance(top_risk, dict) else 0
            top_action = top_risk.get("action", "rebajar") if isinstance(top_risk, dict) else "rebajar"
            cited = knowledge.get_cited_decision(top_name, top_cat, top_days, top_action)
            if cited.citations:
                brief_text += f"\n\nNORMATIVA APLICADA ({top_name}):\n{cited.format_with_citations()}"
        except Exception:
            pass  # Citations son mejora opcional, no bloquean el brief

    return brief_text


def generate_intraday_alert(critical_actions: list[dict], store_id: str = "") -> str:
    """
    Alerta de mediodía para acciones críticas sin resolver.
    Retorna "" si no hay acciones críticas o si el último brief fue hace menos de 3h
    (para evitar spam cuando el scheduler la dispara muy seguido tras el brief).
    """
    if not critical_actions:
        return ""

    # No generar alerta si el brief de la mañana fue hace menos de 3 horas
    if store_id:
        try:
            from datetime import datetime, timezone
            brief = database.get_latest_brief(store_id)
            if brief:
                brief_ts = brief.get("created_at") or brief.get("date", "")
                if brief_ts:
                    if isinstance(brief_ts, str):
                        brief_dt = datetime.fromisoformat(brief_ts.replace("Z", "+00:00"))
                    else:
                        brief_dt = brief_ts
                    if brief_dt.tzinfo is None:
                        brief_dt = brief_dt.replace(tzinfo=timezone.utc)
                    elapsed_hours = (datetime.now(timezone.utc) - brief_dt).total_seconds() / 3600
                    if elapsed_hours < 3:
                        return ""  # brief muy reciente — el encargado lo acaba de leer
        except Exception:
            pass  # silencioso — la guardia es opcional

    items = []
    for action in critical_actions[:6]:
        batch_info = action.get("batches") or {}
        product_info = (batch_info.get("products") or {})
        name = product_info.get("name", "Producto desconocido")
        pasillo = product_info.get("pasillo", "?")
        score = action.get("priority_score", 0)
        notes = action.get("notes", "")
        items.append(f"- {name} | Pasillo {pasillo} | Prioridad {score}/100 | {notes[:60]}")

    items_text = "\n".join(items) if items else "- Sin detalle disponible"

    return llm.call(
        f"""Son las 12:00. Hay {len(critical_actions)} acciones CRÍTICAS sin resolver desde el brief de la mañana.

Acciones pendientes:
{items_text}

Genera un mensaje de alerta urgente para el encargado. Máximo 120 palabras. Sin asteriscos.""",
        max_tokens=200,
    )


def generate_closing_report(store_id: str) -> str:
    """Resumen de cierre del día con merma real, acciones completadas y donaciones."""
    from datetime import date, timedelta

    brief = database.get_latest_brief(store_id)
    pending = database.get_pending_actions(store_id)
    pending_critical = [a for a in pending if a.get("priority_score", 0) >= 80]

    # Merma del día
    merma_today = database.get_merma_history(store_id, days=1)
    merma_value = sum(float(r.get("value_lost", 0)) for r in merma_today)
    merma_qty = sum(int(r.get("quantity_lost", 0)) for r in merma_today)

    # Donaciones del día
    donation_stats = database.get_donation_stats(store_id, days=1)

    brief_summary = brief.get("summary", "Sin brief del día")[:400] if brief else "Sin brief del día"
    value_at_risk = brief.get("value_at_risk", 0) if brief else 0
    actions_count = brief.get("actions_count", 0) if brief else 0

    context = f"""Brief inicial del dia: {brief_summary}
Valor en riesgo al inicio: {value_at_risk} euros
Acciones generadas esta mañana: {actions_count}
Acciones CRITICAS pendientes al cierre: {len(pending_critical)}
Merma real registrada hoy: {merma_value:.2f} euros ({merma_qty} uds)
Donaciones realizadas hoy: {donation_stats['total_donations']} entregas — {donation_stats['total_quantity']} uds — {donation_stats['total_value_donated']:.2f} euros donados"""

    return llm.call(
        f"Genera el resumen de cierre del dia para el encargado:\n\n{context}",
        system_extra=(
            "Resumen ejecutivo de cierre: que se hizo, qué quedó pendiente, valoración del día. "
            "Incluye merma real y valor donado si los hay. "
            "Si hay críticos sin resolver, mencionarlo como punto de seguimiento para mañana. "
            "Máximo 200 palabras. Sin asteriscos."
        ),
        max_tokens=400,
    )


def generate_weekly_report(store_id: str) -> str:
    """Informe semanal con tendencias, donaciones, ficha de proveedores y ROI."""
    from backend.core import memory as mem

    patterns = mem.get_all_recent_patterns(store_id)
    pattern_text = "\n".join(f"- {k}: {v}" for k, v in patterns.items()) if patterns else "Sin datos históricos aún."

    # Merma y donaciones de la semana
    merma_week = database.get_merma_history(store_id, days=7)
    merma_value = sum(float(r.get("value_lost", 0)) for r in merma_week)
    merma_qty = sum(int(r.get("quantity_lost", 0)) for r in merma_week)
    donation_stats = database.get_donation_stats(store_id, days=7)

    # Merma evitada — valor recuperado por acciones completadas esta semana
    try:
        roi = database.get_completed_actions_value(store_id, days=7)
        merma_evitada = roi["value_recovered"]
        roi_ratio = round(merma_evitada / merma_value, 1) if merma_value > 0 else 0
        roi_line = (
            f"Merma evitada (acciones completadas): {merma_evitada:.2f} euros "
            f"({roi_ratio}x la merma real)"
        )
    except Exception:
        roi_line = "Merma evitada: sin datos suficientes"

    # Ficha de proveedores para detectar cuál genera más merma
    try:
        supplier_stats = database.get_supplier_stats(store_id)
        top_supplier = supplier_stats[0] if supplier_stats else None
        supplier_line = (
            f"Proveedor con mayor merma: {top_supplier['name']} ({top_supplier['avg_merma_pct']}% promedio)"
            if top_supplier else "Sin datos de proveedores"
        )
    except Exception:
        supplier_line = "Sin datos de proveedores"

    store_name = (database.get_store(store_id) or {}).get("name", "la tienda")
    return llm.call(
        f"""Genera el informe semanal de merma para {store_name}.

DATOS DE LA SEMANA:
- Merma registrada: {merma_value:.2f} euros ({merma_qty} uds)
- {roi_line}
- Donaciones realizadas: {donation_stats['total_donations']} entregas — {donation_stats['total_quantity']} uds — {donation_stats['total_value_donated']:.2f} euros
- {supplier_line}

PATRONES HISTÓRICOS:
{pattern_text}

El informe debe incluir:
1. Resumen ejecutivo (2 líneas con datos reales, incluyendo merma evitada)
2. Merma real vs merma evitada — cuánto ha recuperado el sistema esta semana
3. Impacto social — valor donado a entidades sociales
4. Proveedor más problemático y recomendación para negociación
5. 3 recomendaciones operativas accionables para la próxima semana

Máximo 420 palabras. Sin asteriscos. Usa mayúsculas para énfasis.""",
        system_extra="Eres el analista de merma del Súper Martínez. Informes concisos, basados en datos reales, orientados a reducción de costes y mejora continua.",
        max_tokens=850,
    )


def generate_monthly_report(store_id: str) -> str:
    """Informe mensual para el dueño — resumen ejecutivo con tendencias del mes."""
    from backend.core import memory as mem
    from datetime import date

    today = date.today()
    month_name = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ][today.month - 1]

    merma_month = database.get_merma_history(store_id, days=30)
    merma_value = sum(float(r.get("value_lost", 0)) for r in merma_month)
    merma_qty = sum(int(r.get("quantity_lost", 0)) for r in merma_month)
    donation_stats = database.get_donation_stats(store_id, days=30)

    # ROI del mes — merma evitada vs merma real
    try:
        roi = database.get_completed_actions_value(store_id, days=30)
        merma_evitada = roi["value_recovered"]
        roi_pct = round((merma_evitada / (merma_value + merma_evitada)) * 100, 1) if (merma_value + merma_evitada) > 0 else 0
        roi_line = (
            f"Merma evitada por el sistema: {merma_evitada:.2f} euros "
            f"({roi_pct}% del total de riesgo gestionado fue recuperado)"
        )
    except Exception:
        roi_line = "Merma evitada: sin datos suficientes este mes"

    try:
        supplier_stats = database.get_supplier_stats(store_id)
        sup_lines = "\n".join(
            f"  - {s['name']}: {s['avg_merma_pct']}% merma, riesgo {s['risk']}"
            for s in supplier_stats[:4]
        )
    except Exception:
        sup_lines = "  Sin datos de proveedores"

    try:
        order_suggestions = database.get_order_suggestions(store_id)
        top_orders = ", ".join(
            f"{s['product_name']} ({s['order_qty']} uds)"
            for s in order_suggestions[:3]
        )
    except Exception:
        top_orders = "Sin datos suficientes"

    patterns = mem.get_all_recent_patterns(store_id)
    pattern_text = "\n".join(
        f"- {k}: {v}" for k, v in list(patterns.items())[:5]
    ) if patterns else "Sin patrones disponibles."

    store_name = (database.get_store(store_id) or {}).get("name", "la tienda")
    return llm.call(
        f"""Genera el informe mensual de {month_name} {today.year} para el dueño de {store_name}.

RESUMEN OPERATIVO DEL MES:
- Merma registrada: {merma_value:.2f} euros — {merma_qty} unidades perdidas
- {roi_line}
- Donaciones sociales: {donation_stats['total_donations']} entregas — {donation_stats['total_quantity']} uds — {donation_stats['total_value_donated']:.2f} euros donados

PROVEEDORES (merma por proveedor):
{sup_lines}

PEDIDO RECOMENDADO PARA LA PRÓXIMA SEMANA:
- Productos prioritarios: {top_orders}

PATRONES DETECTADOS ESTE MES:
{pattern_text}

El informe para el dueño debe incluir:
1. Resumen ejecutivo del mes (3 líneas: merma real, merma evitada, ROI del sistema)
2. Comparativa con objetivo: ¿está la tienda mejorando? ¿cuánto ahorra MermaOps?
3. Proveedor más problemático y qué hacer
4. Impacto social de las donaciones (reputación, posible deducción fiscal)
5. 3 acciones prioritarias para el próximo mes

Tono: profesional, orientado a negocio, con datos reales. Máximo 500 palabras. Sin asteriscos.""",
        system_extra=(
            "Eres el analista de negocio del Súper Martínez. Escribes para el propietario, "
            "no para el encargado. Enfoque en coste, rentabilidad y imagen de marca. "
            "Usa datos reales y sé directo. Sin asteriscos."
        ),
        max_tokens=1000,
    )
