"""Tests for backend/core/telegram_formatter.py — no Claude API, no Supabase."""
import html
import pytest
from backend.core.telegram_formatter import (
    format_brief,
    format_actions,
    format_stats,
    format_merma,
    format_donaciones,
    format_proveedores,
    format_pedido,
    format_estado,
)

TELEGRAM_LIMIT = 4096


# ── Helpers ───────────────────────────────────────────────────────────────────

def _len(s: str) -> int:
    return len(s.encode("utf-8"))


def make_action(name="Merluza", pasillo="4", level="CRITICO", action="donar", score=90,
                days_left=1):
    return {
        "id": "a1",
        "action_type": action,
        "priority_score": score,
        "urgency_level": level,
        "batches": {
            "expiry_date": "2026-05-21",
            "quantity": 6,
            "products": {"name": name, "pasillo": pasillo, "category": "pescado"},
        },
        "notes": "",
    }


# ── format_brief() ────────────────────────────────────────────────────────────

class TestFormatBrief:
    def test_returns_string(self):
        result = format_brief("Kuine detecto 2 criticos.", "2026-05-20", 120.0, 5, 2, 3)
        assert isinstance(result, str)

    def test_within_telegram_limit(self):
        long_summary = "A" * 1000
        result = format_brief(long_summary, "2026-05-20", 9999.99, 10, 5, 8)
        assert _len(result) <= TELEGRAM_LIMIT

    def test_contains_html_tags(self):
        result = format_brief("Analisis.", "2026-05-20", 50.0, 3, 1, 2)
        assert "<b>" in result

    def test_escapes_special_html(self):
        result = format_brief("<script>alert('xss')</script>", "2026-05-20", 0, 0, 0, 0)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_shows_date(self):
        result = format_brief("ok", "2026-05-20", 0, 0, 0, 0)
        assert "2026-05-20" in result

    def test_shows_value_at_risk(self):
        result = format_brief("ok", "2026-05-20", 84.5, 0, 0, 0)
        assert "84" in result


# ── format_actions() ─────────────────────────────────────────────────────────

class TestFormatActions:
    def test_empty_returns_string(self):
        result = format_actions([])
        assert isinstance(result, str)

    def test_single_action(self):
        result = format_actions([make_action()])
        assert "Merluza" in result

    def test_critical_section_present(self):
        actions = [make_action(level="CRITICO"), make_action(name="Yogur", level="ALTO")]
        result = format_actions(actions)
        assert "CRIT" in result.upper() or "🔴" in result

    def test_within_limit_with_10_actions(self):
        actions = [make_action(name=f"Producto{i}") for i in range(10)]
        result = format_actions(actions)
        assert _len(result) <= TELEGRAM_LIMIT

    def test_escapes_product_name(self):
        result = format_actions([make_action(name="<b>Peligro</b>")])
        assert "<b>Peligro</b>" not in result
        assert "&lt;b&gt;" in result


# ── format_stats() ────────────────────────────────────────────────────────────

class TestFormatStats:
    def test_returns_string(self):
        result = format_stats(5, 2, 3, 4, 150.0, 80.0, 10, 45.0, "2026-05-20", "ALERTA")

        assert isinstance(result, str)

    def test_within_limit(self):
        result = format_stats(100, 50, 50, 30, 9999.0, 500.0, 100, 300.0, "2026-05-20", "NORMAL")
        assert _len(result) <= TELEGRAM_LIMIT

    def test_semaforo_visible(self):
        result = format_stats(0, 0, 0, 0, 0, 0, 0, 0, "2026-05-20", "NORMAL")
        assert "NORMAL" in result or "normal" in result.lower()


# ── format_merma() ────────────────────────────────────────────────────────────

class TestFormatMerma:
    def test_empty(self):
        result = format_merma([], 7)
        assert isinstance(result, str)

    def test_with_logs(self):
        # format_merma lee el nombre desde log["batches"]["products"]["name"]
        logs = [
            {"batches": {"products": {"name": "Pan integral"}},
             "quantity_lost": 3, "value_lost": 4.5,
             "reason": "caducado", "date": "2026-05-19"},
        ]
        result = format_merma(logs, 7)
        assert "Pan integral" in result

    def test_within_limit_many_logs(self):
        logs = [
            {"batches": {"products": {"name": f"P{i}"}},
             "quantity_lost": 1, "value_lost": 1.0,
             "reason": "caducado", "date": "2026-05-19"}
            for i in range(100)
        ]
        result = format_merma(logs, 30)
        assert _len(result) <= TELEGRAM_LIMIT

    def test_escapes_product_name(self):
        logs = [{"batches": {"products": {"name": "<img src=x>"}},
                 "quantity_lost": 1, "value_lost": 1.0,
                 "reason": "x", "date": "2026-05-19"}]
        result = format_merma(logs, 7)
        assert "<img" not in result


# ── format_proveedores() ──────────────────────────────────────────────────────

class TestFormatProveedores:
    def test_empty(self):
        result = format_proveedores([])
        assert isinstance(result, str)

    def test_single_supplier(self):
        result = format_proveedores([{"name": "Distribuciones SA", "avg_merma_pct": 12, "product_count": 5, "risk": "ALTO"}])
        assert "Distribuciones SA" in result

    def test_limits_to_20_suppliers(self):
        suppliers = [{"name": f"Prov{i}", "avg_merma_pct": 5, "product_count": 3, "risk": "BAJO"} for i in range(50)]
        result = format_proveedores(suppliers)
        # Should not include all 50
        assert result.count("Prov") <= 20

    def test_within_limit_20_suppliers(self):
        suppliers = [{"name": f"Proveedor numero {i} con nombre largo", "avg_merma_pct": 15,
                      "product_count": 10, "risk": "ALTO"} for i in range(20)]
        result = format_proveedores(suppliers)
        assert _len(result) <= TELEGRAM_LIMIT

    def test_escapes_supplier_name(self):
        result = format_proveedores([{"name": "<script>", "avg_merma_pct": 0, "product_count": 0, "risk": "BAJO"}])
        assert "<script>" not in result


# ── format_donaciones() ───────────────────────────────────────────────────────

class TestFormatDonaciones:
    def test_empty_dict(self):
        result = format_donaciones({})
        assert isinstance(result, str)

    def test_with_data(self):
        # format_donaciones usa total_donations, total_quantity, total_value_donated, by_entity
        stats = {
            "total_donations": 3,
            "total_quantity": 45,
            "total_value_donated": 128.5,
            "by_entity": {"Caritas": 30, "Cruz Roja": 15},
        }
        result = format_donaciones(stats)
        assert "Caritas" in result
        assert "128" in result

    def test_within_limit(self):
        stats = {
            "total_donations": 100,
            "total_quantity": 1000,
            "total_value_donated": 9999.99,
            "by_entity": {f"Org{i}": 10 for i in range(50)},
        }
        result = format_donaciones(stats)
        assert _len(result) <= TELEGRAM_LIMIT


# ── format_pedido() ───────────────────────────────────────────────────────────

class TestFormatPedido:
    def test_empty(self):
        result = format_pedido([])
        assert isinstance(result, str)

    def test_with_suggestions(self):
        # format_pedido usa product_name + order_qty
        sugs = [{"product_name": "Leche entera", "order_qty": 24, "estimated_value": 28.8, "reason": "stock bajo"}]
        result = format_pedido(sugs)
        assert "Leche" in result


# ── format_estado() ───────────────────────────────────────────────────────────

class TestFormatEstado:
    def test_empty_all(self):
        result = format_estado([], [], None, 0)
        assert isinstance(result, str)

    def test_with_pending_and_brief(self):
        brief = {"date": "2026-05-20", "summary": "Todo bajo control.", "critical_count": 1, "high_count": 2}
        result = format_estado([make_action()], [], brief, 45.0)
        assert "2026-05-20" in result or "Todo bajo" in result

    def test_within_limit(self):
        actions = [make_action(name=f"Prod{i}") for i in range(15)]
        result = format_estado(actions, [], None, 500.0)
        assert _len(result) <= TELEGRAM_LIMIT
