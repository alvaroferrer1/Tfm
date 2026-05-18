"""
MermaOps Benchmark — Evaluación empírica de modelos para el TFM.

Compara Haiku vs Sonnet vs Opus en los escenarios clave del sistema:
  1. Evaluación de riesgo de producto (¿cuánto tarda? ¿acierta el nivel?)
  2. Generación de texto del brief diario (¿calidad? ¿longitud óptima?)
  3. Extracción de salida estructurada (¿fiabilidad del esquema?)
  4. Consulta a base de conocimiento con Citations API (¿cita correctamente?)

Genera tablas comparativas listas para incluir en el TFM.
Uso:
    python -m backend.data.benchmark
    python -m backend.data.benchmark --scenario riesgo
    python -m backend.data.benchmark --output resultados_benchmark.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

# ── Escenarios de prueba ──────────────────────────────────────────────────────

RISK_SCENARIOS = [
    {
        "id": "carne_1dia",
        "product": "Carne picada 500g",
        "category": "carne",
        "days_left": 1,
        "quantity": 8,
        "price": 4.20,
        "expected_risk": "CRÍTICO",
        "expected_action_keyword": "retirar",
    },
    {
        "id": "yogur_2dias",
        "product": "Yogur natural 125g",
        "category": "lacteos",
        "days_left": 2,
        "quantity": 24,
        "price": 0.85,
        "expected_risk": "ALTO",
        "expected_action_keyword": "rebajar",
    },
    {
        "id": "pan_hoy",
        "product": "Baguette artesana",
        "category": "panaderia",
        "days_left": 0,
        "quantity": 5,
        "price": 1.20,
        "expected_risk": "CRÍTICO",
        "expected_action_keyword": "retirar",
    },
    {
        "id": "leche_5dias",
        "product": "Leche entera 1L",
        "category": "lacteos",
        "days_left": 5,
        "quantity": 30,
        "price": 1.10,
        "expected_risk": "BAJO",
        "expected_action_keyword": "monitorizar",
    },
    {
        "id": "merluza_1dia",
        "product": "Merluza fresca 400g",
        "category": "pescado",
        "days_left": 1,
        "quantity": 3,
        "price": 7.90,
        "expected_risk": "CRÍTICO",
        "expected_action_keyword": "donar",
    },
]

BRIEF_SCENARIO = {
    "store": "Súper Martínez",
    "date": "hoy",
    "critical_count": 3,
    "high_count": 7,
    "value_at_risk": 187.50,
    "route": ["Pasillo 1 (Lácteos)", "Pasillo 2 (Carne)", "Pasillo 4 (Panadería)"],
    "top_actions": [
        "RETIRAR Baguette artesana — Pasillo 4 — caduca hoy",
        "REBAJAR 40% Nata fresca 200ml — Pasillo 2 — 1 día",
        "DONAR 3 ud. Merluza fresca — Banco de Alimentos",
    ],
}

STRUCTURED_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_level": {"type": "string", "enum": ["CRÍTICO", "ALTO", "MEDIO", "BAJO"]},
        "action": {"type": "string", "enum": ["retirar", "rebajar", "donar", "reponer", "monitorizar"]},
        "discount_pct": {"type": "integer", "minimum": 0, "maximum": 70},
        "reasoning": {"type": "string"},
    },
    "required": ["risk_level", "action", "discount_pct", "reasoning"],
}

# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ScenarioResult:
    scenario_id: str
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    success: bool
    correct: bool
    output_preview: str
    error: str = ""
    cost_usd: float = 0.0


@dataclass
class BenchmarkSuite:
    results: list[ScenarioResult] = field(default_factory=list)

    def add(self, r: ScenarioResult) -> None:
        self.results.append(r)

    def summary_table(self) -> str:
        """Genera tabla de resumen lista para el TFM."""
        if not self.results:
            return "Sin resultados."

        models = sorted({r.model for r in self.results})
        scenarios = sorted({r.scenario_id for r in self.results})

        lines = []
        lines.append("\n" + "=" * 80)
        lines.append("BENCHMARK MERMAOPS — COMPARATIVA DE MODELOS")
        lines.append("=" * 80)

        # Por modelo
        for model in models:
            model_results = [r for r in self.results if r.model == model]
            if not model_results:
                continue

            success_rate = sum(1 for r in model_results if r.success) / len(model_results) * 100
            correct_rate = sum(1 for r in model_results if r.correct) / len(model_results) * 100
            avg_latency = statistics.mean(r.latency_ms for r in model_results)
            median_latency = statistics.median(r.latency_ms for r in model_results)
            avg_input = statistics.mean(r.input_tokens for r in model_results)
            avg_output = statistics.mean(r.output_tokens for r in model_results)
            total_cost = sum(r.cost_usd for r in model_results)
            cache_pct = (
                sum(r.cache_read_tokens for r in model_results)
                / max(sum(r.input_tokens for r in model_results), 1)
                * 100
            )

            lines.append(f"\n{'─' * 40}")
            lines.append(f"Modelo: {model}")
            lines.append(f"{'─' * 40}")
            lines.append(f"  Escenarios ejecutados : {len(model_results)}")
            lines.append(f"  Tasa de éxito          : {success_rate:.0f}%")
            lines.append(f"  Precisión (correcto)   : {correct_rate:.0f}%")
            lines.append(f"  Latencia media         : {avg_latency:.0f} ms")
            lines.append(f"  Latencia mediana       : {median_latency:.0f} ms")
            lines.append(f"  Tokens entrada (media) : {avg_input:.0f}")
            lines.append(f"  Tokens salida (media)  : {avg_output:.0f}")
            lines.append(f"  Cache hit rate         : {cache_pct:.0f}%")
            lines.append(f"  Coste total estimado   : ${total_cost:.4f}")

        # Tabla comparativa por escenario
        lines.append(f"\n\n{'─' * 80}")
        lines.append("LATENCIA POR ESCENARIO (ms)")
        lines.append(f"{'Escenario':<25} " + " ".join(f"{m[:20]:<22}" for m in models))
        lines.append("─" * 80)
        for scenario_id in scenarios:
            row = f"{scenario_id:<25} "
            for model in models:
                rs = [r for r in self.results if r.scenario_id == scenario_id and r.model == model]
                if rs:
                    row += f"{rs[0].latency_ms:<22.0f}"
                else:
                    row += f"{'N/A':<22}"
            lines.append(row)

        lines.append("\n" + "=" * 80)
        return "\n".join(lines)

    def to_json(self) -> dict:
        return {"results": [asdict(r) for r in self.results]}


# ── Pricing estimations (mayo 2026) ──────────────────────────────────────────

# Precios aproximados en USD por millón de tokens (input / output)
PRICING = {
    "claude-haiku-4-5-20251001":  {"input": 0.80,  "output": 4.00,  "cache_read": 0.08},
    "claude-sonnet-4-6":          {"input": 3.00,  "output": 15.00, "cache_read": 0.30},
    "claude-opus-4-7":            {"input": 15.00, "output": 75.00, "cache_read": 1.50},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_read: int) -> float:
    p = PRICING.get(model, {"input": 3.0, "output": 15.0, "cache_read": 0.3})
    regular_input = max(0, input_tokens - cache_read)
    cost = (
        regular_input * p["input"] / 1_000_000
        + cache_read * p["cache_read"] / 1_000_000
        + output_tokens * p["output"] / 1_000_000
    )
    return cost


# ── Runner ────────────────────────────────────────────────────────────────────

def _run_risk_scenario(scenario: dict, model: str, llm_module) -> ScenarioResult:
    prompt = (
        f"Producto: {scenario['product']} (categoría: {scenario['category']}). "
        f"Días hasta caducidad: {scenario['days_left']}. "
        f"Cantidad: {scenario['quantity']} unidades. "
        f"Precio venta: {scenario['price']} euros. "
        f"Determina el nivel de riesgo (CRÍTICO/ALTO/MEDIO/BAJO) y la acción recomendada."
    )

    t0 = time.monotonic()
    try:
        client = llm_module.get_client()
        from backend.core.llm import _cached_system, _extract_text
        resp = client.messages.create(
            model=model,
            max_tokens=256,
            system=_cached_system(),
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - t0) * 1000
        text = _extract_text(resp)
        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        # Check correctness
        text_lower = text.lower()
        correct = (
            scenario["expected_risk"].lower() in text_lower
            or scenario["expected_action_keyword"].lower() in text_lower
        )

        return ScenarioResult(
            scenario_id=scenario["id"],
            model=model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            success=True,
            correct=correct,
            output_preview=text[:200],
            cost_usd=_estimate_cost(model, input_tokens, output_tokens, cache_read),
        )
    except Exception as e:
        latency_ms = (time.monotonic() - t0) * 1000
        return ScenarioResult(
            scenario_id=scenario["id"],
            model=model,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            success=False,
            correct=False,
            output_preview="",
            error=str(e)[:200],
        )


def _run_structured_scenario(model: str, llm_module) -> ScenarioResult:
    scenario = RISK_SCENARIOS[0]  # carne 1 día
    prompt = (
        f"Producto: {scenario['product']}. Días: {scenario['days_left']}. "
        f"Categoría: {scenario['category']}. Devuelve la evaluación estructurada."
    )

    t0 = time.monotonic()
    try:
        from backend.core.llm import _cached_system
        tool = {
            "name": "structured_output",
            "description": "Devuelve la evaluación estructurada del producto.",
            "input_schema": STRUCTURED_SCHEMA,
        }
        # Force correct model
        client = llm_module.get_client()
        resp = client.messages.create(
            model=model,
            max_tokens=256,
            system=_cached_system(),
            tools=[tool],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - t0) * 1000
        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        result_data = {}
        for block in resp.content:
            if block.type == "tool_use" and block.name == "structured_output":
                result_data = block.input
                break

        correct = (
            result_data.get("risk_level") == "CRÍTICO"
            and result_data.get("action") in ("retirar", "donar")
            and isinstance(result_data.get("discount_pct"), int)
        )

        return ScenarioResult(
            scenario_id="structured_output",
            model=model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            success=bool(result_data),
            correct=correct,
            output_preview=json.dumps(result_data, ensure_ascii=False)[:200],
            cost_usd=_estimate_cost(model, input_tokens, output_tokens, cache_read),
        )
    except Exception as e:
        latency_ms = (time.monotonic() - t0) * 1000
        return ScenarioResult(
            scenario_id="structured_output",
            model=model,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            success=False,
            correct=False,
            output_preview="",
            error=str(e)[:200],
        )


def run_benchmark(scenarios: list[str] | None = None) -> BenchmarkSuite:
    """Ejecuta el benchmark completo o solo los escenarios especificados."""
    from backend.core import llm as llm_module

    models = [llm_module.MODEL_FAST, llm_module.MODEL, llm_module.MODEL_DEEP]
    suite = BenchmarkSuite()

    run_risk = scenarios is None or "riesgo" in scenarios
    run_structured = scenarios is None or "estructurado" in scenarios

    print("MermaOps Benchmark — iniciando...")
    print(f"Modelos: {models}")
    print(f"Escenarios de riesgo: {len(RISK_SCENARIOS)}")

    if run_risk:
        print("\n[1/2] Escenarios de evaluación de riesgo...")
        for scenario in RISK_SCENARIOS:
            for model in models:
                print(f"  {scenario['id']} / {model[:30]}... ", end="", flush=True)
                result = _run_risk_scenario(scenario, model, llm_module)
                suite.add(result)
                status = "OK" if result.success and result.correct else ("FAIL" if not result.success else "PARCIAL")
                print(f"{status} ({result.latency_ms:.0f}ms, ${result.cost_usd:.5f})")

    if run_structured:
        print("\n[2/2] Extracción de salida estructurada...")
        for model in models:
            print(f"  structured_output / {model[:30]}... ", end="", flush=True)
            result = _run_structured_scenario(model, llm_module)
            suite.add(result)
            status = "OK" if result.success and result.correct else ("FAIL" if not result.success else "PARCIAL")
            print(f"{status} ({result.latency_ms:.0f}ms)")

    return suite


def main() -> None:
    parser = argparse.ArgumentParser(description="MermaOps LLM Benchmark")
    parser.add_argument(
        "--scenario",
        choices=["riesgo", "estructurado"],
        help="Ejecutar solo un escenario específico",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Guardar resultados en JSON (ej: benchmark_results.json)",
    )
    args = parser.parse_args()

    scenarios = [args.scenario] if args.scenario else None
    suite = run_benchmark(scenarios)

    print(suite.summary_table())

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(suite.to_json(), f, ensure_ascii=False, indent=2)
        print(f"\nResultados guardados en: {args.output}")


if __name__ == "__main__":
    main()
