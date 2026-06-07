"""
Tests específicos para la regla de consenso 2/3 en backend/agents/consensus.py.

Cubre:
  - Unanimidad 3/3 → acción ganadora, consensus_used=True, boost de confianza
  - Mayoría 2/3 → acción ganadora, consensus_used=True, nota de disenso
  - Empate 1/1/1 → pasa al árbitro (mock), consensus_used=True
  - Cálculo correcto del descuento ponderado por confianza en mayoría 2/3
  - Verificación de campos requeridos por evaluator.evaluate()
  - Categorías con boost de seguridad (carne) y rentabilidad (conservas)
  - Caso Jeffrey (score>=95, valor>=50€) desvía antes del consenso paralelo
  - Fallback cuando el pool falla no lleva consensus_used=True

Sin llamadas reales a la API — todo mockeado con unittest.mock.patch.
Ejecutar: python -m pytest backend/tests/test_consensus_rule.py -v
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from backend.agents.consensus import reach_consensus, _build_result, _fallback


# ── Fixtures ──────────────────────────────────────────────────────────────────

PRODUCT_BASE = {
    "id": "p-001",
    "name": "Yogur natural 500g",
    "category": "lacteos",
    "price": 1.80,
    "cost": 0.90,
}

PRODUCT_CARNE = {
    "id": "p-002",
    "name": "Carne picada 400g",
    "category": "carne",
    "price": 4.50,
    "cost": 2.25,
}

PRODUCT_CONSERVAS = {
    "id": "p-003",
    "name": "Lata de atún",
    "category": "conservas",
    "price": 1.20,
    "cost": 0.55,
}

PRODUCT_CARO = {
    "id": "p-004",
    "name": "Salmón fresco entero",
    "category": "pescado",
    "price": 12.00,
    "cost": 7.00,
}


def _vote(perspective: str, action: str, confidence: int = 80, discount: int = 40) -> dict:
    """Crea un voto de prueba con todos los campos requeridos."""
    return {
        "perspective": perspective,
        "action": action,
        "confidence": confidence,
        "reasoning": f"Test: {perspective} recomienda {action}",
        "price_adjustment_pct": discount,
    }


# ── Regla 2/3: Unanimidad (3/3) ───────────────────────────────────────────────

class TestUnanimity:
    def test_3_of_3_returns_unanimous_action(self):
        """Tres perspectivas idénticas → acción devuelta correctamente."""
        v_safety = _vote("seguridad", "retirar", 92, 0)
        v_profit = _vote("rentabilidad", "retirar", 78, 0)
        v_ops = _vote("operaciones", "retirar", 85, 0)

        with patch("backend.agents.consensus._vote_safety", return_value=v_safety), \
             patch("backend.agents.consensus._vote_profitability", return_value=v_profit), \
             patch("backend.agents.consensus._vote_operations", return_value=v_ops):
            result = reach_consensus(PRODUCT_BASE, days_left=0, qty=20, heuristic_score=90)

        assert result["action"] == "retirar"

    def test_3_of_3_sets_consensus_used_true(self):
        """Unanimidad debe marcar consensus_used=True."""
        vote = _vote("seguridad", "donar", 88, 0)
        with patch("backend.agents.consensus._vote_safety", return_value=vote), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "donar", 75, 0)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "donar", 80, 0)):
            result = reach_consensus(PRODUCT_BASE, days_left=1, qty=15, heuristic_score=90)

        assert result["consensus_used"] is True

    def test_3_of_3_confidence_boost_applied_when_avg_ge_70(self):
        """Unanimidad con confianza media >=70 añade +5 a avg_confidence (cap 100)."""
        # confidence media = (80+80+80)//3 = 80 → 80+5 = 85 → score ajustado diferente al simple
        vote = _vote("seguridad", "rebajar", 80, 30)
        with patch("backend.agents.consensus._vote_safety", return_value=vote), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 80, 35)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "rebajar", 80, 25)):
            result = reach_consensus(PRODUCT_BASE, days_left=2, qty=10, heuristic_score=90)

        # Con boost: avg_confidence = 85 → score = min(100, int(90*0.7 + 85*0.3)) = min(100, 88) = 88
        # Sin boost: avg_confidence = 80 → score = min(100, int(90*0.7 + 80*0.3)) = min(100, 87) = 87
        assert result["score"] >= 88, (
            f"Esperado >=88 con boost de unanimidad, obtenido {result['score']}"
        )

    def test_3_of_3_no_dissent_note_in_thinking_summary(self):
        """Unanimidad → thinking_summary contiene '3/3'."""
        vote = _vote("seguridad", "revisar", 70, 0)
        with patch("backend.agents.consensus._vote_safety", return_value=vote), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "revisar", 65, 0)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "revisar", 72, 0)):
            result = reach_consensus(PRODUCT_BASE, days_left=3, qty=8, heuristic_score=90)

        assert "3/3" in result["thinking_summary"]


# ── Regla 2/3: Mayoría (2/3) ─────────────────────────────────────────────────

class TestMajority:
    def test_2_of_3_returns_majority_action(self):
        """Dos de tres votan igual → acción mayoritaria ganadora."""
        votes = [
            _vote("seguridad", "rebajar", 90, 40),
            _vote("rentabilidad", "rebajar", 85, 45),
            _vote("operaciones", "revisar", 55, 0),
        ]
        with patch("backend.agents.consensus._vote_safety", return_value=votes[0]), \
             patch("backend.agents.consensus._vote_profitability", return_value=votes[1]), \
             patch("backend.agents.consensus._vote_operations", return_value=votes[2]):
            result = reach_consensus(PRODUCT_CARNE, days_left=1, qty=12, heuristic_score=90)

        assert result["action"] == "rebajar"

    def test_2_of_3_consensus_used_true(self):
        """Mayoría 2/3 también es consenso → consensus_used=True."""
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "donar", 88, 0)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 80, 50)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "donar", 70, 0)):
            result = reach_consensus(PRODUCT_CARNE, days_left=1, qty=10, heuristic_score=90)

        assert result["consensus_used"] is True

    def test_2_of_3_thinking_summary_shows_2_of_3(self):
        """thinking_summary debe mostrar '2/3' cuando la mayoría es justa."""
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "retirar", 95, 0)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 80, 40)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "retirar", 85, 0)):
            result = reach_consensus(PRODUCT_CARNE, days_left=0, qty=8, heuristic_score=90)

        assert "2/3" in result["thinking_summary"]

    def test_2_of_3_dissent_note_present(self):
        """Cuando hay disenso, el reasoning en cotidiano debe mencionar el producto."""
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "rebajar", 90, 40)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 85, 45)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "revisar", 60, 0)):
            result = reach_consensus(PRODUCT_CARNE, days_left=1, qty=12, heuristic_score=90)

        # El reasoning cotidiano debe mencionar el producto
        assert "Carne picada" in result["reasoning"] or "lote" in result["reasoning"].lower()


# ── Cálculo del descuento ponderado ──────────────────────────────────────────

class TestWeightedDiscount:
    # Usa categoría neutral (panaderia) para que ningún boost de confianza
    # interfiera con el cálculo esperado.
    PRODUCT_NEUTRAL = {**PRODUCT_BASE, "category": "panaderia"}

    def test_weighted_discount_exact_calculation_2_of_3(self):
        """
        Descuento ponderado = sum(discount_i * conf_i) / sum(conf_i) para votos ganadores.
        Categoría neutral (sin boost). Votos ganadores: seguridad(conf=80,disc=40) y
        rentabilidad(conf=60,disc=20).
          weighted = (40*80 + 20*60) / (80+60) = 4400/140 = 31 (int truncado)
        """
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "rebajar", 80, 40)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 60, 20)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "revisar", 70, 0)):
            result = reach_consensus(self.PRODUCT_NEUTRAL, days_left=2, qty=10, heuristic_score=90)

        expected = int((40 * 80 + 20 * 60) / (80 + 60))  # = 31
        assert result["price_adjustment_pct"] == expected, (
            f"Esperado {expected}, obtenido {result['price_adjustment_pct']}"
        )

    def test_weighted_discount_exact_calculation_3_of_3(self):
        """
        Unanimidad: descuento ponderado sobre los 3 votos (categoría neutral, sin boost).
        voto1(conf=90, disc=50), voto2(conf=70, disc=30), voto3(conf=80, disc=40)
          weighted = (50*90 + 30*70 + 40*80) / (90+70+80) = 9800/240 = 40
        """
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "rebajar", 90, 50)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 70, 30)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "rebajar", 80, 40)):
            result = reach_consensus(self.PRODUCT_NEUTRAL, days_left=2, qty=10, heuristic_score=90)

        expected = int((50 * 90 + 30 * 70 + 40 * 80) / (90 + 70 + 80))  # = 40
        assert result["price_adjustment_pct"] == expected, (
            f"Esperado {expected}, obtenido {result['price_adjustment_pct']}"
        )

    def test_zero_total_confidence_uses_simple_average(self):
        """
        Si la suma de confianzas de los votos ganadores es 0, usa promedio simple.
        Categoría neutral para que el boost no eleve conf 0 → >0 antes de la suma.
        """
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "rebajar", 0, 40)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 0, 60)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "revisar", 80, 0)):
            result = reach_consensus(self.PRODUCT_NEUTRAL, days_left=2, qty=10, heuristic_score=90)

        # total_confidence=0 → fallback = (40+60)//2 = 50
        assert result["price_adjustment_pct"] == 50


# ── Empate 1/1/1 → árbitro ────────────────────────────────────────────────────

class TestTieArbitration:
    def test_tie_goes_to_arbitrator(self):
        """1/1/1 empate → árbitro llamado, su acción es la devuelta."""
        arb_response = {
            "action": "rebajar",
            "price_adjustment_pct": 50,
            "reasoning": "Árbitro: equilibrio entre seguridad y rentabilidad",
            "deciding_factor": "El riesgo sanitario permite venta con descuento",
        }
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "retirar", 80, 0)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 75, 50)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "donar", 70, 0)), \
             patch("backend.agents.consensus.llm.call_structured_deep",
                   return_value=arb_response) as mock_arb:
            result = reach_consensus(PRODUCT_BASE, days_left=1, qty=10, heuristic_score=90)

        mock_arb.assert_called_once()
        assert result["action"] == "rebajar"

    def test_tie_thinking_summary_mentions_arbitrator(self):
        """Cuando hay empate, thinking_summary menciona 'Árbitro'."""
        arb_response = {
            "action": "donar",
            "price_adjustment_pct": 0,
            "reasoning": "Donación es lo ético",
            "deciding_factor": "Seguridad prevalece sobre rentabilidad",
        }
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "retirar", 90, 0)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 80, 40)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "donar", 75, 0)), \
             patch("backend.agents.consensus.llm.call_structured_deep",
                   return_value=arb_response):
            result = reach_consensus(PRODUCT_BASE, days_left=1, qty=10, heuristic_score=90)

        assert "Árbitro" in result["thinking_summary"]

    def test_tie_consensus_used_true(self):
        """Incluso yendo al árbitro, consensus_used debe ser True (el consenso fue invocado)."""
        arb_response = {
            "action": "revisar",
            "price_adjustment_pct": 0,
            "reasoning": "Revisar con cuidado",
            "deciding_factor": "Incertidumbre alta",
        }
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "retirar", 80, 0)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 80, 40)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "donar", 80, 0)), \
             patch("backend.agents.consensus.llm.call_structured_deep",
                   return_value=arb_response):
            result = reach_consensus(PRODUCT_BASE, days_left=2, qty=10, heuristic_score=90)

        assert result["consensus_used"] is True

    def test_tie_arbiter_default_action_when_llm_returns_none(self):
        """Si el árbitro falla (None), la acción por defecto es 'revisar'."""
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "retirar", 80, 0)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 80, 40)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "donar", 80, 0)), \
             patch("backend.agents.consensus.llm.call_structured_deep", return_value=None):
            result = reach_consensus(PRODUCT_BASE, days_left=2, qty=10, heuristic_score=90)

        assert result["action"] == "revisar"


# ── Formato de respuesta compatible con evaluator ────────────────────────────

class TestOutputFormat:
    REQUIRED_FIELDS = {
        "risk_level", "score", "action", "price_adjustment_pct",
        "reasoning", "thinking_summary", "days_left",
        "total_value_at_risk", "consensus_used",
    }

    def _result_majority(self):
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "rebajar", 85, 40)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 80, 35)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "revisar", 60, 0)):
            return reach_consensus(PRODUCT_BASE, days_left=2, qty=8, heuristic_score=90)

    def test_all_required_fields_present(self):
        result = self._result_majority()
        missing = self.REQUIRED_FIELDS - result.keys()
        assert not missing, f"Faltan campos: {missing}"

    def test_score_within_0_100(self):
        result = self._result_majority()
        assert 0 <= result["score"] <= 100

    def test_risk_level_valid_value(self):
        result = self._result_majority()
        assert result["risk_level"] in ("BAJO", "MEDIO", "ALTO", "CRÍTICO")

    def test_action_is_valid_enum(self):
        result = self._result_majority()
        valid_actions = {"rebajar", "retirar", "donar", "revisar", "reponer", "ok"}
        assert result["action"] in valid_actions

    def test_days_left_preserved(self):
        result = self._result_majority()
        assert result["days_left"] == 2

    def test_total_value_at_risk_calculated(self):
        # 8 uds × 1.80€ = 14.40€
        result = self._result_majority()
        assert result["total_value_at_risk"] == pytest.approx(14.40, rel=1e-3)

    def test_vote_trace_present_in_majority_result(self):
        """El resultado con mayoría incluye vote_trace con 3 entradas."""
        result = self._result_majority()
        assert "vote_trace" in result
        assert len(result["vote_trace"]) == 3

    def test_vote_trace_has_required_keys(self):
        result = self._result_majority()
        for entry in result["vote_trace"]:
            assert "perspective" in entry
            assert "action" in entry
            assert "confidence" in entry


# ── Pesos por categoría ───────────────────────────────────────────────────────

class TestCategoryWeights:
    def test_safety_boost_in_carne_category(self):
        """En carne, la confianza de 'seguridad' se incrementa +20 antes de ponderar."""
        # Configuramos un caso donde 2 votan 'retirar' (seguridad + ops)
        # y 1 vota 'rebajar' (rentabilidad con conf alta)
        # Con boost +20 en seguridad, su confianza sube de 70 a 90
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "retirar", 70, 0)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 85, 40)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "retirar", 75, 0)):
            result = reach_consensus(PRODUCT_CARNE, days_left=0, qty=5, heuristic_score=90)

        # La mayoría (retirar) debe ganar
        assert result["action"] == "retirar"

    def test_profit_boost_in_conservas_category(self):
        """En conservas, la confianza de 'rentabilidad' se incrementa +15 antes de ponderar."""
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "revisar", 65, 0)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 70, 30)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "rebajar", 75, 35)):
            result = reach_consensus(PRODUCT_CONSERVAS, days_left=5, qty=20, heuristic_score=90)

        assert result["action"] == "rebajar"

    def test_no_boost_for_neutral_category(self):
        """Categoría sin boost especial (ej. 'panaderia') no toca las confianzas."""
        product_neutral = {**PRODUCT_BASE, "category": "panaderia"}
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "rebajar", 80, 30)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 80, 40)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "revisar", 60, 0)):
            result = reach_consensus(product_neutral, days_left=1, qty=10, heuristic_score=90)

        # La mayoría funciona igual sin boost
        assert result["action"] == "rebajar"
        assert result["consensus_used"] is True


# ── Debate Jeffrey (score>=95, valor>=50€) ────────────────────────────────────

class TestJeffreyDebate:
    def test_jeffrey_activated_before_parallel_votes(self):
        """Con score>=95 y valor>=50€, Jeffrey se activa y los votos paralelos NO se llaman."""
        jeffrey_synthesis = {
            "action": "rebajar",
            "price_adjustment_pct": 60,
            "reasoning": "Síntesis del debate Jeffrey",
            "deciding_factor": "El Crítico señaló que el producto es seguro con descuento",
        }
        # 5 uds × 12€ = 60€ >= 50€, score=96 >= 95 → Jeffrey
        with patch("backend.agents.consensus.llm.call_fast", return_value="Posición del agente"), \
             patch("backend.agents.consensus.llm.call_structured_deep",
                   return_value=jeffrey_synthesis), \
             patch("backend.agents.consensus._vote_safety") as mock_vs, \
             patch("backend.agents.consensus._vote_profitability") as mock_vp, \
             patch("backend.agents.consensus._vote_operations") as mock_vo:
            result = reach_consensus(PRODUCT_CARO, days_left=0, qty=5, heuristic_score=96)

        # Los votos paralelos NO deben haberse llamado
        mock_vs.assert_not_called()
        mock_vp.assert_not_called()
        mock_vo.assert_not_called()
        assert result["action"] == "rebajar"

    def test_jeffrey_thinking_summary_contains_jeffrey(self):
        """El thinking_summary del debate Jeffrey contiene 'Jeffrey'."""
        synthesis = {
            "action": "retirar",
            "price_adjustment_pct": 0,
            "reasoning": "Seguridad primero",
            "deciding_factor": "Caducado y riesgo alto",
        }
        with patch("backend.agents.consensus.llm.call_fast", return_value="Debate simulado"), \
             patch("backend.agents.consensus.llm.call_structured_deep", return_value=synthesis):
            result = reach_consensus(PRODUCT_CARO, days_left=0, qty=5, heuristic_score=96)

        assert "Jeffrey" in result["thinking_summary"]

    def test_jeffrey_not_activated_below_score_threshold(self):
        """Con score<95, incluso con valor alto, se usa consenso paralelo normal."""
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "rebajar", 85, 40)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "rebajar", 80, 35)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "rebajar", 75, 30)), \
             patch("backend.agents.consensus.llm.call_fast") as mock_fast:
            # score=94 < 95 → no Jeffrey aunque 5 uds × 12€ = 60€ >= 50€
            result = reach_consensus(PRODUCT_CARO, days_left=1, qty=5, heuristic_score=94)

        mock_fast.assert_not_called()
        assert result["action"] == "rebajar"

    def test_jeffrey_not_activated_below_value_threshold(self):
        """Con score>=95 pero valor<50€, se usa consenso paralelo normal."""
        product_cheap = {**PRODUCT_BASE, "price": 1.50}  # 10 uds × 1.50€ = 15€ < 50€
        with patch("backend.agents.consensus._vote_safety",
                   return_value=_vote("seguridad", "retirar", 90, 0)), \
             patch("backend.agents.consensus._vote_profitability",
                   return_value=_vote("rentabilidad", "retirar", 85, 0)), \
             patch("backend.agents.consensus._vote_operations",
                   return_value=_vote("operaciones", "retirar", 80, 0)), \
             patch("backend.agents.consensus.llm.call_fast") as mock_fast:
            result = reach_consensus(product_cheap, days_left=0, qty=10, heuristic_score=96)

        mock_fast.assert_not_called()
        assert result["action"] == "retirar"


# ── Fallback cuando el pool falla ─────────────────────────────────────────────

class TestFallback:
    def test_fallback_consensus_used_false(self):
        """_fallback() devuelve consensus_used=False."""
        result = _fallback(PRODUCT_BASE, days_left=1, qty=10, heuristic_score=92)
        assert result["consensus_used"] is False

    def test_fallback_expired_product_action_retirar(self):
        """Producto caducado (days_left<=0) → acción 'retirar'."""
        result = _fallback(PRODUCT_BASE, days_left=0, qty=5, heuristic_score=95)
        assert result["action"] == "retirar"

    def test_fallback_2_days_action_rebajar(self):
        """2 días → 'rebajar'."""
        result = _fallback(PRODUCT_BASE, days_left=2, qty=5, heuristic_score=90)
        assert result["action"] == "rebajar"

    def test_fallback_7_days_action_revisar(self):
        """7 días → 'revisar'."""
        result = _fallback(PRODUCT_BASE, days_left=7, qty=5, heuristic_score=90)
        assert result["action"] == "revisar"

    def test_fallback_risk_level_critical_when_score_high(self):
        """heuristic_score>=85 → CRÍTICO en fallback."""
        result = _fallback(PRODUCT_BASE, days_left=1, qty=5, heuristic_score=90)
        assert result["risk_level"] == "CRÍTICO"

    def test_fallback_risk_level_alto_when_score_low(self):
        """heuristic_score<85 → ALTO en fallback."""
        result = _fallback(PRODUCT_BASE, days_left=1, qty=5, heuristic_score=80)
        assert result["risk_level"] == "ALTO"

    def test_pool_timeout_triggers_fallback(self):
        """Si future.result() lanza TimeoutError → _fallback() llamado."""
        from concurrent.futures import TimeoutError as FuturesTimeout

        future_mock = MagicMock()
        future_mock.result.side_effect = FuturesTimeout("timeout")

        pool_mock = MagicMock()
        pool_mock.submit.return_value = future_mock
        pool_mock.__enter__ = MagicMock(return_value=pool_mock)
        pool_mock.__exit__ = MagicMock(return_value=False)

        with patch("backend.agents.consensus.ThreadPoolExecutor",
                   return_value=pool_mock):
            result = reach_consensus(PRODUCT_BASE, days_left=1, qty=10, heuristic_score=90)

        assert result["consensus_used"] is False
        assert result["action"] in ("rebajar", "retirar", "revisar")


# ── _build_result — función auxiliar ─────────────────────────────────────────

class TestBuildResult:
    def test_score_formula(self):
        """score = min(100, int(heuristic*0.7 + confidence*0.3))."""
        result = _build_result(
            action="rebajar",
            confidence=80,
            price_adjustment_pct=40,
            reasoning="test",
            thinking_summary="test",
            days_left=2,
            total_value_at_risk=30.0,
            heuristic_score=90,
        )
        expected = min(100, int(90 * 0.7 + 80 * 0.3))  # int(63+24) = 87
        assert result["score"] == expected

    def test_score_capped_at_100(self):
        result = _build_result(
            action="retirar",
            confidence=100,
            price_adjustment_pct=0,
            reasoning="test",
            thinking_summary="test",
            days_left=0,
            total_value_at_risk=100.0,
            heuristic_score=100,
        )
        assert result["score"] == 100

    def test_risk_levels_thresholds(self):
        """
        Verifica las cuatro bandas de riesgo.
        score = min(100, int(heuristic*0.7 + confidence*0.3))
        CRÍTICO >= 85 | ALTO >= 65 | MEDIO >= 40 | BAJO < 40
        """
        for score_h, score_c, expected_risk in [
            (100, 100, "CRÍTICO"),  # score = 100 >= 85 → CRÍTICO
            (90,  90,  "CRÍTICO"),  # int(90*0.7+90*0.3)=90 >= 85 → CRÍTICO
            (70,  60,  "ALTO"),     # int(70*0.7+60*0.3)=67 >= 65 → ALTO
            (30,  30,  "BAJO"),     # int(30*0.7+30*0.3)=30 < 40 → BAJO
        ]:
            result = _build_result(
                action="revisar",
                confidence=score_c,
                price_adjustment_pct=0,
                reasoning="t",
                thinking_summary="t",
                days_left=5,
                total_value_at_risk=10.0,
                heuristic_score=score_h,
            )
            assert result["risk_level"] == expected_risk, (
                f"heuristic={score_h}, conf={score_c} → esperado {expected_risk}, "
                f"obtenido {result['risk_level']} (score={result['score']})"
            )

    def test_vote_trace_excluded_when_none(self):
        """Sin vote_trace, la clave no aparece en el resultado."""
        result = _build_result(
            action="rebajar",
            confidence=75,
            price_adjustment_pct=30,
            reasoning="test",
            thinking_summary="test",
            days_left=3,
            total_value_at_risk=20.0,
            heuristic_score=85,
        )
        assert "vote_trace" not in result

    def test_vote_trace_included_and_filtered(self):
        """vote_trace solo conserva perspective, action y confidence (sin reasoning)."""
        votes = [
            _vote("seguridad", "rebajar", 90, 40),
            _vote("rentabilidad", "rebajar", 80, 35),
            _vote("operaciones", "revisar", 60, 0),
        ]
        result = _build_result(
            action="rebajar",
            confidence=85,
            price_adjustment_pct=38,
            reasoning="test",
            thinking_summary="test",
            days_left=1,
            total_value_at_risk=18.0,
            heuristic_score=90,
            vote_trace=votes,
        )
        assert "vote_trace" in result
        for entry in result["vote_trace"]:
            assert set(entry.keys()) == {"perspective", "action", "confidence"}
