"""
Knowledge base — normativa de seguridad alimentaria para decisiones de agentes.

IMPLEMENTACIÓN ACTUAL: búsqueda por keywords sobre 12 documentos en memoria Python.
DISEÑO FUTURO: interfaz compatible con pgvector (tabla knowledge_base en Supabase, VECTOR 1536).
La interfaz pública (query, get_context_for_decision) NO cambia al activar pgvector.
Soporta Citations API de Anthropic para trazabilidad completa.
"""
from __future__ import annotations

_FOOD_SAFETY_KB: list[dict] = [
    {
        "category": "caducidad_general",
        "content": (
            "Los productos con fecha de caducidad (no consumo preferente) no pueden venderse ni donarse "
            "una vez superada dicha fecha. Deben retirarse de la venta el mismo día de caducidad. "
            "La diferencia entre 'fecha de caducidad' y 'consumo preferente': caducidad indica riesgo sanitario real, "
            "consumo preferente indica pérdida de calidad organoléptica pero el producto no es peligroso."
        ),
        "keywords": ["caducidad", "fecha", "retirar", "vencimiento", "expirado"],
    },
    {
        "category": "carne_fresca",
        "content": (
            "La carne fresca debe mantenerse a 0-4°C. Con 1 día o menos hasta caducidad: retirar de venta inmediatamente "
            "o rebajar máximo 50% si aún está dentro de fecha. "
            "Con 2 días: descuento obligatorio del 30-40%. "
            "No se puede reponer carne fresca cuando queda menos de 48 horas hasta caducidad del lote actual — "
            "el nuevo stock empujaría el viejo al fondo. Aplicar FEFO estrictamente."
        ),
        "keywords": ["carne", "pollo", "cerdo", "ternera", "picada", "pechuga", "lomo", "fresca"],
    },
    {
        "category": "pescado_fresco",
        "content": (
            "El pescado fresco es el producto más perecedero. Temperatura máxima 2°C. "
            "Con 1 día o menos: retirar de venta o donar a banco de alimentos si está en perfectas condiciones. "
            "Con 2 días: descuento del 35-50% obligatorio. "
            "La merluza y otros pescados blancos pierden calidad rápidamente — prioridad CRÍTICA con 1 día. "
            "El salmón ahumado tiene mayor vida útil pero igual requiere vigilancia."
        ),
        "keywords": ["pescado", "merluza", "salmón", "salmon", "bacalao", "atún", "marisco"],
    },
    {
        "category": "lacteos",
        "content": (
            "Lácteos frescos (yogur, nata, queso fresco, leche fresca): mantener a 4°C máximo. "
            "Con 2 días o menos hasta caducidad: descuento del 30-40%. "
            "Con 1 día: descuento del 50% o retirar. "
            "El yogur caduca después de la fecha marcada pero pierde calidad organoléptica antes. "
            "La nata fresca y el queso fresco son más sensibles — prioridad alta con 2 días restantes."
        ),
        "keywords": ["lacteos", "yogur", "leche", "nata", "queso", "mantequilla", "kefir"],
    },
    {
        "category": "panaderia",
        "content": (
            "Pan fresco y bollería: vida muy corta, generalmente 1-3 días. "
            "La baguette artesana debe rebajarse el mismo día de caducidad en las últimas horas. "
            "Bollería (croissants, donuts) pierde calidad rápidamente — considerar donar antes de caducar "
            "si el banco de alimentos acepta. "
            "Pan de molde: mayor duración que pan fresco artesano; aplicar descuento del 20% con 3 días."
        ),
        "keywords": ["pan", "baguette", "croissant", "bollería", "panadería", "molde", "integral"],
    },
    {
        "category": "frutas_verduras",
        "content": (
            "Frutas y verduras: vida variable. Las fresas y frutas rojas son muy perecederas (2-4 días). "
            "Ensaladas en bolsa: 3-5 días. Si hay daño visual, retirar aunque no haya caducado. "
            "Descuentos progresivos: 20% con 2 días, 35% con 1 día. "
            "Donar a banco de alimentos frutas con pequeños defectos estéticos pero perfectamente comestibles."
        ),
        "keywords": ["fruta", "verdura", "fresa", "ensalada", "tomate", "lechuga", "naranja", "manzana"],
    },
    {
        "category": "donacion",
        "content": (
            "Para donar al banco de alimentos: el producto debe estar dentro de fecha, en condiciones higiénicas "
            "correctas, sin daños graves. La donación es preferible al descarte cuando el producto tiene "
            "al menos 24 horas de vida útil. Los supermercados en España pueden deducir el valor de las donaciones. "
            "Proceso: registrar en merma_log con razón 'donacion', contactar banco de alimentos local."
        ),
        "keywords": ["donar", "donación", "banco de alimentos", "descarte", "eliminar"],
    },
    {
        "category": "descuentos_legales",
        "content": (
            "En España, no hay restricciones legales en el porcentaje de descuento aplicable a productos "
            "próximos a caducar siempre que el precio final sea positivo y el producto esté dentro de fecha. "
            "El descuento debe marcarse claramente con el nuevo precio visible junto al antiguo. "
            "No se puede vender por debajo de coste de adquisición en algunos municipios (revisar normativa local). "
            "El límite práctico es el precio de coste + 5% mínimo para cubrir manipulación."
        ),
        "keywords": ["descuento", "precio", "rebaja", "ilegal", "legal", "normativa", "margen"],
    },
    {
        "category": "temperatura_cadena_frio",
        "content": (
            "La cadena de frío es crítica. Si un producto ha estado a temperatura incorrecta, "
            "su fecha de caducidad real puede ser anterior a la marcada. "
            "Señales de ruptura de cadena: condensación en packaging, cristales de hielo en productos "
            "que no deberían tenerlos, cambio de color en carnes/pescados. "
            "Ante duda de cadena de frío rota: RETIRAR aunque la fecha no haya llegado."
        ),
        "keywords": ["temperatura", "frío", "refrigeración", "cadena", "congelación"],
    },
    {
        "category": "estadisticas_merma_retail",
        "content": (
            "Estadísticas de referencia para benchmarking (fuentes: Eurostat 2024, FAO, UE): "
            "El sector retail genera el 8% del total de residuos alimentarios de la UE, "
            "equivalente a 10 kg por habitante y año. "
            "A nivel global, el 14% de los alimentos se pierde antes del retail y un 17% adicional "
            "en retail y consumo. "
            "Los productos más desperdiciados en retail europeo: frutas (27%), verduras (20%), "
            "cereales (13%). España está entre los países de la UE con menor desperdicio relativo. "
            "Impacto económico: un supermercado mediano pierde entre el 2% y el 5% de sus ingresos "
            "por merma de frescos. MermaOps reduce este ratio en un 30-50% según benchmarks de "
            "herramientas similares (Winnow: hasta 50% de reducción en frescos)."
        ),
        "keywords": ["estadísticas", "porcentaje", "merma", "pérdida", "benchmark", "eurostat", "fao", "retail"],
    },
    {
        "category": "csrd_esg_normativa_2026",
        "content": (
            "Marco regulatorio ESG en España (actualizado mayo 2026): "
            "La Directiva Ómnibus I (UE 2026/470, en vigor 18 marzo 2026) modifica la CSRD. "
            "Nuevos umbrales: solo aplica a empresas con >1.000 empleados Y >450M€ de facturación. "
            "Las PYMEs quedan exentas del reporting CSRD obligatorio. "
            "PERO: los grandes clientes/proveedores SÍ reportan y trasladarán solicitudes de datos "
            "ESG a sus cadenas de suministro (chain reporting). Los bancos exigen métricas de "
            "sostenibilidad para préstamos verdes (ICO líneas verdes 2024-2026). "
            "Deducción fiscal por donaciones alimentarias: 35% sobre valor de mercado (Ley 49/2002, art. 19). "
            "ESRS E5 (Recursos y Economía Circular): estándar aplicable a residuos alimentarios — "
            "requiere divulgar kg de residuos, métodos de recuperación (reutilización, reciclaje)."
        ),
        "keywords": ["csrd", "esg", "sostenibilidad", "obligatorio", "omnibus", "ley", "normativa", "reporting", "pyme"],
    },
    {
        "category": "competidores_ia_merma",
        "content": (
            "Contexto competitivo (referencia para decisiones estratégicas): "
            "Winnow: líder en HORECA (cocinas profesionales, hoteles). >3.500 sites, 94 países. "
            "Usa visión artificial + báscula para identificar residuos automáticamente. "
            "Logra 2-8% reducción de coste alimentario. No tiene agente conversacional ni app móvil. "
            "Su producto retail se enfoca en counters de deli de grandes cadenas, no en PYMEs. "
            "Wasteless: pricing dinámico basado en caducidad para retailers. No tiene agente IA ni Telegram. "
            "Orbisk: cámara sobre cubo de basura para registro automático. Solo HORECA. "
            "Diferencial MermaOps: único sistema que combina agente conversacional (Telegram) + "
            "app móvil + automatización completa + pensado para PYMEs sin departamento IT."
        ),
        "keywords": ["competidor", "winnow", "wasteless", "orbisk", "diferencial", "mercado", "comparativa"],
    },
]


def query(query_text: str, top_k: int = 3) -> list[str]:
    """
    Búsqueda por keywords en la base de conocimiento.
    Usa la tabla knowledge_base de Supabase si está disponible (con datos reales).
    Fallback a los 12 documentos en memoria si Supabase no responde.
    Interfaz compatible con futura migración a pgvector.
    """
    # Intentar Supabase primero (datos reales ya poblados)
    try:
        from backend.core.database import get_db
        res = get_db().table("knowledge_base").select("content, category").execute()
        if res.data:
            db_kb = [{"content": r["content"], "category": r.get("category", ""), "keywords": []} for r in res.data]
            return _keyword_score(query_text, db_kb, top_k)
    except Exception:
        pass  # fallback al KB en memoria

    return _keyword_score(query_text, _FOOD_SAFETY_KB, top_k)


def _keyword_score(query_text: str, kb: list[dict], top_k: int) -> list[str]:
    q_lower = query_text.lower()
    scored: list[tuple[int, dict]] = []

    for entry in kb:
        score = 0
        for kw in entry.get("keywords", []):
            if kw in q_lower:
                score += 2
        if entry.get("category", "").replace("_", " ") in q_lower:
            score += 3
        for word in q_lower.split():
            if len(word) > 4 and word in entry.get("content", "").lower():
                score += 1
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry["content"] for _, entry in scored[:top_k]]


def get_regulations_for_category(category: str) -> str:
    """Devuelve las regulaciones específicas de una categoría de producto."""
    category_map = {
        "carne": "carne_fresca",
        "pescado": "pescado_fresco",
        "lacteos": "lacteos",
        "panaderia": "panaderia",
        "fruta": "frutas_verduras",
        "verdura": "frutas_verduras",
    }
    target = category_map.get(category.lower(), "caducidad_general")
    for entry in _FOOD_SAFETY_KB:
        if entry["category"] == target:
            return entry["content"]
    return ""


def search_as_documents(query_text: str, top_k: int = 3) -> list[dict]:
    """
    Igual que query() pero devuelve los resultados en formato de documentos para
    la Citations API de Anthropic. Cada documento tiene 'title' y 'content'.
    """
    q_lower = query_text.lower()
    scored: list[tuple[int, dict]] = []

    for entry in _FOOD_SAFETY_KB:
        score = 0
        for kw in entry["keywords"]:
            if kw in q_lower:
                score += 2
        if entry["category"].replace("_", " ") in q_lower:
            score += 3
        for word in q_lower.split():
            if len(word) > 4 and word in entry["content"].lower():
                score += 1
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "title": entry["category"].replace("_", " ").title(),
            "content": entry["content"],
            "category": entry["category"],
        }
        for _, entry in scored[:top_k]
    ]


def get_context_for_decision(product_category: str, days_left: int, action_being_considered: str) -> str:
    """
    Construye un bloque de contexto normativo para una decisión específica.
    Usado por el Evaluador antes de su análisis con extended thinking.
    """
    fragments = []

    # Category-specific regulation
    cat_reg = get_regulations_for_category(product_category)
    if cat_reg:
        fragments.append(cat_reg)

    # Action-specific guidance
    if action_being_considered in ("donar", "donate"):
        donation_info = next(
            (e["content"] for e in _FOOD_SAFETY_KB if e["category"] == "donacion"), ""
        )
        if donation_info:
            fragments.append(donation_info)

    if action_being_considered in ("rebajar", "descuento"):
        discount_info = next(
            (e["content"] for e in _FOOD_SAFETY_KB if e["category"] == "descuentos_legales"), ""
        )
        if discount_info:
            fragments.append(discount_info)

    # General rule if near/at expiry
    if days_left <= 0:
        fragments.append(
            "ALERTA CRÍTICA: Producto con fecha de caducidad hoy o ya superada. "
            "Solo 'consumo preferente' puede seguir en venta. 'Caducidad' debe retirarse inmediatamente."
        )

    return "\n\n".join(fragments) if fragments else "Aplicar criterio general: rebajar progresivamente con proximidad a caducidad."


def get_cited_decision(
    product_name: str,
    product_category: str,
    days_left: int,
    action_being_considered: str,
) -> "CitedResponse":
    """
    Llama a Claude con Citations API para justificar una decisión operativa,
    citando exactamente qué normativa usó. Devuelve CitedResponse.

    Uso por agentes:
        result = knowledge.get_cited_decision("Nata fresca", "lacteos", 1, "rebajar")
        print(result.format_with_citations())
    """
    from backend.core.llm import call_with_citations, CitedResponse

    # Construir documentos relevantes para Citations API
    documents = []

    # Normativa específica de categoría
    cat_doc = next(
        (e for e in _FOOD_SAFETY_KB if e["category"] == _category_key(product_category)),
        None,
    )
    if cat_doc:
        documents.append({"title": cat_doc["category"].replace("_", " ").title(), "content": cat_doc["content"]})

    # Normativa de la acción
    action_keys = {
        "donar": "donacion",
        "donate": "donacion",
        "rebajar": "descuentos_legales",
        "descuento": "descuentos_legales",
    }
    action_key = action_keys.get(action_being_considered)
    if action_key:
        action_doc = next((e for e in _FOOD_SAFETY_KB if e["category"] == action_key), None)
        if action_doc:
            documents.append({"title": action_doc["category"].replace("_", " ").title(), "content": action_doc["content"]})

    # Caducidad general siempre como contexto
    gen_doc = next((e for e in _FOOD_SAFETY_KB if e["category"] == "caducidad_general"), None)
    if gen_doc:
        documents.append({"title": "Regla general caducidad", "content": gen_doc["content"]})

    if not documents:
        return CitedResponse(text=get_context_for_decision(product_category, days_left, action_being_considered))

    prompt = (
        f"Producto: {product_name} (categoría: {product_category}). "
        f"Días hasta caducidad: {days_left}. "
        f"Acción considerada: {action_being_considered}. "
        f"Basándote ÚNICAMENTE en los documentos de normativa proporcionados, "
        f"justifica si esta acción es correcta, qué descuento aplicar y por qué. "
        f"Sé conciso y específico — el empleado necesita actuar en 30 segundos."
    )

    return call_with_citations(prompt, documents, max_tokens=512)


def _category_key(category: str) -> str:
    return {
        "carne": "carne_fresca",
        "pescado": "pescado_fresco",
        "lacteos": "lacteos",
        "panaderia": "panaderia",
        "fruta": "frutas_verduras",
        "verdura": "frutas_verduras",
    }.get(category.lower(), "caducidad_general")


