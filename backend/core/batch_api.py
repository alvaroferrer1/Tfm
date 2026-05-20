"""
Anthropic Batch API — evaluación masiva de productos a mitad de coste.

Cuándo usar:
  - Briefs nocturnos / de apertura temprana (no urgentes, ~1h de espera OK)
  - Evaluación masiva de 50-500 productos en una pasada
  - Generación de informes semanales / mensuales

Beneficio: 50% de ahorro vs llamadas en tiempo real.
Documentación: https://docs.anthropic.com/en/api/creating-message-batches
"""
from __future__ import annotations
import json
import logging
import time
from typing import Any

from backend.core.llm import get_client, MODEL, _cached_system, _PRICE_PER_1M

logger = logging.getLogger("mermaops.batch")

_EVALUATOR_SYSTEM = (
    "Eres el Evaluador de MermaOps. Analizas riesgo de productos alimentarios en un supermercado español. "
    "Devuelve SOLO un JSON con: score (0-100), risk_level (CRÍTICO/ALTO/MEDIO/BAJO), "
    "action (rebajar/retirar/donar/revisar/ok), price_adjustment_pct (0-70), reasoning (1 línea)."
)

_EVAL_PROMPT_TEMPLATE = """\
Evalúa este producto:
Nombre: {name}
Categoría: {category}
Días hasta caducidad: {days_left}
Cantidad en tienda: {qty}
Precio: {price}€ | Coste: {cost}€
Valor en riesgo: {value_at_risk}€
Contexto histórico: {context}

Responde SOLO con JSON válido."""


# ── Envío de batch ────────────────────────────────────────────────────────────

def submit_evaluation_batch(products_data: list[dict]) -> str | None:
    """
    Envía un batch de evaluaciones de producto.

    products_data: lista de dicts con claves:
        id, name, category, days_left, qty, price, cost, context (opcional)

    Devuelve el batch_id de Anthropic (str), o None si el servicio no está disponible.
    Persiste el batch_id en log para poder recuperarlo después.
    """
    if not products_data:
        return None

    client = get_client()
    requests = []
    for p in products_data:
        custom_id = f"eval-{p['id']}-{int(time.time())}"
        value_at_risk = round(float(p.get("qty", 0)) * float(p.get("price", 0)), 2)
        prompt = _EVAL_PROMPT_TEMPLATE.format(
            name=p.get("name", "?"),
            category=p.get("category", "general"),
            days_left=p.get("days_left", "?"),
            qty=p.get("qty", 0),
            price=p.get("price", 0),
            cost=p.get("cost", 0),
            value_at_risk=value_at_risk,
            context=p.get("context", "Sin historial."),
        )
        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": MODEL,
                "max_tokens": 300,
                "system": _cached_system(_EVALUATOR_SYSTEM),
                "messages": [{"role": "user", "content": prompt}],
            },
        })

    try:
        batch = client.messages.batches.create(requests=requests)
        batch_id = batch.id
        logger.info(f"[batch] Enviado: {batch_id} — {len(requests)} productos")
        return batch_id
    except Exception as e:
        logger.error(f"[batch] Error enviando: {e}")
        return None


# ── Consulta de estado ────────────────────────────────────────────────────────

def get_batch_status(batch_id: str) -> dict:
    """
    Devuelve el estado del batch y, si está completo, los resultados parseados.

    Returns:
        {
          "status": "processing" | "ended" | "canceling" | "expired",
          "results": [...] or None,
          "cost_usd": float (estimado),
          "saved_pct": int,
        }
    """
    client = get_client()
    try:
        batch = client.messages.batches.retrieve(batch_id)
        status = batch.processing_status

        if status != "ended":
            counts = batch.request_counts
            return {
                "status": status,
                "results": None,
                "processing": getattr(counts, "processing", 0),
                "succeeded": getattr(counts, "succeeded", 0),
                "errored": getattr(counts, "errored", 0),
            }

        # Batch completado — leer resultados
        results = []
        total_input = 0
        total_output = 0

        for result in client.messages.batches.results(batch_id):
            custom_id = result.custom_id
            if result.result.type == "succeeded":
                msg = result.result.message
                usage = getattr(msg, "usage", None)
                if usage:
                    total_input  += getattr(usage, "input_tokens", 0) or 0
                    total_output += getattr(usage, "output_tokens", 0) or 0

                text = ""
                for block in msg.content:
                    if hasattr(block, "type") and block.type == "text":
                        text += block.text

                parsed: dict[str, Any] = {}
                try:
                    import re
                    m = re.search(r'\{.*\}', text, re.DOTALL)
                    if m:
                        parsed = json.loads(m.group())
                except Exception:
                    pass

                results.append({
                    "custom_id": custom_id,
                    "ok": True,
                    "score": parsed.get("score", 0),
                    "risk_level": parsed.get("risk_level", "BAJO"),
                    "action": parsed.get("action", "revisar"),
                    "price_adjustment_pct": parsed.get("price_adjustment_pct", 0),
                    "reasoning": parsed.get("reasoning", ""),
                })
            else:
                results.append({"custom_id": custom_id, "ok": False, "error": str(result.result)})

        prices = _PRICE_PER_1M[MODEL]
        actual_cost = (
            total_input  * prices["input"]  / 1_000_000 * 0.5 +  # batch = 50% descuento
            total_output * prices["output"] / 1_000_000 * 0.5
        )
        baseline_cost = (
            total_input  * prices["input"]  / 1_000_000 +
            total_output * prices["output"] / 1_000_000
        )

        logger.info(f"[batch] {batch_id} completado: {len(results)} resultados — coste ~${actual_cost:.4f}")
        return {
            "status": "ended",
            "results": results,
            "total": len(results),
            "cost_usd": round(actual_cost, 6),
            "baseline_usd": round(baseline_cost, 6),
            "saved_pct": 50,
        }

    except Exception as e:
        logger.error(f"[batch] Error consultando {batch_id}: {e}")
        return {"status": "error", "results": None, "error": str(e)}


# ── Helper: preparar productos desde BD ──────────────────────────────────────

def products_to_batch_input(batches: list[dict], memory_fn=None) -> list[dict]:
    """
    Convierte lotes de la BD al formato que espera submit_evaluation_batch.

    batches: resultado de database.get_batches_expiring_soon()
    memory_fn: callable(store_id, product_id) → str con contexto histórico (opcional)
    """
    from datetime import date
    results = []
    for b in batches:
        product = b.get("products") or {}
        product_id = b.get("product_id", b.get("id", ""))
        try:
            days_left = (date.fromisoformat(b["expiry_date"]) - date.today()).days
        except Exception:
            days_left = 999

        context = ""
        if memory_fn and product_id:
            try:
                context = memory_fn(product_id) or ""
            except Exception:
                pass

        results.append({
            "id": b.get("id", product_id),
            "name": product.get("name", "Producto"),
            "category": product.get("category", "general"),
            "days_left": days_left,
            "qty": b.get("quantity", 0),
            "price": float(product.get("price", 0)),
            "cost": float(product.get("cost", 0)),
            "context": context,
        })
    return results
