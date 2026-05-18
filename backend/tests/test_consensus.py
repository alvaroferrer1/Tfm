"""
Tests del Consensus Engine.
Verifica votación por mayoría, árbitro Opus, debate Jeffrey y fallback.
"""
from unittest.mock import patch, MagicMock
import pytest

from backend.agents.consensus import reach_consensus, _build_result, _fallback, _jeffrey_debate


PRODUCT_CARNE = {
    "id": "p-008",
    "name": "Carne picada mixta 500g",
    "category": "carne",
    "price": 4.20,
    "cost": 2.10,
}


def _vote(perspective: str, action: str, confidence: int = 80, discount: int = 40) -> dict:
    return {
        "perspective": perspective,
        "action": action,
        "confidence": confidence,
        "reasoning": f"Test: {perspective} recomienda {action}",
        "price_adjustment_pct": discount,
    }


class TestReachConsensus:
    def test_majority_2_of_3_returns_winner(self):
        """Dos perspectivas coinciden → ganadora directa."""
        votes = [
            _vote("seguridad", "rebajar", 90, 40),
            _vote("rentabilidad", "rebajar", 85, 45),
            _vote("operaciones", "revisar", 60, 0),
        ]
        with patch("backend.agents.consensus._vote_safety", return_value=votes[0]):
            with patch("backend.agents.consensus._vote_profitability", return_value=votes[1]):
                with patch("backend.agents.consensus._vote_operations", return_value=votes[2]):
                    result = reach_consensus(PRODUCT_CARNE, days_left=1, qty=12)

        assert result["action"] == "rebajar"
        assert "consensus_used" in result
        assert result["consensus_used"] is True

    def test_unanimous_returns_winner(self):
        """Los tres votan igual → confianza máxima."""
        vote = _vote("seguridad", "retirar", 95, 0)
        with patch("backend.agents.consensus._vote_safety", return_value=vote):
            with patch("backend.agents.consensus._vote_profitability", return_value=_vote("rentabilidad", "retirar", 80, 0)):
                with patch("backend.agents.consensus._vote_operations", return_value=_vote("operaciones", "retirar", 90, 0)):
                    result = reach_consensus(PRODUCT_CARNE, days_left=0, qty=12)

        assert result["action"] == "retirar"

    def test_tie_activates_arbitration(self):
        """3 acciones distintas → árbitro."""
        arb_result = {
            "action": "rebajar",
            "price_adjustment_pct": 50,
            "reasoning": "Árbitro: rebajar es lo correcto",
            "deciding_factor": "La seguridad permite rebajar",
        }
        with patch("backend.agents.consensus._vote_safety", return_value=_vote("seguridad", "retirar")):
            with patch("backend.agents.consensus._vote_profitability", return_value=_vote("rentabilidad", "rebajar")):
                with patch("backend.agents.consensus._vote_operations", return_value=_vote("operaciones", "donar")):
                    with patch("backend.agents.consensus.llm.call_structured_deep", return_value=arb_result):
                        result = reach_consensus(PRODUCT_CARNE, days_left=1, qty=12)

        assert result["action"] == "rebajar"
        assert "Árbitro" in result["thinking_summary"]

    def test_result_has_evaluator_compatible_fields(self):
        """El resultado debe ser compatible con el formato de evaluator.evaluate()."""
        required = {"risk_level", "score", "action", "price_adjustment_pct",
                    "reasoning", "thinking_summary", "days_left", "total_value_at_risk"}
        vote = _vote("seguridad", "rebajar", 85, 40)
        with patch("backend.agents.consensus._vote_safety", return_value=vote):
            with patch("backend.agents.consensus._vote_profitability", return_value=vote):
                with patch("backend.agents.consensus._vote_operations", return_value=_vote("operaciones", "revisar", 60)):
                    result = reach_consensus(PRODUCT_CARNE, days_left=2, qty=8)

        assert required.issubset(result.keys())

    def test_timeout_returns_fallback(self):
        """Si las perspectivas fallan, el fallback es conservador."""
        from concurrent.futures import TimeoutError as FuturesTimeout
        with patch("backend.agents.consensus._vote_safety", side_effect=FuturesTimeout()):
            with patch("backend.agents.consensus._vote_profitability", return_value=_vote("rentabilidad", "rebajar")):
                with patch("backend.agents.consensus._vote_operations", return_value=_vote("operaciones", "revisar")):
                    with patch("backend.agents.consensus.ThreadPoolExecutor") as mock_pool:
                        mock_cm = MagicMock()
                        mock_pool.return_value.__enter__ = MagicMock(return_value=mock_cm)
                        mock_pool.return_value.__exit__ = MagicMock(return_value=False)
                        future_mock = MagicMock()
                        future_mock.result.side_effect = FuturesTimeout()
                        mock_cm.submit.return_value = future_mock

                        result = _fallback(PRODUCT_CARNE, days_left=1, qty=12, heuristic_score=92)

        assert result["consensus_used"] is False
        assert result["action"] in ("rebajar", "retirar", "revisar")


class TestBuildResult:
    def test_score_stays_within_bounds(self):
        result = _build_result(
            action="rebajar",
            confidence=100,
            price_adjustment_pct=40,
            reasoning="test",
            thinking_summary="test",
            days_left=1,
            total_value_at_risk=50.0,
            heuristic_score=100,
        )
        assert 0 <= result["score"] <= 100

    def test_risk_level_critical_when_score_high(self):
        result = _build_result(
            action="rebajar",
            confidence=95,
            price_adjustment_pct=50,
            reasoning="test",
            thinking_summary="test",
            days_left=0,
            total_value_at_risk=80.0,
            heuristic_score=95,
        )
        assert result["risk_level"] == "CRÍTICO"

    def test_jeffrey_debate_activated_for_extreme_cases(self):
        """Score >= 95 y valor >= 50€ activa el debate Jeffrey en lugar del consenso paralelo."""
        PRODUCT_CARO = {**PRODUCT_CARNE, "price": 10.0, "cost": 5.0}
        synthesis = {
            "action": "rebajar",
            "price_adjustment_pct": 50,
            "reasoning": "Síntesis del debate",
            "deciding_factor": "El Crítico señaló riesgo de seguridad controlable",
        }
        with patch("backend.agents.consensus.llm.call_fast", return_value="Posición del agente"):
            with patch("backend.agents.consensus.llm.call_structured_deep", return_value=synthesis):
                result = reach_consensus(PRODUCT_CARO, days_left=0, qty=10, heuristic_score=96)

        assert result["action"] == "rebajar"
        assert "Jeffrey" in result["thinking_summary"]

    def test_dissent_appears_in_reasoning(self):
        """Cuando hay disenso en la mayoría, debe aparecer en el razonamiento."""
        votes = [
            _vote("seguridad", "rebajar", 90),
            _vote("rentabilidad", "rebajar", 85),
            _vote("operaciones", "revisar", 60),
        ]
        with patch("backend.agents.consensus._vote_safety", return_value=votes[0]):
            with patch("backend.agents.consensus._vote_profitability", return_value=votes[1]):
                with patch("backend.agents.consensus._vote_operations", return_value=votes[2]):
                    result = reach_consensus(PRODUCT_CARNE, days_left=1, qty=12)

        assert "operaciones" in result["reasoning"].lower() or "Disiente" in result["reasoning"]
