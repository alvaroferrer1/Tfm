"""Tests for backend/core/pdf_generator.py — no Claude API, no Supabase."""
import pytest
from backend.core.pdf_generator import (
    _safe,
    generate_brief_pdf,
    generate_weekly_pdf,
    generate_monthly_pdf,
)


# ── _safe() ──────────────────────────────────────────────────────────────────

class TestSafeFunction:
    def test_strips_euro_sign(self):
        assert "EUR" in _safe("84.50€")
        assert "€" not in _safe("84.50€")

    def test_strips_em_dash(self):
        result = _safe("Semana — mayo")
        assert "—" not in result
        assert "-" in result

    def test_strips_middle_dot(self):
        result = _safe("Super · Martinez")
        assert "·" not in result

    def test_strips_non_ascii(self):
        result = _safe("café résumé naïve")
        assert all(ord(c) < 128 for c in result)

    def test_preserves_ascii(self):
        text = "MermaOps 2026 - 100% OK"
        assert _safe(text) == text

    def test_handles_accents(self):
        result = _safe("Análisis de Kuine")
        assert "é" not in result
        # normalized: á → a, etc.
        assert len(result) > 0

    def test_replaces_emoji_labels(self):
        result = _safe("🔴  PRODUCTOS CRÍTICOS")
        assert "🔴" not in result
        assert "[CRITICO]" in result

    def test_empty_string(self):
        assert _safe("") == ""

    def test_degree_symbol(self):
        result = _safe("28°C")
        assert "°" not in result
        assert "o" in result


# ── generate_brief_pdf() ─────────────────────────────────────────────────────

class TestGenerateBriefPdf:
    def test_returns_bytes(self):
        result = generate_brief_pdf("Kuine detecto 2 criticos.")
        assert isinstance(result, bytes)

    def test_is_valid_pdf(self):
        result = generate_brief_pdf("Texto del brief.")
        assert result[:4] == b"%PDF"
        assert b"%%EOF" in result[-20:]

    def test_minimum_size(self):
        result = generate_brief_pdf("x")
        assert len(result) > 1000  # Un PDF minimo tiene estructura

    def test_with_all_params(self):
        result = generate_brief_pdf(
            brief_text="Analisis completo del dia.",
            brief_date="2026-05-20",
            critical_count=3,
            high_count=5,
            value_at_risk=120.50,
            actions_count=8,
            route_minutes=45,
            store_name="Super Martinez",
        )
        assert isinstance(result, bytes)
        assert len(result) > 2000

    def test_with_critical_actions(self):
        actions = [
            {
                "batches": {
                    "expiry_date": "2026-05-21",
                    "products": {"name": "Merluza fresca", "pasillo": "4"},
                },
                "action_type": "donar",
                "priority_score": 95,
            }
        ]
        result = generate_brief_pdf(
            "Brief con critico.", critical_count=1, critical_actions=actions
        )
        assert isinstance(result, bytes)
        assert len(result) > 1500

    def test_euro_chars_dont_crash(self):
        result = generate_brief_pdf("Valor en riesgo: 84.50 EUR. Merma evitada: 320 EUR.")
        assert isinstance(result, bytes)

    def test_accented_store_name_doesnt_crash(self):
        result = generate_brief_pdf("Texto.", store_name="Supermercado García & Cía")
        assert isinstance(result, bytes)

    def test_empty_text_doesnt_crash(self):
        result = generate_brief_pdf("")
        assert isinstance(result, bytes)


# ── generate_weekly_pdf() ────────────────────────────────────────────────────

class TestGenerateWeeklyPdf:
    def test_returns_valid_pdf(self):
        result = generate_weekly_pdf("Informe semanal.")
        assert result[:4] == b"%PDF"

    def test_with_all_metrics(self):
        result = generate_weekly_pdf(
            report_text="Semana positiva.",
            week_start="2026-05-13",
            merma_eur=120.50,
            merma_qty=15,
            merma_evitada_eur=340.0,
            donated_qty=8,
            donated_value=95.0,
            store_name="Super Martinez",
        )
        assert isinstance(result, bytes)
        assert len(result) > 1500

    def test_roi_zero_when_no_merma(self):
        # merma_eur=0 → no ZeroDivisionError
        result = generate_weekly_pdf("Sin merma esta semana.", merma_eur=0.0)
        assert isinstance(result, bytes)


# ── generate_monthly_pdf() ───────────────────────────────────────────────────

class TestGenerateMonthlyPdf:
    def test_returns_valid_pdf(self):
        result = generate_monthly_pdf("Informe mensual.")
        assert result[:4] == b"%PDF"

    def test_roi_pct_zero_when_no_data(self):
        # merma_eur=0 y merma_evitada_eur=0 → no ZeroDivisionError
        result = generate_monthly_pdf("Primer mes.", merma_eur=0.0, merma_evitada_eur=0.0)
        assert isinstance(result, bytes)

    def test_with_month_label(self):
        result = generate_monthly_pdf("Mayo positivo.", month="Mayo 2026", merma_eur=500.0)
        assert isinstance(result, bytes)
