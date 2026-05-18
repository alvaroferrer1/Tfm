"""
Claude API wrapper — prompt caching, tool use, extended thinking, citations, observability.
Fundación del sistema MermaOps.
"""
from __future__ import annotations
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic
from dotenv import load_dotenv

logger = logging.getLogger("mermaops.llm")

load_dotenv()

MODEL = "claude-sonnet-4-6"
MODEL_FAST = "claude-haiku-4-5-20251001"   # salidas estructuradas simples, checks rápidos
MODEL_DEEP = "claude-opus-4-7"             # síntesis compleja, árbitros, informes mensuales

# ── Langfuse observability (opcional — activa si LANGFUSE_PUBLIC_KEY presente) ──
# Usa OpenTelemetry AnthropicInstrumentor — auto-instrumenta TODAS las llamadas
# sin necesidad de modificar cada función individualmente.
# Ref: https://langfuse.com/integrations/model-providers/anthropic (SDK v3, 2025)

_langfuse_initialized: bool = False


def _init_langfuse() -> bool:
    """
    Inicializa Langfuse + OpenTelemetry si las claves están disponibles.
    Llama esto una vez al arrancar el backend. Silent si faltan claves o paquetes.
    """
    global _langfuse_initialized
    if _langfuse_initialized:
        return _langfuse_initialized
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    if not pk or not sk:
        return False
    try:
        from langfuse import get_client as lf_client
        from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", pk)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", sk)
        os.environ.setdefault("LANGFUSE_HOST", host)

        AnthropicInstrumentor().instrument()
        lf = lf_client()
        lf.auth_check()
        _langfuse_initialized = True
        logger.info("Langfuse + AnthropicInstrumentor activo → %s", host)
    except ImportError as e:
        logger.debug("Langfuse/OTEL no instalado (%s) — observabilidad desactivada", e)
    except Exception as e:
        logger.warning("Langfuse init error: %s — continuando sin observabilidad", e)
    return _langfuse_initialized


def _trace_call(
    name: str,
    model: str,
    prompt: str,
    response_text: str,
    usage: Any,
    duration_ms: float,
    metadata: dict | None = None,
) -> None:
    """
    Fallback manual de traza para cuando AnthropicInstrumentor no está disponible.
    Con Langfuse+OTEL activo, este método no se usa — OTEL instrumenta automáticamente.
    """
    if _langfuse_initialized:
        return  # OTEL ya lo captura — no duplicar
    try:
        from langfuse import get_client as lf_client
        lf = lf_client()
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        trace = lf.trace(name=f"mermaops.{name}", metadata=metadata or {})
        trace.generation(
            name=name,
            model=model,
            input=prompt[:4000],
            output=response_text[:4000],
            usage={"input": input_tokens, "output": output_tokens,
                   "cache_read": cache_read, "cache_write": cache_write},
            metadata={"duration_ms": round(duration_ms, 1), **(metadata or {})},
        )
    except Exception as e:
        logger.debug("Langfuse manual trace error: %s", e)


# ── Citation result type ──────────────────────────────────────────────────────

@dataclass
class CitedResponse:
    """Respuesta con citas a documentos fuente — para transparencia y trazabilidad."""
    text: str
    citations: list[dict] = field(default_factory=list)

    def format_with_citations(self) -> str:
        """Formatea la respuesta con las citas como notas al pie."""
        if not self.citations:
            return self.text
        lines = [self.text, "", "FUENTES:"]
        for i, c in enumerate(self.citations, 1):
            doc_title = c.get("document_title", "Normativa MermaOps")
            excerpt = c.get("cited_text", "")[:120]
            lines.append(f"[{i}] {doc_title}: \"{excerpt}...\"")
        return "\n".join(lines)

# System prompt base — se cachea en todas las llamadas repetidas (90% ahorro)
SYSTEM_BASE = """\
Eres el núcleo de inteligencia de MermaOps, sistema de gestión de merma alimentaria \
para supermercados españoles.

Tu misión: convertir datos de productos, lotes, fechas de caducidad y stock en \
decisiones operativas claras, justificadas y priorizadas para el personal de tienda.

Principios de razonamiento:
- Nunca apliques reglas fijas. Cada situación es diferente: razona con los datos reales.
- Un producto de alto valor con 1 día de vida es diferente a uno de bajo valor. Considera el margen.
- Si hay patrones históricos, úsalos para ajustar la prioridad.
- Sé específico: no digas "rebajar", di "rebajar -35% → nuevo precio 1.85 euros".
- Tus respuestas van al personal de tienda. Deben ser accionables en 30 segundos.
- Escribe en texto limpio, sin asteriscos ni símbolos de markdown. Usa mayúsculas para énfasis.
"""

_client: anthropic.Anthropic | None = None
_async_client: "anthropic.AsyncAnthropic | None" = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY no está definido en .env")
        _client = anthropic.Anthropic(api_key=key)
    return _client


def get_async_client() -> "anthropic.AsyncAnthropic":
    """Cliente async — para streaming en tiempo real (Chuwi)."""
    global _async_client
    if _async_client is None:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY no está definido en .env")
        _async_client = anthropic.AsyncAnthropic(api_key=key)
    return _async_client


def _cached_system(extra: str = "") -> list[dict]:
    """Construye el system prompt con cache_control para prompt caching."""
    text = SYSTEM_BASE + ("\n\n" + extra if extra else "")
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


# ── Llamada simple ────────────────────────────────────────────────────────────

def _log_usage(
    response: anthropic.types.Message,
    label: str = "call",
    prompt: str = "",
    duration_ms: float = 0.0,
    model: str = MODEL,
) -> None:
    usage = getattr(response, "usage", None)
    if usage:
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        logger.debug(
            f"[{label}] tokens in={usage.input_tokens} out={usage.output_tokens} "
            f"cache_read={cache_read} cache_write={cache_write} "
            f"duration_ms={duration_ms:.0f}"
        )
        _trace_call(
            name=label,
            model=model,
            prompt=prompt,
            response_text=_extract_text(response),
            usage=usage,
            duration_ms=duration_ms,
        )


def call(
    prompt: str,
    system_extra: str = "",
    max_tokens: int = 1024,
) -> str:
    """Llamada directa sin tool use. Para tareas simples y rápidas."""
    t0 = time.monotonic()
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        messages=[{"role": "user", "content": prompt}],
    )
    _log_usage(response, "call", prompt=prompt, duration_ms=(time.monotonic() - t0) * 1000)
    return _extract_text(response)


# ── Citations API (Anthropic, 2025) ──────────────────────────────────────────
# Permite que Claude cite exactamente qué fragmento de documento usó para
# cada parte de su respuesta. Clave para trazabilidad y anti-alucinación.

def call_with_citations(
    prompt: str,
    documents: list[dict],
    system_extra: str = "",
    max_tokens: int = 1024,
) -> "CitedResponse":
    """
    Llamada con Citations API — Claude cita los fragmentos exactos de cada documento
    que usó para construir su respuesta.

    documents: lista de dicts con claves 'title', 'content' (y opcionalmente 'id').
    Devuelve CitedResponse con .text y .citations (lista de citas con documento y texto citado).

    Ejemplo de uso:
        docs = [{"title": "Normativa carne fresca", "content": "..."}]
        result = call_with_citations("¿Cuándo rebajar la carne?", docs)
        print(result.format_with_citations())
    """
    doc_blocks = []
    for i, doc in enumerate(documents):
        doc_blocks.append({
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": doc["content"],
            },
            "title": doc.get("title", f"Documento {i + 1}"),
            "citations": {"enabled": True},
        })
    doc_blocks.append({"type": "text", "text": prompt})

    t0 = time.monotonic()
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        messages=[{"role": "user", "content": doc_blocks}],
    )
    duration_ms = (time.monotonic() - t0) * 1000
    _log_usage(response, "call_with_citations", prompt=prompt, duration_ms=duration_ms)

    # Extraer texto y citas del response
    text_parts = []
    citations = []
    for block in response.content:
        if not hasattr(block, "type"):
            continue
        if block.type == "text":
            text_parts.append(block.text)
            # Extraer citas del bloque si las hay
            raw_citations = getattr(block, "citations", None) or []
            for c in raw_citations:
                citations.append({
                    "document_title": getattr(c, "document_title", ""),
                    "cited_text": getattr(c, "cited_text", ""),
                    "document_index": getattr(c, "document_index", 0),
                    "start_char_index": getattr(c, "start_char_index", 0),
                    "end_char_index": getattr(c, "end_char_index", 0),
                })

    return CitedResponse(text="\n".join(text_parts).strip(), citations=citations)


# ── Llamadas con routing de modelo ───────────────────────────────────────────

def call_fast(
    prompt: str,
    system_extra: str = "",
    max_tokens: int = 512,
) -> str:
    """Haiku — para outputs simples, checks rápidos, tareas sin razonamiento profundo."""
    t0 = time.monotonic()
    response = get_client().messages.create(
        model=MODEL_FAST,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        messages=[{"role": "user", "content": prompt}],
    )
    _log_usage(response, "call_fast", prompt=prompt, duration_ms=(time.monotonic() - t0) * 1000, model=MODEL_FAST)
    return _extract_text(response)


def call_deep(
    prompt: str,
    system_extra: str = "",
    max_tokens: int = 2048,
) -> str:
    """Opus — para síntesis complejas, decisiones críticas, informes de negocio."""
    t0 = time.monotonic()
    response = get_client().messages.create(
        model=MODEL_DEEP,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        messages=[{"role": "user", "content": prompt}],
    )
    _log_usage(response, "call_deep", prompt=prompt, duration_ms=(time.monotonic() - t0) * 1000, model=MODEL_DEEP)
    return _extract_text(response)


def call_structured_fast(
    prompt: str,
    output_schema: dict,
    system_extra: str = "",
    max_tokens: int = 256,
) -> dict:
    """call_structured() con Haiku — para voting simple, outputs cortos y estructurados."""
    extraction_tool = {
        "name": "structured_output",
        "description": "Devuelve el resultado estructurado del análisis.",
        "input_schema": output_schema,
    }
    t0 = time.monotonic()
    response = get_client().messages.create(
        model=MODEL_FAST,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        tools=[extraction_tool],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )
    _log_usage(response, "call_structured_fast", prompt=prompt, duration_ms=(time.monotonic() - t0) * 1000, model=MODEL_FAST)
    for block in response.content:
        if block.type == "tool_use" and block.name == "structured_output":
            return block.input
    return {}


def call_vision(
    image_base64: str,
    prompt: str,
    media_type: str = "image/jpeg",
    system_extra: str = "",
    max_tokens: int = 1024,
) -> str:
    """
    Analiza una imagen con Claude Vision.
    Acepta imagen en base64. Usa Sonnet (soporta visión multimodal).
    """
    t0 = time.monotonic()
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_base64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    _log_usage(response, "call_vision", prompt=prompt, duration_ms=(time.monotonic() - t0) * 1000)
    return _extract_text(response)


def call_structured_deep(
    prompt: str,
    output_schema: dict,
    system_extra: str = "",
    max_tokens: int = 1024,
) -> dict:
    """call_structured() con Opus — árbitros de consenso y decisiones de alto impacto."""
    extraction_tool = {
        "name": "structured_output",
        "description": "Devuelve el resultado estructurado del análisis.",
        "input_schema": output_schema,
    }
    t0 = time.monotonic()
    response = get_client().messages.create(
        model=MODEL_DEEP,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        tools=[extraction_tool],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )
    _log_usage(response, "call_structured_deep", prompt=prompt, duration_ms=(time.monotonic() - t0) * 1000, model=MODEL_DEEP)
    for block in response.content:
        if block.type == "tool_use" and block.name == "structured_output":
            return block.input
    return {}


# ── Streaming async con historial (para Chuwi) ───────────────────────────────

async def stream_with_history(
    messages: list[dict],
    system_extra: str = "",
    max_tokens: int = 1024,
):
    """
    Generador async — emite chunks de texto a medida que Claude los genera.
    Úsalo con 'async for chunk in stream_with_history(...)'.
    """
    client = get_async_client()
    async with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        messages=messages,
    ) as stream:
        async for chunk in stream.text_stream:
            yield chunk


# ── Llamada con historial ─────────────────────────────────────────────────────

def call_with_history(
    messages: list[dict],
    system_extra: str = "",
    max_tokens: int = 2048,
) -> str:
    """Llamada con historial de conversación (para Chuwi)."""
    t0 = time.monotonic()
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        messages=messages,
    )
    _log_usage(response, "call_with_history", prompt=str(messages[-1])[:200] if messages else "", duration_ms=(time.monotonic() - t0) * 1000)
    return _extract_text(response)


# ── Adaptive thinking (Anthropic, mayo 2025) ─────────────────────────────────
# Modo recomendado para Sonnet 4.6 y Opus 4.7.
# Claude decide cuándo y cuánto pensar según la complejidad de cada request.
# Activa automáticamente interleaved thinking entre tool calls en agentic loops.
# Ref: https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking

def call_with_thinking(
    prompt: str,
    system_extra: str = "",
    budget_tokens: int = 8000,
    max_tokens: int = 12000,
) -> tuple[str, str]:
    """
    Llamada con adaptive thinking (Sonnet 4.6 / Opus 4.7).
    El parámetro budget_tokens se mantiene por compatibilidad pero se ignora —
    en adaptive mode Claude gestiona su propio presupuesto de tokens de razonamiento.
    Devuelve (respuesta_final, bloque_de_razonamiento).
    """
    t0 = time.monotonic()
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=_cached_system(system_extra),
        messages=[{"role": "user", "content": prompt}],
    )
    _log_usage(response, "call_with_thinking", prompt=prompt, duration_ms=(time.monotonic() - t0) * 1000)
    text = _extract_text(response)
    thinking = _extract_thinking(response)
    return text, thinking


# ── Agentic loop con tool use ─────────────────────────────────────────────────

def run_agentic_loop(
    prompt: str,
    tools: list[dict],
    tool_executor: Callable[[str, dict], Any],
    system_extra: str = "",
    max_tokens: int = 4096,
    max_iterations: int = 15,
    adaptive_thinking: bool = True,
) -> tuple[str, list[dict]]:
    """
    Loop agéntico completo: Claude llama herramientas hasta tener la respuesta.
    Devuelve (respuesta_final, trace_de_herramientas).

    Con adaptive_thinking=True (por defecto en Sonnet 4.6): activa interleaved
    thinking entre tool calls — Claude razona sobre cada resultado antes de
    decidir el siguiente paso. Referencia: Anthropic adaptive thinking docs.
    Benchmark: +54% en τ-Bench airline domain (Anthropic, 2025).
    """
    client = get_client()
    messages: list[dict] = [{"role": "user", "content": prompt}]
    tool_trace: list[dict] = []
    t0 = time.monotonic()

    # Adaptive thinking params — solo para modelos que lo soportan (Sonnet 4.6+)
    thinking_param = {"type": "adaptive"} if adaptive_thinking else None

    for iteration in range(max_iterations):
        create_kwargs: dict = dict(
            model=MODEL,
            max_tokens=max_tokens,
            system=_cached_system(system_extra),
            tools=tools,
            tool_choice={"type": "auto"},
            messages=messages,
        )
        if thinking_param:
            create_kwargs["thinking"] = thinking_param

        response = client.messages.create(**create_kwargs)

        # Si Claude llegó a una conclusión final, terminamos
        if response.stop_reason == "end_turn":
            _log_usage(response, f"agentic_loop[{iteration}]", prompt=prompt[:200], duration_ms=(time.monotonic() - t0) * 1000)
            return _extract_text(response), tool_trace

        # Si Claude quiere usar herramientas, las ejecutamos
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    try:
                        result = tool_executor(tool_name, tool_input)
                    except Exception as e:
                        result = {"error": str(e)}

                    serialized = json.dumps(result, ensure_ascii=False, default=str)
                    tool_trace.append({
                        "tool": tool_name,
                        "input": tool_input,
                        "output_preview": serialized[:200],
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": serialized,
                    })

            messages.append({"role": "user", "content": tool_results})

    # Si agotamos iteraciones, pedimos síntesis con lo que tiene
    messages.append({
        "role": "user",
        "content": "Con la información recopilada hasta ahora, proporciona la respuesta final.",
    })
    final_kwargs: dict = dict(
        model=MODEL,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        messages=messages,
    )
    if thinking_param:
        final_kwargs["thinking"] = thinking_param
    final = client.messages.create(**final_kwargs)
    return _extract_text(final), tool_trace


# ── Salida estructurada JSON ──────────────────────────────────────────────────

def call_structured(
    prompt: str,
    output_schema: dict,
    system_extra: str = "",
    max_tokens: int = 2048,
) -> dict:
    """
    Usa tool_use para forzar salida JSON estructurada.
    Más fiable que pedirle a Claude que responda en JSON directamente.
    """
    extraction_tool = {
        "name": "structured_output",
        "description": "Devuelve el resultado estructurado del análisis.",
        "input_schema": output_schema,
    }
    t0 = time.monotonic()
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        tools=[extraction_tool],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )
    _log_usage(response, "call_structured", prompt=prompt, duration_ms=(time.monotonic() - t0) * 1000)
    for block in response.content:
        if block.type == "tool_use" and block.name == "structured_output":
            return block.input
    return {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_text(response: anthropic.types.Message) -> str:
    parts = []
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _extract_thinking(response: anthropic.types.Message) -> str:
    for block in response.content:
        if hasattr(block, "type") and block.type == "thinking":
            return block.thinking
    return ""
