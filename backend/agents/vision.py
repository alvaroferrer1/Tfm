"""
Vision Agent — analiza fotos de productos con Claude Vision (multimodal).

Capacidades:
  - Detecta el estado visual: fresco, deteriorado, dañado, posiblemente expirado
  - Identifica problemas específicos: manchas, golpes, envase roto, moho
  - Lee la fecha de caducidad visible si aparece en la foto
  - Sugiere la acción operativa (rebajar/retirar/ok) basándose solo en lo visual
  - Compara el estado visual con los días restantes según el sistema

Fundamento real: Winnow y Orbisk usan visión artificial para detectar
residuos y frescura. Nadie lo tiene integrado en un agente conversacional
para retail pequeño con Claude Vision.
"""
from __future__ import annotations
import base64
import logging
from datetime import date, timedelta
from backend.core import llm

logger = logging.getLogger("mermaops.vision")

# CO2 por kg por categoría (kg CO2eq / kg alimento) — fuente: Poore & Nemecek 2018, FAO 2023
_CO2_KG: dict[str, float] = {
    "carne": 60.0,
    "carne_ternera": 60.0,
    "carne_cerdo": 7.6,
    "carne_pollo": 5.7,
    "carne_cordero": 24.0,
    "pescado": 6.1,
    "pescado_salvaje": 4.0,
    "marisco": 8.0,
    "lacteos": 3.2,
    "queso": 13.5,
    "huevos": 4.5,
    "panaderia": 1.1,
    "bolleria": 2.2,
    "fruta": 0.5,
    "verdura": 0.4,
    "legumbres": 1.8,
    "bebidas": 0.4,
    "bebidas_lacteas": 3.2,
    "conservas": 1.5,
    "congelados": 2.0,
    "embutidos": 8.5,
    "aceite": 3.8,
    "default": 2.5,
}

_VISION_SYSTEM = (
    "Eres el inspector visual de calidad de MermaOps. "
    "Analizas fotos de productos alimentarios en un supermercado español. "
    "Tu diagnóstico es directo, operativo y sin ambigüedades. "
    "Escribe en texto limpio, sin asteriscos ni markdown. "
    "Si no puedes ver el producto con claridad, dilo."
)


def _get_co2_factor(category: str) -> float:
    cat = (category or "").lower().replace(" ", "_")
    return _CO2_KG.get(cat, _CO2_KG["default"])


def analyze_product_photo(
    image_base64: str,
    product_name: str = "",
    days_left: int = -1,
    category: str = "",
    media_type: str = "image/jpeg",
) -> dict:
    """
    Analiza visualmente un producto alimentario.

    Returns dict:
      condition       — "bueno" | "deteriorado" | "dañado" | "posiblemente_expirado" | "no_identificado"
      issues          — lista de problemas visuales detectados
      action          — "ok" | "rebajar" | "retirar" | "revisar"
      urgency         — "inmediata" | "hoy" | "normal" | "ninguna"
      visible_date    — fecha visible en la foto si la hay (str o None)
      date_matches    — True/False/None si se puede comparar con days_left
      confidence      — 0-100 (qué tan claro es el diagnóstico)
      diagnosis       — texto de una línea para el empleado
      full_analysis   — texto completo del análisis
    """
    context_lines = []
    if product_name:
        context_lines.append(f"Producto esperado: {product_name}")
    if category:
        context_lines.append(f"Categoría: {category}")
    if days_left >= 0:
        context_lines.append(
            f"Días hasta caducidad según sistema: {days_left} días"
        )

    context = "\n".join(context_lines)

    prompt = f"""Analiza visualmente este producto alimentario de un supermercado español.

{context}

Sé específico: si hay manchas, di dónde. Si el envase está roto, describe dónde.
Si la fecha de caducidad visible no coincide con {days_left if days_left >= 0 else 'N/A'} días del sistema, indícalo.
La acción debe ser inmediatamente ejecutable por un empleado de tienda."""

    _VISION_SCHEMA = {
        "type": "object",
        "properties": {
            "condition": {
                "type": "string",
                "enum": ["bueno", "deteriorado", "danado", "posiblemente_expirado", "no_identificado"],
                "description": "Estado visual del producto",
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Problemas visuales específicos detectados. Array vacío si no hay.",
            },
            "visible_date": {
                "type": "string",
                "description": "Fecha de caducidad visible en la etiqueta, o null si no se ve.",
            },
            "action": {
                "type": "string",
                "enum": ["ok", "rebajar", "retirar", "revisar"],
                "description": "Acción operativa recomendada",
            },
            "urgency": {
                "type": "string",
                "enum": ["inmediata", "hoy", "normal", "ninguna"],
                "description": "Urgencia de la acción",
            },
            "confidence": {
                "type": "integer",
                "description": "Confianza del diagnóstico 0-100",
            },
            "diagnosis": {
                "type": "string",
                "description": "Una línea para el empleado: qué hacer exactamente y por qué.",
            },
            "full_analysis": {
                "type": "string",
                "description": "Análisis detallado completo para el encargado.",
            },
        },
        "required": ["condition", "issues", "action", "urgency", "confidence", "diagnosis", "full_analysis"],
    }

    try:
        # Claude Vision + structured output: enviamos la imagen al modelo y extraemos JSON
        import anthropic as _anthropic
        from backend.core.llm import get_client, _cached_system, _log_usage
        import time as _time

        t0 = _time.monotonic()
        response = get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=_cached_system(_VISION_SYSTEM),
            tools=[{
                "name": "vision_analysis",
                "description": "Resultado estructurado del análisis visual del producto.",
                "input_schema": _VISION_SCHEMA,
            }],
            tool_choice={"type": "any"},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_base64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        _log_usage(response, "vision_structured", prompt=prompt[:100],
                   duration_ms=(_time.monotonic() - t0) * 1000)

        structured: dict = {}
        for block in response.content:
            if hasattr(block, "type") and block.type == "tool_use" and block.name == "vision_analysis":
                structured = block.input
                break

        if not structured:
            raise ValueError("Structured output vacío")

    except Exception as e:
        logger.error(f"[vision] Error en análisis: {e}")
        return {
            "condition": "no_identificado",
            "issues": [str(e)],
            "action": "revisar",
            "urgency": "normal",
            "visible_date": None,
            "date_matches": None,
            "confidence": 0,
            "diagnosis": "Error en análisis visual. Revisar manualmente.",
            "full_analysis": str(e),
        }

    logger.info(f"[vision] Análisis completado para '{product_name}': {structured.get('condition')} / {structured.get('action')}")

    visible_date_str = structured.get("visible_date") or None
    action = structured.get("action", "revisar")

    # Comparar fecha visible en la foto con los días que dice el sistema
    date_matches: bool | None = None
    if visible_date_str and days_left >= 0:
        try:
            visible_dt = date.fromisoformat(visible_date_str)
            expected_dt = date.today() + timedelta(days=days_left)
            diff = abs((visible_dt - expected_dt).days)
            date_matches = diff <= 1  # Tolerancia de 1 día para errores de escaneo
            if diff > 3:
                logger.warning(
                    f"[vision] Fecha visible '{visible_date_str}' diverge del sistema "
                    f"({days_left} días restantes) en {diff} días — posible error de datos"
                )
        except (ValueError, TypeError):
            pass

    # CO2 estimado en caso de retirada — la tabla _CO2_KG existe desde el inicio
    # pero nunca se había usado en el resultado de análisis
    co2_kg_wasted: float | None = None
    if action == "retirar" and category:
        weight_kg = 0.4  # peso medio estimado por unidad (400g) si no hay dato
        co2_factor = _get_co2_factor(category)
        co2_kg_wasted = round(weight_kg * co2_factor, 3)

    result = {
        "condition": structured.get("condition", "no_identificado"),
        "issues": structured.get("issues", []),
        "action": action,
        "urgency": structured.get("urgency", "normal"),
        "visible_date": visible_date_str,
        "date_matches": date_matches,
        "confidence": structured.get("confidence", 50),
        "diagnosis": structured.get("diagnosis", ""),
        "full_analysis": structured.get("full_analysis", ""),
        "co2_kg_wasted": co2_kg_wasted,
    }

    return result


def analyze_from_telegram_file(
    file_bytes: bytes,
    product_name: str = "",
    days_left: int = -1,
    category: str = "",
) -> dict:
    """Wrapper: recibe bytes de Telegram y llama al analizador."""
    image_b64 = base64.b64encode(file_bytes).decode()
    return analyze_product_photo(
        image_base64=image_b64,
        product_name=product_name,
        days_left=days_left,
        category=category,
        media_type="image/jpeg",
    )


def format_vision_result(result: dict) -> str:
    """Formatea el resultado de visión para Telegram (texto limpio, sin markdown)."""
    # "danado" es el valor del enum (sin tilde — JSON normalizado), "dañado" es el display
    condition_label = {
        "bueno": "VERDE",
        "deteriorado": "AMARILLO",
        "danado": "NARANJA",       # enum value sin tilde
        "dañado": "NARANJA",       # por si Claude devuelve con tilde
        "posiblemente_expirado": "ROJO",
        "no_identificado": "GRIS",
    }
    estado = condition_label.get(result["condition"], "GRIS")

    lines = [
        f"ANALISIS VISUAL — {estado}",
        "",
        f"Estado: {result['condition'].upper().replace('_', ' ')}",
        f"Accion recomendada: {result['action'].upper()}",
        f"Urgencia: {result['urgency'].upper()}",
    ]

    if result.get("issues"):
        lines.append(f"Problemas: {', '.join(result['issues'])}")

    if result.get("visible_date"):
        date_ok = result.get("date_matches")
        match_note = ""
        if date_ok is True:
            match_note = " (coincide con sistema)"
        elif date_ok is False:
            match_note = " — DISCREPANCIA CON SISTEMA"
        lines.append(f"Fecha en etiqueta: {result['visible_date']}{match_note}")

    lines += ["", result.get("diagnosis", ""), ""]

    if result.get("co2_kg_wasted") is not None:
        lines.append(f"CO2 estimado si se retira: {result['co2_kg_wasted']} kg CO2eq")

    lines.append(f"Confianza: {result.get('confidence', 0)}%")

    return "\n".join(lines)
