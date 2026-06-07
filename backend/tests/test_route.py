"""Tests del Route Agent — sin red ni LLM."""
from datetime import date, timedelta
import pytest
from backend.agents.route import generate, format_route_message, format_route_html


def _make_batch_with_product(product_id: str, pasillo: str, days: int, qty: int):
    today = date.today()
    return {
        "id": f"b-{product_id}",
        "product_id": product_id,
        "expiry_date": (today + timedelta(days=days)).isoformat(),
        "quantity": qty,
        "status": "active",
        "products": {
            "id": product_id,
            "name": f"Producto {product_id}",
            "category": "test",
            "pasillo": pasillo,
            "estanteria": "1",
            "nivel": "1",
            "price": 2.00,
            "cost": 0.80,
        },
    }


def _make_risk(risk_level: str, score: int, action: str, days: int):
    return {
        "risk_level": risk_level,
        "score": score,
        "action": action,
        "days_left": days,
        "reasoning": "test",
        "price_adjustment_pct": 30,
    }


class TestGenerate:
    def test_groups_by_pasillo(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 5), _make_risk("CRÍTICO", 90, "rebajar", 2)),
            (_make_batch_with_product("p-2", "1", 3, 8), _make_risk("ALTO", 70, "rebajar", 3)),
            (_make_batch_with_product("p-3", "2", 5, 10), _make_risk("MEDIO", 45, "revisar", 5)),
        ]
        route = generate("demo-store-001", reports)
        assert "1" in route["pasillos"]
        assert "2" in route["pasillos"]
        assert len(route["pasillos"]["1"]) == 2
        assert len(route["pasillos"]["2"]) == 1

    def test_critical_sorted_first_within_pasillo(self):
        reports = [
            (_make_batch_with_product("p-a", "1", 5, 10), _make_risk("MEDIO", 45, "revisar", 5)),
            (_make_batch_with_product("p-b", "1", 1, 3), _make_risk("CRÍTICO", 95, "rebajar", 1)),
        ]
        route = generate("demo-store-001", reports)
        items = route["pasillos"]["1"]
        assert items[0]["risk_level"] == "CRÍTICO"

    def test_total_value_at_risk_calculated(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 10), _make_risk("CRÍTICO", 90, "rebajar", 2)),
        ]
        route = generate("demo-store-001", reports)
        # 10 qty * 2.00 price = 20.00
        assert route["total_value_at_risk"] == 20.00

    def test_empty_reports(self):
        route = generate("demo-store-001", [])
        assert route["total_actions"] == 0
        assert route["pasillos"] == {}

    def test_route_order_is_sorted(self):
        reports = [
            (_make_batch_with_product("p-3", "3", 2, 5), _make_risk("CRÍTICO", 90, "rebajar", 2)),
            (_make_batch_with_product("p-1", "1", 5, 8), _make_risk("BAJO", 20, "ok", 5)),
            (_make_batch_with_product("p-2", "2", 3, 6), _make_risk("ALTO", 70, "rebajar", 3)),
        ]
        route = generate("demo-store-001", reports)
        # TSP nearest-neighbor: todos los pasillos presentes en la ruta (orden optimizado, no necesariamente 1→2→3)
        assert set(route["route_order"]) == {"1", "2", "3"}
        assert len(route["route_order"]) == 3

    def test_critical_count(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 0, 5), _make_risk("CRÍTICO", 100, "retirar", 0)),
            (_make_batch_with_product("p-2", "2", 1, 3), _make_risk("CRÍTICO", 92, "rebajar", 1)),
            (_make_batch_with_product("p-3", "3", 4, 8), _make_risk("MEDIO", 45, "revisar", 4)),
        ]
        route = generate("demo-store-001", reports)
        assert route["critical_count"] == 2


class TestFormatRouteMessage:
    def test_empty_route(self):
        msg = format_route_message({})
        assert "Sin ruta" in msg

    def test_route_message_contains_pasillo(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 5), _make_risk("CRÍTICO", 90, "rebajar", 2)),
        ]
        route = generate("demo-store-001", reports)
        msg = format_route_message(route)
        assert "Pasillo 1" in msg.upper() or "PASILLO 1" in msg

    def test_no_markdown_asterisks(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 5), _make_risk("ALTO", 70, "rebajar", 2)),
        ]
        route = generate("demo-store-001", reports)
        msg = format_route_message(route)
        assert "**" not in msg
        assert "__" not in msg

    def test_includes_estimated_minutes(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 5), _make_risk("CRÍTICO", 90, "rebajar", 2)),
        ]
        route = generate("demo-store-001", reports)
        msg = format_route_message(route)
        assert "min" in msg.lower()

    def test_includes_value_at_risk(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 10), _make_risk("ALTO", 70, "rebajar", 2)),
        ]
        route = generate("demo-store-001", reports)
        msg = format_route_message(route)
        assert "20" in msg or "euro" in msg.lower()

    def test_action_appears_in_message(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 5), _make_risk("CRÍTICO", 90, "retirar", 2)),
        ]
        route = generate("demo-store-001", reports)
        msg = format_route_message(route)
        assert "RETIRAR" in msg


class TestGenerateResultKeys:
    def test_has_all_required_keys(self):
        route = generate("demo-store-001", [])
        required = {"pasillos", "total_actions", "total_value_at_risk", "estimated_minutes",
                    "route_order", "critical_count"}
        assert required.issubset(route.keys())

    def test_total_actions_matches_sum(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 5), _make_risk("CRÍTICO", 90, "rebajar", 2)),
            (_make_batch_with_product("p-2", "2", 3, 5), _make_risk("ALTO", 70, "rebajar", 3)),
        ]
        route = generate("demo-store-001", reports)
        assert route["total_actions"] == 2

    def test_estimated_minutes_positive(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 5), _make_risk("CRÍTICO", 90, "donar", 2)),
        ]
        route = generate("demo-store-001", reports)
        assert route["estimated_minutes"] > 0

    def test_item_keys_complete(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 5), _make_risk("ALTO", 70, "rebajar", 2)),
        ]
        route = generate("demo-store-001", reports)
        item = route["pasillos"]["1"][0]
        required_item_keys = {"batch_id", "product_id", "product_name", "expiry_date",
                               "days_left", "quantity", "value_at_risk", "risk_level",
                               "score", "action", "reasoning", "minutes_estimated"}
        assert required_item_keys.issubset(item.keys())

    def test_days_left_calculated_correctly(self):
        today = date.today()
        batch = {
            "id": "b-test",
            "product_id": "p-test",
            "expiry_date": (today + timedelta(days=5)).isoformat(),
            "quantity": 1,
            "status": "active",
            "products": {"id": "p-test", "name": "Test", "category": "test",
                         "pasillo": "1", "estanteria": "1", "nivel": "1",
                         "price": 1.0, "cost": 0.5},
        }
        risk = _make_risk("BAJO", 20, "ok", 5)
        route = generate("demo-store-001", [(batch, risk)])
        item = route["pasillos"]["1"][0]
        assert item["days_left"] == 5


class TestFormatRouteHtml:
    def test_empty_route_returns_sin_ruta(self):
        msg = format_route_html({})
        assert "Sin ruta" in msg

    def test_html_contains_bold_tags(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 5), _make_risk("CRÍTICO", 90, "rebajar", 2)),
        ]
        route = generate("demo-store-001", reports)
        msg = format_route_html(route)
        assert "<b>" in msg

    def test_html_contains_pasillo(self):
        reports = [
            (_make_batch_with_product("p-1", "3", 2, 5), _make_risk("ALTO", 70, "rebajar", 2)),
        ]
        route = generate("demo-store-001", reports)
        msg = format_route_html(route)
        assert "Pasillo 3" in msg or "PASILLO 3" in msg.upper()

    def test_html_critical_has_red_icon(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 1, 5), _make_risk("CRÍTICO", 95, "retirar", 1)),
        ]
        route = generate("demo-store-001", reports)
        msg = format_route_html(route)
        assert "🔴" in msg

    def test_html_no_plain_asterisks(self):
        reports = [
            (_make_batch_with_product("p-1", "1", 2, 5), _make_risk("MEDIO", 50, "revisar", 2)),
        ]
        route = generate("demo-store-001", reports)
        msg = format_route_html(route)
        assert "**" not in msg
