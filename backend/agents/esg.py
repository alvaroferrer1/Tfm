"""
ESG Agent — cuantifica el impacto ambiental de la gestión de merma.

Métricas calculadas por cada acción completada de rebajar/donar:
  - kg CO2eq evitados (huella de carbono del alimento no desperdiciado)
  - Litros de agua ahorrados (huella hídrica)
  - Equivalencia comprensible (km en coche, días de ducha, etc.)

Fuentes de datos:
  - CO2: Poore & Nemecek 2018 (Science), actualizado FAO 2023
  - Agua: Mekonnen & Hoekstra 2011 (UNESCO-IHE)
  - Peso por unidad: estimaciones estándar de packaging español

Relevancia TFM:
  - Directiva Ómnibus I (UE 2026/470, en vigor marzo 2026): eleva el umbral CSRD a
    >1.000 empleados Y >450M€ de facturación — las PYMEs quedan exentas legalmente.
    Sin embargo, sus clientes grandes SÍ reportan y pedirán datos ESG a proveedores.
    Además, los bancos exigen métricas de sostenibilidad para líneas de crédito verde.
  - Deducción fiscal por donaciones alimentarias: 35% (Ley 49/2002, art. 19)
  - Contexto estadístico: el sector retail genera el 8% del total de residuos
    alimentarios de la UE (≈10 kg/habitante/año) — Eurostat 2024.
    Frutas (27%), verduras (20%) y cereales (13%) son los más desperdiciados.
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from backend.core import database, llm

logger = logging.getLogger("mermaops.esg")

# kg CO2eq por kg de alimento (Poore & Nemecek 2018, FAO 2023)
_CO2_PER_KG: dict[str, float] = {
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
    "congelados": 2.0,
    "embutidos": 8.5,
    "aceite": 3.8,
    "conservas": 1.5,
    "default": 2.5,
}

# Litros de agua por kg de alimento (Mekonnen & Hoekstra, UNESCO-IHE)
_WATER_PER_KG: dict[str, float] = {
    "carne": 15415.0,
    "carne_ternera": 15415.0,
    "carne_cerdo": 5988.0,
    "carne_pollo": 4325.0,
    "carne_cordero": 10412.0,
    "pescado": 2500.0,
    "marisco": 3700.0,
    "lacteos": 1020.0,
    "queso": 3178.0,
    "huevos": 3265.0,
    "panaderia": 1608.0,
    "fruta": 962.0,
    "verdura": 322.0,
    "legumbres": 4055.0,
    "bebidas": 300.0,
    "congelados": 2000.0,
    "embutidos": 6000.0,
    "aceite": 6000.0,
    "conservas": 1200.0,
    "default": 2000.0,
}

# Peso medio en kg por unidad vendida según categoría (packaging España)
_WEIGHT_PER_UNIT: dict[str, float] = {
    "carne": 0.45,
    "pescado": 0.40,
    "marisco": 0.35,
    "lacteos": 1.00,
    "queso": 0.25,
    "huevos": 0.60,   # docena
    "panaderia": 0.30,
    "bolleria": 0.20,
    "fruta": 0.30,
    "verdura": 0.40,
    "legumbres": 0.50,
    "bebidas": 1.00,
    "congelados": 0.45,
    "embutidos": 0.20,
    "conservas": 0.40,
    "aceite": 1.00,
    "default": 0.30,
}


def _normalize_category(category: str) -> str:
    return (category or "").lower().strip().replace(" ", "_")


def _get_factors(category: str) -> tuple[float, float, float]:
    """Returns (co2_per_kg, water_per_kg, weight_per_unit)."""
    cat = _normalize_category(category)
    co2 = _CO2_PER_KG.get(cat, _CO2_PER_KG["default"])
    water = _WATER_PER_KG.get(cat, _WATER_PER_KG["default"])
    weight = _WEIGHT_PER_UNIT.get(cat, _WEIGHT_PER_UNIT["default"])
    return co2, water, weight


def compute_action_impact(quantity: int, category: str, price: float = 0.0) -> dict:
    """
    Calcula el impacto ESG de salvar N unidades de un producto.
    Usado al completar una acción de rebajar o donar.
    """
    co2_factor, water_factor, weight = _get_factors(category)
    total_kg = quantity * weight
    co2_saved = round(total_kg * co2_factor, 3)
    water_saved = round(total_kg * water_factor, 1)
    value_saved = round(quantity * price, 2) if price else 0.0

    # Equivalencias comprensibles
    km_car = round(co2_saved / 0.21, 1)     # 0.21 kg CO2/km media coche español (DGT 2023)
    shower_days = round(water_saved / 65, 1)  # 65L por ducha media España (AEAS 2023)

    return {
        "units_saved": quantity,
        "total_kg": round(total_kg, 2),
        "co2_saved_kg": co2_saved,
        "water_saved_liters": water_saved,
        "value_saved_eur": value_saved,
        "equivalences": {
            "km_car_avoided": km_car,
            "shower_days_equivalent": shower_days,
        },
        "category": category,
    }


def get_store_esg_summary(store_id: str, days: int = 30) -> dict:
    """
    Calcula el resumen ESG de la tienda para el período dado.
    Usa las acciones completadas de rebajar/donar como base de cálculo.
    """
    try:
        roi = database.get_completed_actions_value(store_id, days=days)
        completed_actions = roi.get("actions_completed", 0)
        value_recovered = roi.get("value_recovered", 0.0)
    except Exception as e:
        logger.error(f"[esg] Error obteniendo acciones: {e}")
        completed_actions = 0
        value_recovered = 0.0

    # Merma real (lo que se perdió)
    try:
        merma = database.get_merma_history(store_id, days=days)
        def _merma_category(r: dict) -> str:
            products = (r.get("batches") or {}).get("products") or {}
            return (products.get("category") or "default")

        merma_kg = sum(
            int(r.get("quantity_lost", 0)) *
            _WEIGHT_PER_UNIT.get(_normalize_category(_merma_category(r)), _WEIGHT_PER_UNIT["default"])
            for r in merma
        )
        merma_co2 = sum(
            int(r.get("quantity_lost", 0)) *
            _WEIGHT_PER_UNIT.get(_normalize_category(_merma_category(r)), _WEIGHT_PER_UNIT["default"]) *
            _CO2_PER_KG.get(_normalize_category(_merma_category(r)), _CO2_PER_KG["default"])
            for r in merma
        )
    except Exception:
        merma_kg = 0.0
        merma_co2 = 0.0

    # Donaciones
    try:
        donations = database.get_donation_stats(store_id, days=days)
        donated_value = donations.get("total_value_donated", 0.0)
        donated_qty = donations.get("total_quantity", 0)
    except Exception:
        donated_value = 0.0
        donated_qty = 0

    # Estimación CO2 evitado desde acciones completadas
    # Asumimos 2.5 kg CO2/kg (promedio) y 0.3 kg/unidad (promedio)
    estimated_units_saved = max(completed_actions * 5, donated_qty)  # estimación conservadora
    estimated_kg_saved = estimated_units_saved * 0.3
    co2_avoided = round(estimated_kg_saved * 2.5, 1)
    water_avoided = round(estimated_kg_saved * 2000, 0)

    km_car = round(co2_avoided / 0.21, 1)
    shower_days = round(water_avoided / 65, 1)

    # Deducción fiscal estimada (Ley 49/2002: 35% sobre valor donado)
    tax_deduction_estimate = round(donated_value * 0.35, 2)

    return {
        "period_days": days,
        "actions_completed": completed_actions,
        "value_recovered_eur": round(value_recovered, 2),
        "merma_actual_kg": round(merma_kg, 1),
        "merma_actual_co2_kg": round(merma_co2, 1),
        "estimated_co2_avoided_kg": co2_avoided,
        "estimated_water_avoided_liters": water_avoided,
        "donated_value_eur": round(donated_value, 2),
        "donated_units": donated_qty,
        "tax_deduction_estimate_eur": tax_deduction_estimate,
        "equivalences": {
            "km_car_avoided": km_car,
            "shower_days_equivalent": shower_days,
        },
        "esg_score": _compute_esg_score(co2_avoided, merma_kg, completed_actions, donated_value),
    }


def _compute_esg_score(co2_avoided: float, merma_kg: float, actions: int, donations: float) -> int:
    """
    Puntuación ESG 0-100 propia de MermaOps.
    No es una certificación — es un KPI interno orientativo.
    """
    score = 0
    # CO2 evitado (hasta 30 puntos)
    score += min(30, int(co2_avoided / 2))
    # Ratio merma gestionada (hasta 30 puntos)
    if merma_kg > 0:
        score += min(30, int(30 * (1 - min(merma_kg / 100, 1))))
    else:
        score += 30
    # Acciones completadas (hasta 25 puntos)
    score += min(25, actions)
    # Donaciones (hasta 15 puntos)
    score += min(15, int(donations / 10))
    return min(100, score)


def generate_esg_report(store_id: str, days: int = 30) -> str:
    """Genera un informe ESG en texto para el dueño / encargado."""
    summary = get_store_esg_summary(store_id, days=days)

    prompt = f"""Genera un informe ESG (impacto ambiental y social) para el Súper Martínez.

DATOS DEL PERIODO ({days} días):
- Acciones de gestión completadas: {summary['actions_completed']}
- Valor económico recuperado: {summary['value_recovered_eur']:.2f} euros
- CO2 evitado estimado: {summary['estimated_co2_avoided_kg']} kg CO2eq
- Agua ahorrada estimada: {summary['estimated_water_avoided_liters']:.0f} litros
- Merma real generada: {summary['merma_actual_kg']} kg ({summary['merma_actual_co2_kg']:.1f} kg CO2)
- Donaciones realizadas: {summary['donated_units']} uds — {summary['donated_value_eur']:.2f} euros
- Deducción fiscal estimada: {summary['tax_deduction_estimate_eur']:.2f} euros (Ley 49/2002, 35%)
- Equivalencias: {summary['equivalences']['km_car_avoided']} km en coche evitados, {summary['equivalences']['shower_days_equivalent']} días de ducha ahorrados
- Puntuación ESG MermaOps: {summary['esg_score']}/100

El informe debe:
1. Resumir el impacto ambiental en lenguaje que entienda el dueño de una PYME (no técnico)
2. Destacar el ahorro fiscal por donaciones (Ley 49/2002, 35%)
3. Mencionar que aunque la Directiva Ómnibus I (marzo 2026) exime a PYMEs del CSRD obligatorio,
   sus proveedores y clientes grandes SÍ pedirán datos ESG — tenerlos listos es ventaja competitiva.
   Además los bancos exigen métricas de sostenibilidad para préstamos verdes.
4. Dar 2 recomendaciones concretas para mejorar la puntuación ESG el próximo mes
5. Ser breve: máximo 300 palabras. Sin asteriscos."""

    return llm.call(
        prompt,
        system_extra=(
            "Eres el consultor de sostenibilidad del Súper Martínez. "
            "Hablas claro, sin tecnicismos innecesarios. "
            "Tu objetivo es que el dueño entienda el impacto real de sus decisiones "
            "y cómo MermaOps le ayuda a ser más sostenible y ahorrar dinero a la vez."
        ),
        max_tokens=600,
    )
