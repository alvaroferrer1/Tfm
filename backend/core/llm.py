"""
Claude API wrapper — prompt caching, tool use, extended thinking, citations, observability.
Fundación del sistema MermaOps.
"""
from __future__ import annotations
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import anthropic
from dotenv import load_dotenv

logger = logging.getLogger("mermaops.llm")

load_dotenv()

MODEL = "claude-sonnet-4-6"
MODEL_FAST = "claude-haiku-4-5-20251001"   # salidas estructuradas simples, checks rápidos
MODEL_DEEP = "claude-opus-4-8"             # síntesis compleja, árbitros, informes mensuales

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


# ── Token cost tracker ────────────────────────────────────────────────────────
# Precios por millón de tokens (Anthropic, mayo 2025)
_PRICE_PER_1M: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00,  "cache_read": 0.08,  "cache_write": 1.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00, "cache_read": 0.30,  "cache_write": 3.75},
    "claude-opus-4-7":           {"input": 15.00, "output": 75.00, "cache_read": 1.50,  "cache_write": 18.75},
    "claude-opus-4-8":           {"input": 15.00, "output": 75.00, "cache_read": 1.50,  "cache_write": 18.75},
}

# Acumulador global (se resetea al reiniciar el proceso — basta para la demo)
_cost_tracker: dict[str, float] = {
    "total_usd": 0.0,
    "saved_usd": 0.0,
    "calls": 0.0,
    "cache_hits": 0.0,
    "input_tokens": 0.0,
    "output_tokens": 0.0,
    "cache_read_tokens": 0.0,
}


def _tok(usage: Any, attr: str) -> int:
    """Extrae un contador de tokens de forma segura (0 si MagicMock o None)."""
    val = getattr(usage, attr, None)
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def _track_cost(usage: Any, model: str) -> tuple[float, float]:
    """
    Calcula el coste real y el coste sin caché para una llamada.
    Actualiza el acumulador global y devuelve (actual_usd, baseline_usd).
    """
    prices = _PRICE_PER_1M.get(model, _PRICE_PER_1M["claude-sonnet-4-6"])
    cache_read  = _tok(usage, "cache_read_input_tokens")
    cache_write = _tok(usage, "cache_creation_input_tokens")
    input_tok   = _tok(usage, "input_tokens")
    output_tok  = _tok(usage, "output_tokens")

    actual = (
        input_tok   * prices["input"]        / 1_000_000 +
        output_tok  * prices["output"]       / 1_000_000 +
        cache_read  * prices["cache_read"]   / 1_000_000 +
        cache_write * prices["cache_write"]  / 1_000_000
    )
    baseline = (
        (input_tok + cache_read + cache_write) * prices["input"]  / 1_000_000 +
        output_tok                             * prices["output"] / 1_000_000
    )
    saved = baseline - actual

    _cost_tracker["total_usd"]        += actual
    _cost_tracker["saved_usd"]        += max(0.0, saved)
    _cost_tracker["calls"]            += 1
    _cost_tracker["input_tokens"]     += input_tok + cache_read + cache_write
    _cost_tracker["output_tokens"]    += output_tok
    _cost_tracker["cache_read_tokens"] += cache_read
    if cache_read > 0:
        _cost_tracker["cache_hits"] += 1

    return actual, baseline


def get_cost_summary() -> dict:
    """Devuelve el resumen de coste de la sesión actual."""
    t = _cost_tracker
    calls = int(t["calls"])
    cache_hit_pct = round(t["cache_hits"] / calls * 100) if calls > 0 else 0
    total = t["total_usd"]
    saved = t["saved_usd"]
    saving_pct = round(saved / (total + saved) * 100) if (total + saved) > 0 else 0
    return {
        "total_usd": round(total, 6),
        "saved_usd": round(saved, 6),
        "saving_pct": saving_pct,
        "calls": calls,
        "cache_hit_pct": cache_hit_pct,
        "input_tokens": int(t["input_tokens"]),
        "output_tokens": int(t["output_tokens"]),
        "cache_read_tokens": int(t["cache_read_tokens"]),
    }


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
        actual, baseline = _track_cost(usage, model)
        logger.debug(
            f"[{label}] tokens in={usage.input_tokens} out={usage.output_tokens} "
            f"cache_read={cache_read} cache_write={cache_write} "
            f"cost=${actual:.6f} saved=${baseline - actual:.6f} "
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
    fast: bool = False,
) -> tuple[str, str]:
    """
    Llamada con thinking (Sonnet 4.6).
    fast=False (default): adaptive mode — Claude decide cuánto pensar. Para briefs y análisis profundos.
    fast=True: enabled mode con budget acotado — máx 1500 tokens de razonamiento. Para scans interactivos.
    Devuelve (respuesta_final, bloque_de_razonamiento).
    """
    t0 = time.monotonic()
    thinking_param = (
        {"type": "enabled", "budget_tokens": min(budget_tokens, 1500)}
        if fast
        else {"type": "adaptive"}
    )
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens if not fast else min(max_tokens, 2048),
        thinking=thinking_param,
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
    initial_messages: Optional[list[dict]] = None,
    model: str | None = None,
    cancel_event: "threading.Event | None" = None,
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
    messages: list[dict] = list(initial_messages) if initial_messages else []
    messages.append({"role": "user", "content": prompt})
    tool_trace: list[dict] = []
    t0 = time.monotonic()

    # Adaptive thinking params — solo para modelos que lo soportan (Sonnet 4.6+)
    thinking_param = {"type": "adaptive"} if adaptive_thinking else None
    _model = model or MODEL

    for iteration in range(max_iterations):
        # Cancelación cooperativa: si el llamador señala cancel_event, paramos limpiamente
        if cancel_event is not None and cancel_event.is_set():
            logger.info(f"[llm] run_agentic_loop cancelado en iteración {iteration}")
            break
        create_kwargs: dict = dict(
            model=_model,
            max_tokens=max_tokens,
            system=_cached_system(system_extra),
            tools=tools,
            tool_choice={"type": "auto"},
            messages=messages,
        )
        if thinking_param:
            create_kwargs["thinking"] = thinking_param

        # Token-efficient tool use: formato compacto de tool definitions (~15% ahorro).
        # Ref: https://docs.anthropic.com/en/docs/build-with-claude/tool-use/token-efficient-tool-use
        response = client.messages.create(
            **create_kwargs,
            extra_headers={"anthropic-beta": "token-efficient-tools-2025-02-19"},
        )

        # Si Claude llegó a una conclusión final, terminamos
        if response.stop_reason == "end_turn":
            _log_usage(response, f"agentic_loop[{iteration}]", prompt=prompt[:200], duration_ms=(time.monotonic() - t0) * 1000)
            return _extract_text(response), tool_trace

        # Si Claude quiere usar herramientas, las ejecutamos (en paralelo con ThreadPoolExecutor)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            def _run_tool(block):
                try:
                    result = tool_executor(block.name, block.input)
                except Exception as e:
                    result = {"error": str(e)}
                return block, result

            import concurrent.futures
            tool_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tool_use_blocks), 5)) as pool:
                # Mantener el orden original de tool_use_blocks (Claude requiere orden consistente)
                futures = [(b, pool.submit(_run_tool, b)) for b in tool_use_blocks]
                for block, future in futures:
                    _, result = future.result()
                    serialized = json.dumps(result, ensure_ascii=False, default=str)
                    tool_trace.append({
                        "tool": block.name,
                        "input": block.input,
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
        model=_model,  # usa el modelo original del caller, no el default global
        max_tokens=max_tokens,
        system=_cached_system(system_extra),
        messages=messages,
    )
    if thinking_param:
        final_kwargs["thinking"] = thinking_param
    final = client.messages.create(**final_kwargs)
    _log_usage(final, "agentic_loop_final_synthesis", prompt=prompt[:200],
               duration_ms=(time.monotonic() - t0) * 1000, model=_model)
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


# ── Circuit breaker — previene gasto descontrolado en loops agénticos ─────────

class _CBState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class _LLMCircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.state = _CBState.CLOSED
        self.failure_count = 0
        self.last_failure = 0.0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._lock = threading.Lock()

    def before_call(self) -> None:
        with self._lock:
            if self.state == _CBState.OPEN:
                if time.monotonic() - self.last_failure > self.recovery_timeout:
                    self.state = _CBState.HALF_OPEN
                else:
                    raise RuntimeError(
                        "[circuit_breaker] Claude API temporalmente suspendida — "
                        "demasiados errores consecutivos. Espera 60s o reinicia."
                    )

    def on_success(self) -> None:
        with self._lock:
            self.failure_count = max(0, self.failure_count - 1)
            if self.state == _CBState.HALF_OPEN:
                self.state = _CBState.CLOSED

    def on_failure(self, exc: Exception) -> None:
        with self._lock:
            self.failure_count += 1
            self.last_failure = time.monotonic()
            if self.failure_count >= self.failure_threshold:
                self.state = _CBState.OPEN
                logger.error(
                    f"[circuit_breaker] OPEN — {self.failure_count} fallos consecutivos. "
                    f"Último: {str(exc)[:120]}"
                )


_circuit_breaker = _LLMCircuitBreaker(failure_threshold=5, recovery_timeout=60.0)


def call_with_retry(func: Callable, *args, max_retries: int = 3, **kwargs) -> Any:
    """
    Llama a `func` con retry exponencial + jitter para errores recuperables
    (rate limit 429, server error 529/500). Pasa por el circuit breaker global.
    """
    _circuit_breaker.before_call()
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            _circuit_breaker.on_success()
            return result
        except Exception as exc:
            err = str(exc)
            retriable = any(code in err for code in ("429", "529", "500", "rate_limit", "overloaded"))
            if not retriable or attempt == max_retries - 1:
                _circuit_breaker.on_failure(exc)
                raise
            delay = (2 ** attempt) + random.uniform(0, 1.0)
            logger.warning(f"[llm] retry {attempt + 1}/{max_retries} en {delay:.1f}s — {err[:80]}")
            time.sleep(delay)
    raise RuntimeError("call_with_retry: max retries sin resultado")
