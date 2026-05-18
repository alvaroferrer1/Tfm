"""
Tests del Validator Agent — foco en la detección determinista de contradicciones.
Los tests que llaman LLM están marcados con @pytest.mark.integration.
"""
from datetime import date, datetime, timedelta
import pytest
from unittest.mock import patch
from backend.agents.validator import _check_contradictions, validate_section_review


class TestCheckContradictions:
    """Detección determinista de contradicciones — sin LLM."""

    def _make_risk(self, risk_level: str, score: int, action: str, days_left: int):
        return {
            "risk_level": risk_level,
            "score": score,
            "action": action,
            "days_left": days_left,
            "reasoning": "test",
        }

    def _make_price(self, discount_pct: int, new_price: float, original_price: float):
        return {
            "discount_pct": discount_pct,
            "new_price": new_price,
            "original_price": original_price,
            "recommendation_text": f"REBAJAR {discount_pct}%",
        }

    def test_restock_with_critical_is_contradiction(self, product_carne):
        batch = {"expiry_date": (date.today() + timedelta(days=1)).isoformat(), "quantity": 5}
        risk = self._make_risk("CRÍTICO", 95, "rebajar", 1)
        price = self._make_price(50, 2.10, 4.20)
        issues = _check_contradictions(product_carne, batch, risk, "SÍ reponer — 4 uds", price)
        assert any("CONTRADICCIÓN" in i or "reponer" in i.lower() for i in issues)

    def test_price_below_cost_is_violation(self, product_carne):
        batch = {"expiry_date": (date.today() + timedelta(days=1)).isoformat(), "quantity": 5}
        risk = self._make_risk("CRÍTICO", 90, "rebajar", 1)
        # New price below cost (cost = 2.10)
        price = self._make_price(60, 1.50, 4.20)
        issues = _check_contradictions(product_carne, batch, risk, "NO reponer", price)
        assert any("VIOLACIÓN" in i or "coste" in i.lower() for i in issues)

    def test_critical_with_ok_action_is_incoherence(self, product_carne):
        batch = {"expiry_date": date.today().isoformat(), "quantity": 10}
        risk = self._make_risk("CRÍTICO", 100, "ok", 0)
        price = self._make_price(0, 4.20, 4.20)
        issues = _check_contradictions(product_carne, batch, risk, "NO reponer", price)
        assert any("INCOHERENCIA" in i or "crítico" in i.lower() for i in issues)

    def test_expired_with_ok_action(self, product_panaderia):
        batch = {"expiry_date": (date.today() - timedelta(days=1)).isoformat(), "quantity": 5}
        risk = self._make_risk("BAJO", 10, "ok", -1)
        price = self._make_price(0, 1.20, 1.20)
        issues = _check_contradictions(product_panaderia, batch, risk, "NO reponer", price)
        assert any("ERROR CRÍTICO" in i or "caducado" in i.lower() for i in issues)

    def test_premature_donation(self, product_pescado):
        batch = {"expiry_date": (date.today() + timedelta(days=5)).isoformat(), "quantity": 4}
        risk = self._make_risk("MEDIO", 45, "donar", 5)
        price = self._make_price(20, 6.32, 7.90)
        issues = _check_contradictions(product_pescado, batch, risk, "NO reponer", price)
        assert any("PREMATURA" in i or "donar" in i.lower() for i in issues)

    def test_unjustified_withdrawal(self, product_panaderia):
        batch = {"expiry_date": (date.today() + timedelta(days=4)).isoformat(), "quantity": 8}
        risk = self._make_risk("BAJO", 15, "retirar", 4)
        price = self._make_price(0, 1.20, 1.20)
        issues = _check_contradictions(product_panaderia, batch, risk, "NO reponer", price)
        assert any("INJUSTIFICADA" in i or "retirar" in i.lower() for i in issues)

    def test_valid_scenario_has_no_issues(self, product_carne, batch_expiring_tomorrow):
        risk = self._make_risk("CRÍTICO", 92, "rebajar", 1)
        # New price above cost (cost = 2.10, min = 2.21)
        price = self._make_price(50, 2.25, 4.20)
        issues = _check_contradictions(product_carne, batch_expiring_tomorrow, risk, "NO reponer", price)
        assert len(issues) == 0

    def test_no_contradiction_when_restocking_far_future(self):
        product = {"id": "p-x", "name": "Test", "cost": 0.50, "price": 1.50}
        batch = {
            "expiry_date": (date.today() + timedelta(days=7)).isoformat(),
            "quantity": 2,
        }
        risk = self._make_risk("BAJO", 15, "revisar", 7)
        price = self._make_price(10, 1.35, 1.50)
        issues = _check_contradictions(product, batch, risk, "SÍ reponer — solo 2 uds", price)
        # Should not flag restock contradiction for low risk with 7 days
        restock_issues = [i for i in issues if "CONTRADICCIÓN" in i and "reponer" in i.lower()]
        assert len(restock_issues) == 0


class TestSectionReview:
    """Tests para Feature #21: alerta de pasillos sin revisión."""

    def _batch(self, pasillo: str, days_left: int) -> dict:
        return {
            "expiry_date": (date.today() + timedelta(days=days_left)).isoformat(),
            "quantity": 5,
            "products": {"name": "Test", "pasillo": pasillo},
        }

    def _completed_action(self, pasillo: str, hours_ago: float) -> dict:
        completed_at = datetime.now() - timedelta(hours=hours_ago)
        return {
            "status": "completed",
            "completed_at": completed_at.isoformat(),
            "batches": {"products": {"pasillo": pasillo}},
        }

    def test_no_batches_returns_ok(self):
        result = validate_section_review("store", [], [])
        assert result["ok"] is True
        assert result["total_stale_pasillos"] == 0

    def test_critical_without_any_review_returns_alert(self):
        batches = [self._batch("A1", 1), self._batch("A1", 0)]
        result = validate_section_review("store", batches, completed_actions=[])
        assert result["total_stale_pasillos"] == 1
        assert result["alerts"][0]["pasillo"] == "A1"
        assert result["ok"] is False

    def test_recently_reviewed_section_no_alert(self):
        batches = [self._batch("B2", 1)]
        completed = [self._completed_action("B2", hours_ago=1)]
        result = validate_section_review("store", batches, completed, stale_hours=4)
        assert result["ok"] is True

    def test_stale_section_returns_alert(self):
        batches = [self._batch("C3", 0)]
        completed = [self._completed_action("C3", hours_ago=6)]
        result = validate_section_review("store", batches, completed, stale_hours=4)
        assert result["ok"] is False
        assert result["alerts"][0]["hours_since_review"] >= 6

    def test_non_critical_batch_does_not_alert(self):
        # 5 days left = not critical (threshold is <= 2)
        batches = [self._batch("D4", 5)]
        result = validate_section_review("store", batches, completed_actions=[])
        assert result["ok"] is True

    def test_alert_sorted_by_critical_count_desc(self):
        batches = [
            self._batch("A1", 0),
            self._batch("B2", 1), self._batch("B2", 0), self._batch("B2", 2),
        ]
        result = validate_section_review("store", batches, completed_actions=[])
        # B2 has 3 critical, A1 has 1 — B2 should come first
        assert result["alerts"][0]["pasillo"] == "B2"
