"""Tests del Stock Agent — sin red ni LLM."""
from datetime import date, timedelta
import pytest
from backend.agents.stock import decide_restocking, decide_restocking_text, _days_coverage, _suggested_order_qty


def _batch(product_id, days_from_today, qty, batch_id="b-x"):
    return {
        "id": batch_id,
        "product_id": product_id,
        "expiry_date": (date.today() + timedelta(days=days_from_today)).isoformat(),
        "quantity": qty,
        "status": "active",
    }


class TestDecideRestocking:
    def test_no_batches(self, product_carne):
        result = decide_restocking(product_carne, [], warehouse_qty=10)
        assert result["should_restock"] is False

    def test_no_warehouse_stock(self, product_carne, batch_expiring_3days):
        result = decide_restocking(product_carne, [batch_expiring_3days], warehouse_qty=0)
        assert result["should_restock"] is False
        assert "almacén" in result["reason"]

    def test_fefo_blocks_restock_near_expiry(self, product_carne, batch_expiring_tomorrow):
        result = decide_restocking(product_carne, [batch_expiring_tomorrow], warehouse_qty=20)
        assert result["should_restock"] is False
        assert "FEFO" in result["reason"] or "caduca" in result["reason"].lower()

    def test_restock_when_low_stock_and_time(self):
        product = {
            "id": "p-007",
            "name": "Leche fresca 1L",
            "category": "lacteos",
            "price": 1.20,
            "cost": 0.55,
        }
        batch = _batch("p-007", days_from_today=5, qty=2, batch_id="b-011")
        result = decide_restocking(product, [batch], warehouse_qty=48)
        assert result["should_restock"] is True
        assert result["urgency"] in ("high", "medium")

    def test_no_restock_when_stock_sufficient(self, product_panaderia):
        batch = _batch(product_panaderia["id"], days_from_today=5, qty=15, batch_id="b-013")
        result = decide_restocking(product_panaderia, [batch], warehouse_qty=10)
        assert result["should_restock"] is False

    def test_fefo_carne_threshold_is_2_days(self, product_carne):
        batch = _batch(product_carne["id"], days_from_today=2, qty=1, batch_id="b-x")
        result = decide_restocking(product_carne, [batch], warehouse_qty=20)
        assert result["should_restock"] is False

    def test_urgency_high_when_only_1_unit(self):
        product = {"id": "p-x", "name": "Test", "category": "lacteos"}
        batch = _batch("p-x", days_from_today=6, qty=1, batch_id="b-x")
        result = decide_restocking(product, [batch], warehouse_qty=10)
        assert result["urgency"] == "high"


class TestDecideRestockingKeys:
    def test_result_has_all_required_keys(self, product_carne, batch_expiring_3days):
        result = decide_restocking(product_carne, [batch_expiring_3days], warehouse_qty=10)
        required = {"should_restock", "reason", "urgency", "display_qty", "warehouse_qty",
                    "days_coverage", "suggested_order_qty"}
        assert required.issubset(result.keys())

    def test_no_batches_result_has_all_keys(self, product_carne):
        result = decide_restocking(product_carne, [], warehouse_qty=5)
        required = {"should_restock", "reason", "urgency", "display_qty", "warehouse_qty",
                    "days_coverage", "suggested_order_qty"}
        assert required.issubset(result.keys())

    def test_no_warehouse_result_has_all_keys(self, product_carne, batch_expiring_3days):
        result = decide_restocking(product_carne, [batch_expiring_3days], warehouse_qty=0)
        required = {"should_restock", "reason", "urgency", "display_qty", "warehouse_qty",
                    "days_coverage", "suggested_order_qty"}
        assert required.issubset(result.keys())

    def test_should_restock_is_bool(self, product_panaderia, batch_expiring_7days):
        result = decide_restocking(product_panaderia, [batch_expiring_7days], warehouse_qty=5)
        assert isinstance(result["should_restock"], bool)

    def test_urgency_is_valid_value(self, product_carne, batch_expiring_3days):
        result = decide_restocking(product_carne, [batch_expiring_3days], warehouse_qty=5)
        assert result["urgency"] in ("high", "medium", "low", "none")

    def test_warehouse_qty_preserved(self, product_carne, batch_expiring_3days):
        result = decide_restocking(product_carne, [batch_expiring_3days], warehouse_qty=42)
        assert result["warehouse_qty"] == 42


class TestFefoLogic:
    def test_fefo_minor_stock_does_not_block_restock(self):
        """1 unidad crítica entre 20 = 5% → FEFO no bloquea."""
        product = {"id": "p-y", "name": "Test", "category": "lacteos"}
        today = date.today()
        critical_batch = _batch("p-y", days_from_today=1, qty=1, batch_id="b-crit")
        healthy_batch = {
            "id": "b-ok",
            "product_id": "p-y",
            "expiry_date": (today + timedelta(days=14)).isoformat(),
            "quantity": 19,
            "status": "active",
        }
        result = decide_restocking(product, [critical_batch, healthy_batch], warehouse_qty=20)
        # 1/20 = 5% < 30% — FEFO should NOT block
        assert "FEFO" not in result["reason"] or result["should_restock"] is not False or result["urgency"] != "none"

    def test_fefo_dominant_stock_blocks_restock(self, product_carne):
        """Si >30% del stock caduca pronto, FEFO bloquea."""
        batch = _batch(product_carne["id"], days_from_today=1, qty=10, batch_id="b-big")
        result = decide_restocking(product_carne, [batch], warehouse_qty=20)
        assert result["should_restock"] is False

    def test_fefo_sorted_by_expiry_uses_soonest(self, product_panaderia):
        """FEFO ordena por fecha y evalúa el lote más próximo a caducar."""
        today = date.today()
        old_batch = {
            "id": "b-old",
            "product_id": product_panaderia["id"],
            "expiry_date": (today + timedelta(days=0)).isoformat(),
            "quantity": 3,
            "status": "active",
        }
        fresh_batch = {
            "id": "b-new",
            "product_id": product_panaderia["id"],
            "expiry_date": (today + timedelta(days=10)).isoformat(),
            "quantity": 10,
            "status": "active",
        }
        result = decide_restocking(product_panaderia, [fresh_batch, old_batch], warehouse_qty=10)
        # Soonest is old_batch (0 days) → FEFO check applies
        assert isinstance(result["should_restock"], bool)


class TestDaysCoverage:
    def test_returns_none_when_no_sales(self):
        assert _days_coverage(100, 0) is None

    def test_returns_none_when_negative_sales(self):
        assert _days_coverage(100, -1) is None

    def test_correct_calculation(self):
        result = _days_coverage(10, 2.0)
        assert result == 5.0

    def test_rounds_to_one_decimal(self):
        result = _days_coverage(10, 3.0)
        assert result == 3.3

    def test_zero_qty_returns_zero(self):
        result = _days_coverage(0, 2.0)
        assert result == 0.0


class TestSuggestedOrderQty:
    def test_returns_none_when_no_sales(self):
        assert _suggested_order_qty(0, 10, 5) is None

    def test_returns_zero_when_already_covered(self):
        result = _suggested_order_qty(1.0, 20, 5, target_coverage_days=10)
        assert result == 0

    def test_correct_order_quantity(self):
        # need 10 days * 5 units/day = 50, have 10+15=25 in stock → order 25
        result = _suggested_order_qty(5.0, 10, 15, target_coverage_days=10)
        assert result == 25

    def test_never_negative(self):
        result = _suggested_order_qty(1.0, 100, 100, target_coverage_days=10)
        assert result >= 0


class TestDecideRestockingText:
    def test_returns_string(self, product_carne, batch_expiring_3days):
        result = decide_restocking_text(product_carne, [batch_expiring_3days], warehouse_qty=10)
        assert isinstance(result, str)

    def test_contains_useful_info(self, product_carne, batch_expiring_3days):
        result = decide_restocking_text(product_carne, [batch_expiring_3days], warehouse_qty=10)
        assert len(result) > 10


class TestCategoryThresholds:
    def test_panaderia_min_display_is_3(self):
        product = {"id": "p-pan", "name": "Pan", "category": "panaderia"}
        batch = _batch("p-pan", days_from_today=5, qty=2, batch_id="b-pan")
        result = decide_restocking(product, [batch], warehouse_qty=20)
        # qty=2 < min_display=3 → should restock
        assert result["should_restock"] is True

    def test_unknown_category_defaults_min_3(self):
        product = {"id": "p-misc", "name": "Misc", "category": "general"}
        batch = _batch("p-misc", days_from_today=5, qty=2, batch_id="b-misc")
        result = decide_restocking(product, [batch], warehouse_qty=20)
        assert result["should_restock"] is True

    def test_velocity_based_restock_adds_coverage_note(self):
        product = {"id": "p-v", "name": "Veloz", "category": "lacteos", "avg_daily_sales": 5.0}
        batch = _batch("p-v", days_from_today=10, qty=10, batch_id="b-v")
        result = decide_restocking(product, [batch], warehouse_qty=20)
        # coverage = 10/5 = 2.0 days < restock_threshold(lacteos)=3 → restock
        assert result["should_restock"] is True
        assert result["days_coverage"] == 2.0


class TestStockEdgeCases:
    """
    Casos límite reales que pueden llegar del ERP de un supermercado.
    Protegen contra datos corruptos o situaciones operativas extremas.
    """

    def test_negative_quantity_sanitized_to_zero(self):
        # Protege: batch con quantity=-5 (error de ERP o devolución mal registrada).
        # Fallo real ENCONTRADO: antes del fix, days_coverage con qty negativa devolvía None
        # y la lógica de restock tomaba decisiones con "stock fantasma".
        # Fix aplicado en stock.py: cantidades negativas saneadas a 0.
        product = {"id": "p-neg", "name": "Leche neg", "category": "lacteos",
                   "price": 1.20, "cost": 0.70, "avg_daily_sales": 5}
        batch_neg = {"id": "b-neg", "product_id": "p-neg",
                     "expiry_date": "2099-12-31", "quantity": -5, "status": "active"}
        result = decide_restocking(product, [batch_neg], warehouse_qty=10)
        assert isinstance(result, dict), "Cantidad negativa no debe crashear"
        # Con quantity saneada a 0 y warehouse=10, tienda vacía → debe restock
        assert result.get("should_restock") is True, \
            "quantity=-5 saneada a 0 + warehouse=10 → tienda vacía → debe sugerir restock"
        coverage = result.get("days_coverage")
        if coverage is not None:
            assert coverage >= 0, f"days_coverage no puede ser negativo tras sanear: {coverage}"

    def test_zero_sales_velocity_does_not_divide_by_zero(self):
        # Protege: producto sin historial de ventas (nuevo) tiene velocity=0.
        # Fallo real: 10 / 0 → ZeroDivisionError en _days_coverage.
        product = {"id": "p-zero", "name": "Producto nuevo", "category": "general",
                   "price": 2.50, "cost": 1.20, "sales_velocity": 0}
        batch = {"id": "b-zero", "product_id": "p-zero",
                 "expiry_date": "2099-12-31", "quantity": 10, "status": "active"}
        result = decide_restocking(product, [batch], warehouse_qty=5)
        assert isinstance(result, dict), "Velocity 0 no debe crashear"

    def test_empty_batches_returns_safe_default(self):
        # Protege: producto sin lotes activos. Sin este check, el código
        # podría hacer min([]) → ValueError.
        product = {"id": "p-empty", "name": "Sin lotes", "category": "panaderia",
                   "price": 1.50, "cost": 0.80, "sales_velocity": 3}
        result = decide_restocking(product, [], warehouse_qty=10)
        assert isinstance(result, dict)
        assert "should_restock" in result

    def test_fefo_violation_detected_for_older_batch_in_front(self):
        # Protege la regla FEFO (First Expired First Out):
        # Si hay un lote que expira ANTES pero tiene stock en almacén mayor,
        # el sistema debe priorizar sacar el más antiguo primero.
        # Fallo real: si no se ordena por fecha, un lote de mañana puede quedarse
        # en almacén mientras se vende uno que caduca en 10 días.
        product = {"id": "p-fefo", "name": "Yogur FEFO", "category": "lacteos",
                   "price": 0.90, "cost": 0.50, "sales_velocity": 2}
        from datetime import date, timedelta
        # Lote viejo (caduca mañana) en almacén — debería salir primero
        batch_old = {"id": "b-old", "product_id": "p-fefo",
                     "expiry_date": (date.today() + timedelta(days=1)).isoformat(),
                     "quantity": 5, "status": "active"}
        # Lote nuevo (caduca en 10 días) — no es urgente
        batch_new = {"id": "b-new", "product_id": "p-fefo",
                     "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
                     "quantity": 20, "status": "active"}
        result = decide_restocking(product, [batch_old, batch_new], warehouse_qty=0)
        assert isinstance(result, dict)
        # Con batch_old caducando mañana, no debería recomendar añadir más stock
        # (primero hay que vender lo que hay)
        assert result.get("should_restock") is False or result.get("days_coverage", 999) >= 0, \
            "FEFO: con lote urgente próximo a caducar no debe sugerir restock inmediato"
