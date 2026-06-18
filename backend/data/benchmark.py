"""
MermaOps Benchmark — Evaluación empírica de modelos para el TFM.

Compara Haiku vs Sonnet vs Opus en los escenarios clave del sistema:
  1. Evaluación de riesgo de producto (¿cuánto tarda? ¿acierta el nivel?)
  2. Generación de texto del brief diario (¿calidad? ¿longitud óptima?)
  3. Extracción de salida estructurada (¿fiabilidad del esquema?)
  4. Robustez multilingüe (¿responde en español ante prompt en inglés?)
  5. Caso adversarial (¿resiste sobre-predicción de riesgo en productos seguros?)

Genera tablas comparativas listas para incluir en el TFM.
Uso:
    python -m backend.data.benchmark
    python -m backend.data.benchmark --scenario riesgo
    python -m backend.data.benchmark --scenario brief
    python -m backend.data.benchmark --scenario multilingue
    python -m backend.data.benchmark --scenario adversarial
    python -m backend.data.benchmark --parallel
    python -m backend.data.benchmark --output resultados_benchmark.json
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import date
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

# Prompt en inglés para el escenario multilingüe
MULTILINGUAL_PROMPT = (
    "Product: Fresh chicken 500g, category: carne, 1 day until expiry, "
    "quantity 10, price 5.50€. Assess risk."
)

# Producto seguro para probar resistencia a sobre-predicción
ADVERSARIAL_PROMPT = (
    "Producto: Agua embotellada, días: 365, cantidad: 1000, precio: 0.50€. "
    "Nivel de riesgo?"
)

# Versión del benchmark
BENCHMARK_VERSION = "2.0.0"


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
            correct_count = sum(1 for r in model_results if r.correct)
            correct_rate = correct_count / len(model_results) * 100
            avg_latency = statistics.mean(r.latency_ms for r in model_results)
            median_latency = statistics.median(r.latency_ms for r in model_results)
            avg_input = statistics.mean(r.input_tokens for r in model_results)
            avg_output = statistics.mean(r.output_tokens for r in model_results)
            total_cost = sum(r.cost_usd for r in model_results)
            total_tokens = sum(r.input_tokens + r.output_tokens for r in model_results)
            cache_pct = (
                sum(r.cache_read_tokens for r in model_results)
                / max(sum(r.input_tokens for r in model_results), 1)
                * 100
            )

            # p95 latency using statistics.quantiles (n=20 → index 18 = 95th percentile)
            latencies = [r.latency_ms for r in model_results]
            if len(latencies) >= 2:
                p95_latency = statistics.quantiles(latencies, n=20)[18]
            else:
                p95_latency = latencies[0]

            # tokens_per_correct
            tokens_per_correct = total_tokens / max(1, correct_count)

            lines.append(f"\n{'─' * 40}")
            lines.append(f"Modelo: {model}")
            lines.append(f"{'─' * 40}")
            lines.append(f"  Escenarios ejecutados : {len(model_results)}")
            lines.append(f"  Tasa de éxito          : {success_rate:.0f}%")
            lines.append(f"  Precisión (correcto)   : {correct_rate:.0f}%")
            lines.append(f"  Latencia media         : {avg_latency:.0f} ms")
            lines.append(f"  Latencia mediana       : {median_latency:.0f} ms")
            lines.append(f"  Latencia p95           : {p95_latency:.0f} ms")
            lines.append(f"  Tokens entrada (media) : {avg_input:.0f}")
            lines.append(f"  Tokens salida (media)  : {avg_output:.0f}")
            lines.append(f"  Cache hit rate         : {cache_pct:.0f}%")
            lines.append(f"  Tokens por acierto     : {tokens_per_correct:.0f}")
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
        total_cost = sum(r.cost_usd for r in self.results)
        scenario_ids = sorted({r.scenario_id for r in self.results})
        return {
            "benchmark_version": BENCHMARK_VERSION,
            "run_date": date.today().isoformat(),
            "total_cost_usd": round(total_cost, 6),
            "total_scenarios": len(scenario_ids),
            "results": [asdict(r) for r in self.results],
        }


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


# ── Runner helpers ────────────────────────────────────────────────────────────

def _call_model(client, model: str, prompt: str, max_tokens: int = 256, system=None) -> tuple:
    """Shared helper: returns (text, input_tokens, output_tokens, cache_read, latency_ms)."""
    from backend.core.llm import _cached_system, _extract_text
    sys_prompt = system if system is not None else _cached_system()
    t0 = time.monotonic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=sys_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = (time.monotonic() - t0) * 1000
    text = _extract_text(resp)
    usage = getattr(resp, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    return text, input_tokens, output_tokens, cache_read, latency_ms


def _make_error_result(scenario_id: str, model: str, latency_ms: float, error: str) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        model=model,
        latency_ms=latency_ms,
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        success=False,
        correct=False,
        output_preview="",
        error=error[:200],
    )


# ── Scenario runners ──────────────────────────────────────────────────────────

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
        text, input_tokens, output_tokens, cache_read, latency_ms = _call_model(client, model, prompt)

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
        return _make_error_result(scenario["id"], model, latency_ms, str(e))


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
        return _make_error_result("structured_output", model, latency_ms, str(e))


def _run_brief_quality_scenario(model: str, llm_module) -> ScenarioResult:
    """
    Genera un párrafo de brief diario y puntúa la calidad de la salida.
    Criterios (1 punto cada uno, correcto si score >= 3/5):
      1. Longitud entre 100 y 250 palabras
      2. Menciona nombres de productos concretos del escenario
      3. Contiene verbos de acción (rebaja, retira, dona)
      4. No contiene asteriscos ni símbolos markdown (* # **)
      5. Menciona el valor en riesgo (187 o 187.50)
    """
    sc = BRIEF_SCENARIO
    actions_text = "\n".join(f"- {a}" for a in sc["top_actions"])
    route_text = ", ".join(sc["route"])
    prompt = (
        f"Genera un brief diario en español para la tienda {sc['store']}. "
        f"Fecha: {sc['date']}. "
        f"Productos críticos: {sc['critical_count']}. Productos en alto riesgo: {sc['high_count']}. "
        f"Valor en riesgo: {sc['value_at_risk']}€. "
        f"Ruta prioritaria: {route_text}. "
        f"Acciones recomendadas:\n{actions_text}\n"
        f"Escribe un párrafo resumen claro y directo para el encargado de turno. "
        f"Sin markdown, sin asteriscos, sin bullets. Solo texto."
    )

    t0 = time.monotonic()
    try:
        client = llm_module.get_client()
        text, input_tokens, output_tokens, cache_read, latency_ms = _call_model(
            client, model, prompt, max_tokens=512
        )

        # Scoring
        word_count = len(text.split())
        text_lower = text.lower()

        score = 0

        # Criterio 1: longitud 100–250 palabras
        if 100 <= word_count <= 250:
            score += 1

        # Criterio 2: menciona nombres de productos concretos
        product_names = ["baguette", "nata", "merluza"]
        if any(p in text_lower for p in product_names):
            score += 1

        # Criterio 3: contiene verbos de acción operativos
        action_verbs = ["rebaja", "retira", "dona", "retirar", "rebajar", "donar"]
        if any(v in text_lower for v in action_verbs):
            score += 1

        # Criterio 4: sin asteriscos ni markdown
        if "*" not in text and "#" not in text and "**" not in text:
            score += 1

        # Criterio 5: menciona el valor en riesgo
        if "187" in text:
            score += 1

        correct = score >= 3

        preview = f"[score={score}/5, words={word_count}] {text[:150]}"

        return ScenarioResult(
            scenario_id="brief_quality",
            model=model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            success=True,
            correct=correct,
            output_preview=preview,
            cost_usd=_estimate_cost(model, input_tokens, output_tokens, cache_read),
        )
    except Exception as e:
        latency_ms = (time.monotonic() - t0) * 1000
        return _make_error_result("brief_quality", model, latency_ms, str(e))


def _run_multilingual_scenario(model: str, llm_module) -> ScenarioResult:
    """
    Envía el prompt de riesgo en inglés y verifica que el modelo:
      - Responde en español, O
      - Identifica correctamente el nivel CRÍTICO / HIGH risk.
    """
    t0 = time.monotonic()
    try:
        client = llm_module.get_client()
        text, input_tokens, output_tokens, cache_read, latency_ms = _call_model(
            client, model, MULTILINGUAL_PROMPT, max_tokens=256
        )

        text_lower = text.lower()

        # Correcto si detecta alto riesgo (en cualquier idioma) O responde en español
        risk_keywords_es = ["crítico", "critico", "alto riesgo", "retirar", "urgente"]
        risk_keywords_en = ["critical", "high risk", "remove", "urgent"]
        spanish_indicators = ["el ", "la ", "un ", "una ", "que ", "los ", "las ", "con ", "para "]

        detected_risk = any(k in text_lower for k in risk_keywords_es + risk_keywords_en)
        responds_in_spanish = sum(1 for ind in spanish_indicators if ind in text_lower) >= 3

        correct = detected_risk or responds_in_spanish

        preview = f"[es={responds_in_spanish}, risk={detected_risk}] {text[:150]}"

        return ScenarioResult(
            scenario_id="multilingual_robustness",
            model=model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            success=True,
            correct=correct,
            output_preview=preview,
            cost_usd=_estimate_cost(model, input_tokens, output_tokens, cache_read),
        )
    except Exception as e:
        latency_ms = (time.monotonic() - t0) * 1000
        return _make_error_result("multilingual_robustness", model, latency_ms, str(e))


def _run_adversarial_scenario(model: str, llm_module) -> ScenarioResult:
    """
    Envía un producto claramente seguro (agua, 365 días, cantidad alta).
    Correcto si el modelo NO sobre-predice: responde BAJO o monitorizar.
    Incorrecto si dice CRÍTICO o ALTO para agua embotellada con 365 días.
    """
    t0 = time.monotonic()
    try:
        client = llm_module.get_client()
        text, input_tokens, output_tokens, cache_read, latency_ms = _call_model(
            client, model, ADVERSARIAL_PROMPT, max_tokens=256
        )

        text_lower = text.lower()

        # El modelo falla si dice crítico o alto para agua con 365 días
        over_predicted = any(k in text_lower for k in ["crítico", "critico", "alto"])
        # Correcto si dice bajo o monitorizar
        correct_answer = any(k in text_lower for k in ["bajo", "monitorizar", "sin riesgo", "seguro", "no hay riesgo"])

        correct = correct_answer and not over_predicted

        preview = f"[over_pred={over_predicted}, correct_kw={correct_answer}] {text[:150]}"

        return ScenarioResult(
            scenario_id="adversarial_edge_case",
            model=model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            success=True,
            correct=correct,
            output_preview=preview,
            cost_usd=_estimate_cost(model, input_tokens, output_tokens, cache_read),
        )
    except Exception as e:
        latency_ms = (time.monotonic() - t0) * 1000
        return _make_error_result("adversarial_edge_case", model, latency_ms, str(e))


# ── Main orchestration ────────────────────────────────────────────────────────

def _build_combos(models: list[str], scenarios: list[str] | None, llm_module) -> list[tuple[Callable, tuple]]:
    """
    Returns a flat list of (runner_fn, args) tuples for all selected
    (scenario, model) combinations.
    """
    combos: list[tuple[Callable, tuple]] = []

    run_risk = scenarios is None or "riesgo" in scenarios
    run_structured = scenarios is None or "estructurado" in scenarios
    run_brief = scenarios is None or "brief" in scenarios
    run_multilingual = scenarios is None or "multilingue" in scenarios
    run_adversarial = scenarios is None or "adversarial" in scenarios

    if run_risk:
        for scenario in RISK_SCENARIOS:
            for model in models:
                combos.append((_run_risk_scenario, (scenario, model, llm_module)))

    if run_structured:
        for model in models:
            combos.append((_run_structured_scenario, (model, llm_module)))

    if run_brief:
        for model in models:
            combos.append((_run_brief_quality_scenario, (model, llm_module)))

    if run_multilingual:
        for model in models:
            combos.append((_run_multilingual_scenario, (model, llm_module)))

    if run_adversarial:
        for model in models:
            combos.append((_run_adversarial_scenario, (model, llm_module)))

    return combos


def run_benchmark(
    scenarios: list[str] | None = None,
    parallel: bool = False,
) -> BenchmarkSuite:
    """Ejecuta el benchmark completo o solo los escenarios especificados."""
    from backend.core import llm as llm_module

    models = [llm_module.MODEL_FAST, llm_module.MODEL, llm_module.MODEL_DEEP]
    suite = BenchmarkSuite()

    print("MermaOps Benchmark — iniciando...")
    print(f"Modelos: {models}")
    print(f"Escenarios de riesgo: {len(RISK_SCENARIOS)}")
    if parallel:
        print("Modo: paralelo (ThreadPoolExecutor, max_workers=6)")
    else:
        print("Modo: secuencial")

    combos = _build_combos(models, scenarios, llm_module)
    print(f"Total combinaciones: {len(combos)}\n")

    if parallel:
        results: list[ScenarioResult] = []

        def _run_one(item: tuple) -> ScenarioResult:
            fn, args = item
            return fn(*args)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(_run_one, item): item for item in combos}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
                status = (
                    "OK"
                    if result.success and result.correct
                    else ("FAIL" if not result.success else "PARCIAL")
                )
                print(
                    f"  {result.scenario_id} / {result.model[:30]}... "
                    f"{status} ({result.latency_ms:.0f}ms, ${result.cost_usd:.5f})"
                )

        # Sort results for stable output
        results.sort(key=lambda r: (r.scenario_id, r.model))
        for r in results:
            suite.add(r)

    else:
        # Sequential execution with section headers
        scenario_type_labels = {
            "riesgo": ("[1/5] Escenarios de evaluación de riesgo...", "riesgo"),
            "estructurado": ("[2/5] Extracción de salida estructurada...", "estructurado"),
            "brief": ("[3/5] Calidad del brief diario...", "brief"),
            "multilingue": ("[4/5] Robustez multilingüe...", "multilingue"),
            "adversarial": ("[5/5] Caso adversarial (resistencia a sobre-predicción)...", "adversarial"),
        }
        run_flags = {
            "riesgo": scenarios is None or "riesgo" in (scenarios or []),
            "estructurado": scenarios is None or "estructurado" in (scenarios or []),
            "brief": scenarios is None or "brief" in (scenarios or []),
            "multilingue": scenarios is None or "multilingue" in (scenarios or []),
            "adversarial": scenarios is None or "adversarial" in (scenarios or []),
        }

        if run_flags["riesgo"]:
            print("[1/5] Escenarios de evaluación de riesgo...")
            for scenario in RISK_SCENARIOS:
                for model in models:
                    print(f"  {scenario['id']} / {model[:30]}... ", end="", flush=True)
                    result = _run_risk_scenario(scenario, model, llm_module)
                    suite.add(result)
                    status = "OK" if result.success and result.correct else ("FAIL" if not result.success else "PARCIAL")
                    print(f"{status} ({result.latency_ms:.0f}ms, ${result.cost_usd:.5f})")

        if run_flags["estructurado"]:
            print("\n[2/5] Extracción de salida estructurada...")
            for model in models:
                print(f"  structured_output / {model[:30]}... ", end="", flush=True)
                result = _run_structured_scenario(model, llm_module)
                suite.add(result)
                status = "OK" if result.success and result.correct else ("FAIL" if not result.success else "PARCIAL")
                print(f"{status} ({result.latency_ms:.0f}ms, ${result.cost_usd:.5f})")

        if run_flags["brief"]:
            print("\n[3/5] Calidad del brief diario...")
            for model in models:
                print(f"  brief_quality / {model[:30]}... ", end="", flush=True)
                result = _run_brief_quality_scenario(model, llm_module)
                suite.add(result)
                status = "OK" if result.success and result.correct else ("FAIL" if not result.success else "PARCIAL")
                print(f"{status} ({result.latency_ms:.0f}ms, ${result.cost_usd:.5f})")

        if run_flags["multilingue"]:
            print("\n[4/5] Robustez multilingüe...")
            for model in models:
                print(f"  multilingual_robustness / {model[:30]}... ", end="", flush=True)
                result = _run_multilingual_scenario(model, llm_module)
                suite.add(result)
                status = "OK" if result.success and result.correct else ("FAIL" if not result.success else "PARCIAL")
                print(f"{status} ({result.latency_ms:.0f}ms, ${result.cost_usd:.5f})")

        if run_flags["adversarial"]:
            print("\n[5/5] Caso adversarial...")
            for model in models:
                print(f"  adversarial_edge_case / {model[:30]}... ", end="", flush=True)
                result = _run_adversarial_scenario(model, llm_module)
                suite.add(result)
                status = "OK" if result.success and result.correct else ("FAIL" if not result.success else "PARCIAL")
                print(f"{status} ({result.latency_ms:.0f}ms, ${result.cost_usd:.5f})")

    return suite


def main() -> None:
    parser = argparse.ArgumentParser(description="MermaOps LLM Benchmark")
    parser.add_argument(
        "--scenario",
        choices=["riesgo", "estructurado", "brief", "multilingue", "adversarial"],
        help="Ejecutar solo un escenario específico",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Guardar resultados en JSON (ej: benchmark_results.json)",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Ejecutar todos los combos en paralelo (ThreadPoolExecutor, max_workers=6)",
    )
    args = parser.parse_args()

    scenarios = [args.scenario] if args.scenario else None
    suite = run_benchmark(scenarios=scenarios, parallel=args.parallel)

    print(suite.summary_table())

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(suite.to_json(), f, ensure_ascii=False, indent=2)
        print(f"\nResultados guardados en: {args.output}")


if __name__ == "__main__":
    main()
