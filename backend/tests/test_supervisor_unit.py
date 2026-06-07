"""
Tests unitarios del Supervisor — sin red ni LLM real.
Verifica que el loop agéntico construye herramientas correctamente y
que el executor maneja cada herramienta de forma apropiada.
"""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, call
import json
import pytest

from backend.agents.supervisor import _make_executor, SUPERVISOR_TOOLS

STORE_ID = "demo-store-001"


class TestSupervisorTools:
    def test_tools_have_required_fields(self):
        for tool in SUPERVISOR_TOOLS:
            assert "name" in tool, f"Tool missing 'name'"
            assert "description" in tool, f"Tool '{tool.get('name')}' missing 'description'"
            assert "input_schema" in tool, f"Tool '{tool.get('name')}' missing 'input_schema'"
            assert "type" in tool["input_schema"]
            assert "properties" in tool["input_schema"]

    def test_all_required_tools_present(self):
        names = {t["name"] for t in SUPERVISOR_TOOLS}
        required = {
            "think",  # Anthropic think tool — patrón agéntico documentado (+54% en τ-bench)
            "get_expiring_batches",
            "get_warehouse_stock",
            "recall_memory",
            "store_memory",
            "evaluate_product_risk",
            "calculate_discount",
            "create_action",
            "get_pending_actions",
            "search_food_regulations",
            "get_day_context",
            "get_merma_history",
            "evaluate_all_products_parallel",
            "get_supplier_stats",
            "get_order_suggestions",
            "get_roi",
        }
        assert required.issubset(names), f"Missing tools: {required - names}"

    def test_think_tool_schema_is_valid(self):
        think = next(t for t in SUPERVISOR_TOOLS if t["name"] == "think")
        assert "thought" in think["input_schema"]["properties"]
        assert "thought" in think["input_schema"].get("required", [])

    def test_think_tool_has_no_side_effects(self):
        executor = _make_executor(STORE_ID)
        result = executor("think", {"thought": "¿Debo rebajar o retirar este producto?"})
        assert result["ok"] is True
        assert "thought_logged" in result

    def test_create_action_tool_has_enum_for_action_type(self):
        tool = next(t for t in SUPERVISOR_TOOLS if t["name"] == "create_action")
        action_type_prop = tool["input_schema"]["properties"]["action_type"]
        assert "enum" in action_type_prop
        assert "rebajar" in action_type_prop["enum"]
        assert "retirar" in action_type_prop["enum"]


class TestSupervisorExecutor:
    def _exec(self):
        return _make_executor(STORE_ID)

    def test_get_expiring_batches(self):
        mock_batches = [
            {
                "id": "b-001",
                "product_id": "p-001",
                "expiry_date": date.today().isoformat(),
                "quantity": 8,
                "products": {"name": "Baguette", "category": "panaderia"},
            }
        ]
        with patch("backend.agents.supervisor.database.get_batches_expiring_soon", return_value=mock_batches):
            result = self._exec()("get_expiring_batches", {"days": 3})
        assert result["count"] == 1
        assert result["batches"][0]["days_left"] == 0

    def test_get_expiring_batches_filters_category(self):
        mock_batches = [
            {
                "id": "b-001",
                "expiry_date": (date.today() + timedelta(days=2)).isoformat(),
                "quantity": 5,
                "products": {"category": "carne"},
            },
            {
                "id": "b-002",
                "expiry_date": (date.today() + timedelta(days=3)).isoformat(),
                "quantity": 10,
                "products": {"category": "lacteos"},
            },
        ]
        with patch("backend.agents.supervisor.database.get_batches_expiring_soon", return_value=mock_batches):
            result = self._exec()("get_expiring_batches", {"days": 7, "category": "carne"})
        assert result["count"] == 1
        assert result["batches"][0]["id"] == "b-001"

    def test_get_warehouse_stock(self):
        with patch("backend.agents.supervisor.database.get_warehouse_stock", return_value=15):
            result = self._exec()("get_warehouse_stock", {"product_id": "p-001"})
        assert result["warehouse_qty"] == 15
        assert result["product_id"] == "p-001"

    def test_recall_memory_found(self):
        with patch("backend.agents.supervisor.mem.recall", return_value="alta en lunes"):
            result = self._exec()("recall_memory", {"pattern_key": "categoria_panaderia_velocidad"})
        assert result["found"] is True
        assert result["value"] == "alta en lunes"

    def test_recall_memory_not_found(self):
        with patch("backend.agents.supervisor.mem.recall", return_value=None):
            result = self._exec()("recall_memory", {"pattern_key": "clave_inexistente"})
        assert result["found"] is False
        assert result["value"] is None

    def test_store_memory(self):
        with patch("backend.agents.supervisor.mem.remember") as mock:
            result = self._exec()("store_memory", {
                "pattern_key": "test_key",
                "pattern_value": "test_value",
            })
        assert result["stored"] is True
        mock.assert_called_once_with(STORE_ID, "test_key", "test_value")

    def test_search_food_regulations(self):
        with patch("backend.agents.supervisor.knowledge.query",
                   return_value=["Carne fresca: temperatura máxima 4°C..."]):
            result = self._exec()("search_food_regulations", {"query": "temperatura carne"})
        assert result["count"] == 1
        assert len(result["results"]) == 1

    def test_get_day_context_has_required_fields(self):
        with patch("backend.agents.supervisor.database.get_latest_brief", return_value=None):
            result = self._exec()("get_day_context", {})
        assert "date" in result
        assert "weekday" in result
        assert "hour" in result
        assert "is_weekend" in result

    def test_create_action_blocks_duplicate(self):
        existing_actions = [{"batch_id": "b-001", "status": "pending"}]
        with patch("backend.agents.supervisor.database.get_pending_actions", return_value=existing_actions):
            result = self._exec()("create_action", {
                "store_id": STORE_ID,
                "batch_id": "b-001",
                "action_type": "rebajar",
                "priority_score": 90,
                "notes": "test",
            })
        assert result["created"] is False
        assert "duplicado" in result["reason"].lower() or "Ya existe" in result["reason"]

    def test_create_action_creates_when_no_duplicate(self):
        with patch("backend.agents.supervisor.database.get_pending_actions", return_value=[]):
            with patch("backend.agents.supervisor.database.create_action",
                       return_value={"id": "action-123"}):
                result = self._exec()("create_action", {
                    "store_id": STORE_ID,
                    "batch_id": "b-NEW",
                    "action_type": "rebajar",
                    "priority_score": 85,
                    "notes": "Rebajar 40%",
                })
        assert result["created"] is True
        assert result["action_id"] == "action-123"

    def test_get_supplier_stats_returns_list(self):
        mock_stats = [
            {"id": "sup-001", "name": "Horno San Luis", "avg_merma_pct": 16.3,
             "product_count": 3, "risk": "ALTO", "contact": "", "products": [], "period": "2025-05"},
            {"id": "sup-004", "name": "Lácteos Cantabria", "avg_merma_pct": 6.7,
             "product_count": 4, "risk": "BAJO", "contact": "", "products": [], "period": "2025-05"},
        ]
        with patch("backend.agents.supervisor.database.get_supplier_stats", return_value=mock_stats):
            result = self._exec()("get_supplier_stats", {})
        assert result["count"] == 2
        assert result["top_risk"]["name"] == "Horno San Luis"
        assert "suppliers" in result

    def test_get_order_suggestions_returns_count_and_value(self):
        mock_suggestions = [
            {"product_id": "p-001", "product_name": "Baguette", "order_qty": 20,
             "avg_daily_loss": 0.7, "estimated_value": 24.0},
            {"product_id": "p-002", "product_name": "Yogur", "order_qty": 12,
             "avg_daily_loss": 0.4, "estimated_value": 9.6},
        ]
        with patch("backend.agents.supervisor.database.get_order_suggestions",
                   return_value=mock_suggestions):
            result = self._exec()("get_order_suggestions", {})
        assert result["count"] == 2
        assert result["total_estimated_value"] == pytest.approx(33.6, abs=0.01)
        assert len(result["suggestions"]) == 2

    def test_get_roi_returns_value_recovered(self):
        """get_roi mide la merma evitada: valor recuperado por acciones completadas."""
        mock_roi = {
            "actions_completed": 5,
            "value_recovered": 47.30,
            "cost_recovered": 22.10,
            "period_days": 7,
        }
        with patch("backend.agents.supervisor.database.get_completed_actions_value",
                   return_value=mock_roi):
            result = self._exec()("get_roi", {"days": 7})
        assert result["actions_completed"] == 5
        assert result["value_recovered"] == pytest.approx(47.30)
        assert result["period_days"] == 7

    def test_get_roi_default_days_is_7(self):
        mock_roi = {"actions_completed": 0, "value_recovered": 0.0,
                    "cost_recovered": 0.0, "period_days": 7}
        with patch("backend.agents.supervisor.database.get_completed_actions_value",
                   return_value=mock_roi) as mock_fn:
            self._exec()("get_roi", {})
        mock_fn.assert_called_once_with(STORE_ID, days=7)

    def test_all_16_tools_present(self):
        """Kuine tiene al menos 16 tools. Actualizar si se añaden más."""
        assert len(SUPERVISOR_TOOLS) >= 16
        names = {t["name"] for t in SUPERVISOR_TOOLS}
        assert "get_roi" in names
        assert "get_order_suggestions" in names
        assert "get_store_comparison" in names

    def test_unknown_tool_returns_error(self):
        result = self._exec()("herramienta_fantasma", {})
        assert "error" in result

    def test_evaluate_all_products_parallel_returns_stats_and_results(self):
        mock_results = [
            {"batch_id": "b-001", "score": 95, "risk_level": "CRÍTICO",
             "action": "rebajar", "product_name": "Baguette", "total_value_at_risk": 9.6},
        ]
        mock_stats = {
            "total": 1, "critical": 1, "high": 0, "medium": 0, "low": 0,
            "total_value_at_risk": 9.6, "actions_needed": 1,
        }
        with patch("backend.agents.parallel_evaluator.database.get_batches_expiring_soon",
                   return_value=[]):
            # El executor importa evaluate_all_parallel en tiempo de ejecución
            # — patcharla directamente en el módulo
            import backend.agents.parallel_evaluator as pe_mod
            original = pe_mod.evaluate_all_parallel
            pe_mod.evaluate_all_parallel = lambda *a, **kw: mock_results

            import backend.agents.parallel_evaluator as pe_stats_mod
            original_stats = pe_stats_mod.summary_stats
            pe_stats_mod.summary_stats = lambda *a, **kw: mock_stats

            try:
                result = self._exec()("evaluate_all_products_parallel", {"days": 7})
            finally:
                pe_mod.evaluate_all_parallel = original
                pe_stats_mod.summary_stats = original_stats

        assert "stats" in result
        assert "results" in result
        assert result["total_evaluated"] == 1

    def test_evaluate_product_risk_calls_evaluator(self):
        mock_result = {
            "risk_level": "CRÍTICO",
            "score": 95,
            "action": "rebajar",
            "price_adjustment_pct": 50,
            "reasoning": "Caduca mañana.",
            "thinking_summary": "",
        }
        with patch("backend.agents.supervisor.evaluator.evaluate", return_value=mock_result):
            result = self._exec()("evaluate_product_risk", {
                "product_id": "p-001",
                "product_name": "Baguette",
                "category": "panaderia",
                "price": 1.20,
                "cost": 0.45,
                "days_left": 1,
                "quantity": 8,
                "warehouse_qty": 0,
            })
        assert result["risk_level"] == "CRÍTICO"
        assert result["score"] == 95

    def test_get_order_suggestions_returns_list(self):
        mock_suggestions = [
            {
                "product_id": "p-001",
                "product_name": "Baguette artesana",
                "category": "panaderia",
                "pasillo": "A1",
                "avg_daily_loss": 1.4,
                "suggested_weekly_qty": 10,
                "current_warehouse_stock": 4,
                "order_qty": 6,
                "estimated_value": 7.2,
            }
        ]
        with patch("backend.agents.supervisor.database.get_order_suggestions", return_value=mock_suggestions):
            result = self._exec()("get_order_suggestions", {})
        assert result["count"] == 1
        assert result["total_estimated_value"] == 7.2
        assert result["suggestions"][0]["product_name"] == "Baguette artesana"

    def test_get_order_suggestions_empty_returns_zero(self):
        with patch("backend.agents.supervisor.database.get_order_suggestions", return_value=[]):
            result = self._exec()("get_order_suggestions", {})
        assert result["count"] == 0
        assert result["total_estimated_value"] == 0
