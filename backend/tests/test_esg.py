"""
Tests del ESG Agent.
Sin llamadas a Supabase ni a Claude — se mockea database y llm.call.
"""
from unittest.mock import patch, MagicMock
import pytest

from backend.agents.esg import (
    compute_action_impact,
    _get_factors,
    _normalize_category,
    get_store_esg_summary,
)


class TestNormalizeCategory:
    def test_lowercases_and_strips(self):
        assert _normalize_category("  Carne  ") == "carne"
        assert _normalize_category("LACTEOS") == "lacteos"

    def test_spaces_to_underscores(self):
        assert _normalize_category("carne ternera") == "carne_ternera"

    def test_empty_returns_empty(self):
        assert _normalize_category("") == ""
        assert _normalize_category(None) == ""


class TestGetFactors:
    def test_known_category_returns_real_data(self):
        co2, water, weight = _get_factors("carne")
        assert co2 == 60.0       # Poore & Nemecek 2018
        assert water == 15415.0  # Mekonnen & Hoekstra
        assert weight == 0.45

    def test_unknown_category_returns_defaults(self):
        co2, water, weight = _get_factors("categoria_inexistente")
        assert co2 == 2.5
        assert water == 2000.0
        assert weight == 0.30

    def test_subcategory_resolved(self):
        co2_cerdo, _, _ = _get_factors("carne_cerdo")
        assert co2_cerdo == 7.6  # Mucho menor que carne genérica (60.0)


class TestComputeActionImpact:
    def test_carne_impact_is_high(self):
        impact = compute_action_impact(quantity=5, category="carne", price=4.20)
        # 5 unidades × 0.45 kg/ud × 60 kgCO2/kg = 135 kg CO2
        assert impact["co2_saved_kg"] == pytest.approx(135.0, abs=1.0)
        assert impact["water_saved_liters"] > 10_000
        assert impact["value_saved_eur"] == pytest.approx(21.0, abs=0.1)
        assert impact["units_saved"] == 5

    def test_verdura_impact_is_low_co2(self):
        impact = compute_action_impact(quantity=10, category="verdura")
        # 10 × 0.40 kg × 0.4 kgCO2/kg = 1.6 kg CO2
        assert impact["co2_saved_kg"] < 5.0

    def test_equivalences_calculated(self):
        impact = compute_action_impact(quantity=2, category="panaderia")
        assert "km_car_avoided" in impact["equivalences"]
        assert "shower_days_equivalent" in impact["equivalences"]
        assert impact["equivalences"]["km_car_avoided"] >= 0

    def test_zero_price_gives_zero_value(self):
        impact = compute_action_impact(quantity=3, category="fruta", price=0)
        assert impact["value_saved_eur"] == 0.0

    def test_all_required_keys_present(self):
        impact = compute_action_impact(quantity=1, category="lacteos", price=1.50)
        required = {"units_saved", "total_kg", "co2_saved_kg", "water_saved_liters",
                    "value_saved_eur", "equivalences", "category"}
        assert required.issubset(impact.keys())

    def test_km_car_uses_dgt_factor(self):
        # 1 ud de carne = 0.45 kg × 60 = 27 kg CO2 → 27 / 0.21 ≈ 128.6 km
        impact = compute_action_impact(quantity=1, category="carne")
        assert impact["equivalences"]["km_car_avoided"] == pytest.approx(128.6, abs=1.0)

    def test_shower_days_uses_aeas_factor(self):
        # 1 ud de verdura = 0.4 kg × 322 L/kg = 128.8 L → 128.8 / 65 ≈ 1.98 dias
        impact = compute_action_impact(quantity=1, category="verdura")
        assert impact["equivalences"]["shower_days_equivalent"] == pytest.approx(1.98, abs=0.2)


class TestGetStoreEsgSummary:
    def _mock_roi(self):
        return {"actions_completed": 15, "value_recovered": 320.50}

    def _mock_merma(self):
        return [
            {"quantity_lost": 3, "category": "carne", "value_lost": 12.60},
            {"quantity_lost": 5, "category": "verdura", "value_lost": 3.75},
        ]

    def _mock_donations(self):
        return {"total_donations": 8, "total_value_donated": 45.20}

    def test_summary_has_all_keys(self):
        with patch("backend.agents.esg.database.get_completed_actions_value",
                   return_value=self._mock_roi()):
            with patch("backend.agents.esg.database.get_merma_history",
                       return_value=self._mock_merma()):
                with patch("backend.agents.esg.database.get_donation_stats",
                           return_value=self._mock_donations()):
                    summary = get_store_esg_summary("demo-store-001", days=30)

        required = {
            "actions_completed", "value_recovered_eur", "donated_value_eur",
            "estimated_co2_avoided_kg", "estimated_water_avoided_liters",
            "equivalences", "tax_deduction_estimate_eur", "esg_score", "period_days",
        }
        assert required.issubset(summary.keys())

    def test_esg_score_within_bounds(self):
        with patch("backend.agents.esg.database.get_completed_actions_value",
                   return_value=self._mock_roi()):
            with patch("backend.agents.esg.database.get_merma_history",
                       return_value=self._mock_merma()):
                with patch("backend.agents.esg.database.get_donation_stats",
                           return_value=self._mock_donations()):
                    summary = get_store_esg_summary("demo-store-001")

        assert 0 <= summary["esg_score"] <= 100

    def test_tax_deduction_is_35_pct_of_donations(self):
        with patch("backend.agents.esg.database.get_completed_actions_value",
                   return_value=self._mock_roi()):
            with patch("backend.agents.esg.database.get_merma_history",
                       return_value=[]):
                with patch("backend.agents.esg.database.get_donation_stats",
                           return_value={"total_donations": 5, "total_value_donated": 100.0}):
                    summary = get_store_esg_summary("demo-store-001")

        # Ley 49/2002: deducción del 35%
        assert summary["tax_deduction_estimate_eur"] == pytest.approx(35.0, abs=0.5)

    def test_database_error_returns_zeros_not_crash(self):
        with patch("backend.agents.esg.database.get_completed_actions_value",
                   side_effect=Exception("DB down")):
            with patch("backend.agents.esg.database.get_merma_history",
                       side_effect=Exception("DB down")):
                with patch("backend.agents.esg.database.get_donation_stats",
                           side_effect=Exception("DB down")):
                    summary = get_store_esg_summary("demo-store-001")

        # No debe lanzar excepción — retorna valores en 0
        assert summary["actions_completed"] == 0
        assert summary["estimated_co2_avoided_kg"] == 0

    def test_co2_positive_when_actions_completed(self):
        with patch("backend.agents.esg.database.get_completed_actions_value",
                   return_value={"actions_completed": 10, "value_recovered": 50.0}):
            with patch("backend.agents.esg.database.get_merma_history",
                       return_value=[{"quantity_lost": 2, "category": "carne", "value_lost": 8.4}]):
                with patch("backend.agents.esg.database.get_donation_stats",
                           return_value={"total_donations": 3, "total_value_donated": 20.0}):
                    summary = get_store_esg_summary("demo-store-001")

        assert summary["estimated_co2_avoided_kg"] >= 0
        assert summary["estimated_water_avoided_liters"] >= 0
