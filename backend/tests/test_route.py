"""Tests del Route Agent — sin red ni LLM."""
from datetime import date, timedelta
import pytest
from backend.agents.route import generate, format_route_message


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
        assert route["route_order"] == ["1", "2", "3"]

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
