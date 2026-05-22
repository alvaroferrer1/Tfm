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


class TestNewAdversarialAttacks:
    """Tests para los 6 nuevos ataques adversariales (contradicciones 8-13)."""

    def _make_risk(self, risk_level, score, action, days_left):
        return {"risk_level": risk_level, "score": score, "action": action,
                "days_left": days_left, "reasoning": "test"}

    def _make_price(self, discount_pct, new_price, original_price=4.20):
        return {"discount_pct": discount_pct, "new_price": new_price,
                "original_price": original_price, "recommendation_text": f"{discount_pct}%"}

    def test_attack8_high_score_soft_action(self):
        """Score ≥95 con acción blanda debe detectarse (ataque 8)."""
        product = {"id": "p1", "name": "Merluza", "cost": 2.10, "price": 4.20}
        batch = {"expiry_date": date.today().isoformat(), "quantity": 5}
        risk = self._make_risk("CRÍTICO", 98, "revisar", 0)
        price = self._make_price(0, 4.20)
        issues = _check_contradictions(product, batch, risk, "NO reponer", price)
        assert any("DIVERGENCIA" in i or "score" in i.lower() for i in issues)

    def test_attack9_rebajar_with_zero_stock(self):
        """Rebajar con 0 unidades en tienda es acción imposible (ataque 9)."""
        product = {"id": "p2", "name": "Pan integral", "cost": 0.80, "price": 1.60}
        batch = {"expiry_date": date.today().isoformat(), "quantity": 0}
        risk = self._make_risk("ALTO", 82, "rebajar", 0)
        price = self._make_price(40, 0.96)
        issues = _check_contradictions(product, batch, risk, "NO reponer", price)
        assert any("IMPOSIBLE" in i or "0 unidades" in i for i in issues)

    def test_attack10_excessive_discount_low_risk(self):
        """Descuento >70% con riesgo MEDIO y 3 días es excesivo (ataque 10)."""
        product = {"id": "p3", "name": "Yogur", "cost": 0.50, "price": 1.20}
        batch = {"expiry_date": (date.today() + timedelta(days=3)).isoformat(), "quantity": 10}
        risk = self._make_risk("MEDIO", 50, "rebajar", 3)
        price = self._make_price(75, 0.30)
        issues = _check_contradictions(product, batch, risk, "NO reponer", price)
        assert any("EXCESIVO" in i or "70%" in i for i in issues)

    def test_attack11_large_expired_stock_no_donation(self):
        """Más de 50 uds caducadas sin proponer donación (ataque 11)."""
        product = {"id": "p4", "name": "Baguettes", "cost": 0.40, "price": 0.90}
        batch = {"expiry_date": (date.today() - timedelta(days=1)).isoformat(), "quantity": 60}
        risk = self._make_risk("CRÍTICO", 99, "retirar", -1)
        price = self._make_price(0, 0.90)
        issues = _check_contradictions(product, batch, risk, "NO reponer", price)
        assert any("DONACIÓN" in i or "50" in i for i in issues)

    def test_attack12_reposicion_con_riesgo_alto(self):
        """Reponer con riesgo ALTO viola FEFO (ataque 12)."""
        product = {"id": "p5", "name": "Fresas", "cost": 1.50, "price": 3.00}
        batch = {"expiry_date": (date.today() + timedelta(days=1)).isoformat(), "quantity": 8}
        risk = self._make_risk("ALTO", 88, "reponer", 1)
        price = self._make_price(30, 2.10)
        issues = _check_contradictions(product, batch, risk, "SÍ reponer — solo 8 uds", price)
        assert any("REPOSICIÓN" in i or "FEFO" in i for i in issues)

    def test_attack13_rebaja_sin_efecto(self):
        """Acción rebajar pero precio nuevo = precio original (ataque 13)."""
        product = {"id": "p6", "name": "Leche", "cost": 0.60, "price": 1.20, "category": "lacteos"}
        batch = {"expiry_date": (date.today() + timedelta(days=2)).isoformat(), "quantity": 12}
        risk = self._make_risk("ALTO", 80, "rebajar", 2)
        price = self._make_price(0, 1.20, 1.20)  # mismo precio
        issues = _check_contradictions(product, batch, risk, "NO reponer", price)
        assert any("SIN EFECTO" in i or "idéntico" in i for i in issues)

    def test_attack8_no_false_positive_normal_action(self):
        """Score 95 con RETIRAR no debe disparar la contradicción 8."""
        product = {"id": "p7", "name": "Pollo", "cost": 3.00, "price": 6.00}
        batch = {"expiry_date": date.today().isoformat(), "quantity": 4}
        risk = self._make_risk("CRÍTICO", 97, "retirar", 0)
        price = self._make_price(0, 6.00)
        issues = _check_contradictions(product, batch, risk, "NO reponer", price)
        # score 97 + retirar = correcto, no debe disparar la contradicción 8
        divergence_issues = [i for i in issues if "DIVERGENCIA" in i]
        assert len(divergence_issues) == 0
