"""Tests para backend/agents/fork_merge.py — sin LLM real."""
from __future__ import annotations
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_product(price: float = 10.0, cost: float = 5.0,
                  name: str = "Merluza", category: str = "pescado") -> dict:
    return {"name": name, "price": price, "cost": cost, "category": category,
            "id": "prod-001"}


def _make_batch(days_left: int = 1, qty: int = 10) -> dict:
    exp = (date.today() + timedelta(days=days_left)).isoformat()
    return {"expiry_date": exp, "quantity": qty, "id": "batch-001"}


# ── should_use_fork_merge ─────────────────────────────────────────────────────

class TestShouldUseForkMerge:
    def test_high_value_triggers(self):
        from backend.agents.fork_merge import should_use_fork_merge
        product = _make_product(price=20.0)
        batches = [_make_batch(days_left=3, qty=5)]  # 5×20=100 > 50
        assert should_use_fork_merge(product, batches) is True

    def test_low_value_not_triggered(self):
        from backend.agents.fork_merge import should_use_fork_merge
        product = _make_product(price=1.0)
        batches = [_make_batch(days_left=3, qty=3)]  # 3×1=3 < 50
        assert should_use_fork_merge(product, batches) is False

    def test_expired_today_triggers(self):
        from backend.agents.fork_merge import should_use_fork_merge
        product = _make_product(price=1.0)
        batches = [_make_batch(days_left=0, qty=1)]  # days_left=0 → siempre activa
        assert should_use_fork_merge(product, batches) is True

    def test_empty_batches_no_trigger(self):
        from backend.agents.fork_merge import should_use_fork_merge
        assert should_use_fork_merge(_make_product(), []) is False


# ── evaluate_fork_merge ───────────────────────────────────────────────────────

def _branch_result(action="rebajar", price_pct=30, score=80, confidence=75,
                   branch_name="clearance") -> dict:
    return {
        "branch_name": branch_name,
        "action": action,
        "price_adjustment_pct": price_pct,
        "score": score,
        "confidence": confidence,
        "reasoning": "Test reasoning.",
    }


def _merge_result(action="rebajar", score=85, pct=35, branch="clearance") -> dict:
    return {
        "winning_branch": branch,
        "action": action,
        "price_adjustment_pct": pct,
        "score": score,
        "risk_level": "CRÍTICO",
        "synthesis": "Rebaja agresiva — caduca hoy con alto stock.",
    }


class TestEvaluateForkMerge:
    def test_empty_batches_returns_safe_default(self):
        from backend.agents.fork_merge import evaluate_fork_merge
        result = evaluate_fork_merge(_make_product(), [])
        assert result["score"] == 0
        assert result["action"] == "ok"
        assert result["risk_level"] == "BAJO"

    def test_returns_required_keys(self):
        from backend.agents.fork_merge import evaluate_fork_merge
        branches = [
            _branch_result("clearance"),
            _branch_result("margin"),
            _branch_result("donation"),
        ]
        with patch("backend.agents.fork_merge.llm.call_structured_fast",
                   side_effect=[branches[0], branches[1], branches[2]]), \
             patch("backend.agents.fork_merge.llm.call_structured_deep",
                   return_value=_merge_result()):
            result = evaluate_fork_merge(
                _make_product(price=20.0),
                [_make_batch(days_left=1, qty=10)],
            )
        required = {"risk_level", "score", "action", "price_adjustment_pct",
                    "reasoning", "thinking_summary", "days_left",
                    "total_value_at_risk", "method"}
        assert required.issubset(result.keys())

    def test_method_is_fork_merge(self):
        from backend.agents.fork_merge import evaluate_fork_merge
        branches = [_branch_result() for _ in range(3)]
        with patch("backend.agents.fork_merge.llm.call_structured_fast",
                   side_effect=branches), \
             patch("backend.agents.fork_merge.llm.call_structured_deep",
                   return_value=_merge_result()):
            result = evaluate_fork_merge(
                _make_product(price=20.0),
                [_make_batch(days_left=0, qty=5)],
            )
        assert result["method"] in ("fork_merge", "fork_merge_fallback", "fork_merge_consensus")

    def test_fallback_when_merge_fails(self):
        """Si Opus falla en el merge, usa la rama de mayor confianza."""
        from backend.agents.fork_merge import evaluate_fork_merge
        branches = [
            _branch_result(action="donar", confidence=90, branch_name="donation"),
            _branch_result(action="rebajar", confidence=60, branch_name="clearance"),
            _branch_result(action="retirar", confidence=40, branch_name="margin"),
        ]
        with patch("backend.agents.fork_merge.llm.call_structured_fast",
                   side_effect=branches), \
             patch("backend.agents.fork_merge.llm.call_structured_deep",
                   side_effect=RuntimeError("Opus no disponible")):
            result = evaluate_fork_merge(
                _make_product(price=20.0),
                [_make_batch(days_left=1, qty=10)],
            )
        # Debe usar la rama de mayor confianza (donation=90%)
        assert result["action"] == "donar"
        assert result["method"] == "fork_merge_fallback"

    def test_total_value_at_risk_calculated(self):
        from backend.agents.fork_merge import evaluate_fork_merge
        branches = [_branch_result() for _ in range(3)]
        with patch("backend.agents.fork_merge.llm.call_structured_fast",
                   side_effect=branches), \
             patch("backend.agents.fork_merge.llm.call_structured_deep",
                   return_value=_merge_result()):
            result = evaluate_fork_merge(
                _make_product(price=5.0),
                [_make_batch(days_left=2, qty=8)],
            )
        assert result["total_value_at_risk"] == pytest.approx(40.0, abs=0.1)

    def test_branches_in_result_when_merge_succeeds(self):
        from backend.agents.fork_merge import evaluate_fork_merge
        b = [_branch_result() for _ in range(3)]
        with patch("backend.agents.fork_merge.llm.call_structured_fast",
                   side_effect=b), \
             patch("backend.agents.fork_merge.llm.call_structured_deep",
                   return_value=_merge_result()):
            result = evaluate_fork_merge(
                _make_product(price=20.0),
                [_make_batch(days_left=1, qty=5)],
            )
        assert "branches" in result
        assert len(result["branches"]) == 3
