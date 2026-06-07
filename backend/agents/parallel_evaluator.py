"""
Parallel Evaluator — evalúa múltiples lotes simultáneamente con ThreadPoolExecutor.

Sin paralelización: 15 lotes × ~2s por llamada LLM = ~30s
Con paralelización: 15 lotes / 4 workers = ~8s

Las llamadas al LLM son I/O bound (red), no CPU bound: el GIL no es problema.
"""
from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from backend.agents import evaluator
from backend.core import database, memory as mem

logger = logging.getLogger("mermaops.parallel_evaluator")


def evaluate_all_parallel(
    store_id: str,
    days: int = 7,
    max_workers: int = 4,
) -> list[dict]:
    """
    Evalúa todos los lotes activos que caducan en `days` días, en paralelo.
    Devuelve lista ordenada por score descendente (más crítico primero).

    Cada resultado es compatible con el formato de evaluator.evaluate() más
    los campos de ubicación del producto.
    """
    batches = database.get_batches_expiring_soon(store_id, days=days)
    if not batches:
        return []

    def _eval_one(batch: dict) -> dict:
        product = batch.get("products") or {}
        product_id = product.get("id", "")

        # Datos de soporte — fallback silencioso si fallan
        historical = ""
        warehouse_qty = 0
        try:
            historical = mem.recall_product_pattern(store_id, product_id) or ""
            warehouse_qty = database.get_warehouse_stock(store_id, product_id)
        except Exception:
            pass

        try:
            from backend.agents.fork_merge import evaluate_fork_merge, should_use_fork_merge
            from backend.agents import stock as _stock
            # Para productos de alto valor: fork-merge
            if should_use_fork_merge(product, [batch]):
                risk = evaluate_fork_merge(
                    product, [batch],
                    historical_context=historical,
                    warehouse_qty=warehouse_qty,
                )
            else:
                risk = evaluator.evaluate(
                    product, [batch],
                    historical_context=historical,
                    warehouse_qty=warehouse_qty,
                )
        except Exception as e:
            logger.warning(f"[parallel] Error evaluando '{product.get('name', product_id)}': {e}")
            risk = {
                "risk_level": "MEDIO",
                "score": 50,
                "action": "revisar",
                "reasoning": f"Error en evaluación automática.",
                "price_adjustment_pct": 0,
                "thinking_summary": "",
                "days_left": 999,
                "total_value_at_risk": 0,
            }

        try:
            days_left = (date.fromisoformat(batch["expiry_date"]) - date.today()).days
        except (ValueError, KeyError):
            days_left = risk.get("days_left", 999)

        return {
            "batch_id": batch.get("id", ""),
            "product_id": product_id,
            "product_name": product.get("name", "Desconocido"),
            "category": product.get("category", ""),
            "pasillo": product.get("pasillo", "?"),
            "estanteria": product.get("estanteria", "?"),
            "nivel": product.get("nivel", "?"),
            "price": float(product.get("price", 0)),
            "cost": float(product.get("cost", 0)),
            "quantity": batch.get("quantity", 0),
            "expiry_date": batch.get("expiry_date", ""),
            "days_left": days_left,
            **risk,
        }

    results: list[dict] = []
    failed: list[str] = []

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="eval") as pool:
        future_map = {pool.submit(_eval_one, b): b for b in batches}
        for future in as_completed(future_map, timeout=90):
            batch = future_map[future]
            product_name = (batch.get("products") or {}).get("name", batch.get("id", "?"))
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"[parallel] Future falló para '{product_name}': {e}")
                failed.append(product_name)

    if failed:
        logger.warning(f"[parallel] {len(failed)} evaluaciones sin completar: {failed}")

    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    return results


def summary_stats(results: list[dict]) -> dict:
    """Estadísticas agregadas del resultado de evaluación paralela."""
    if not results:
        return {
            "total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0,
            "total_value_at_risk": 0.0, "actions_needed": 0,
        }

    counts = {"CRÍTICO": 0, "ALTO": 0, "MEDIO": 0, "BAJO": 0}
    total_value = 0.0
    actions_needed = 0

    for r in results:
        level = r.get("risk_level", "BAJO")
        counts[level] = counts.get(level, 0) + 1
        total_value += float(r.get("total_value_at_risk", 0))
        if r.get("action", "ok") not in ("ok", "revisar"):
            actions_needed += 1

    return {
        "total": len(results),
        "critical": counts["CRÍTICO"],
        "high": counts["ALTO"],
        "medium": counts["MEDIO"],
        "low": counts["BAJO"],
        "total_value_at_risk": round(total_value, 2),
        "actions_needed": actions_needed,
    }
