"""Tests del Knowledge Base — sin red."""
from backend.core.knowledge import query, get_regulations_for_category, get_context_for_decision


class TestQuery:
    def test_carne_query(self):
        results = query("temperatura carne fresca retirar")
        assert len(results) > 0
        assert any("carne" in r.lower() or "fresca" in r.lower() for r in results)

    def test_pescado_query(self):
        results = query("salmón caduca merluza temperatura")
        assert len(results) > 0
        assert any("pescado" in r.lower() or "salmón" in r.lower() for r in results)

    def test_donacion_query(self):
        results = query("donar banco de alimentos descarte")
        assert len(results) > 0
        assert any("donación" in r.lower() or "banco" in r.lower() for r in results)

    def test_empty_query_returns_results(self):
        # Should return nothing meaningful but not crash
        results = query("")
        assert isinstance(results, list)

    def test_top_k_respected(self):
        results = query("carne pescado leche panadería verdura caducidad", top_k=2)
        assert len(results) <= 2

    def test_unrelated_query_returns_empty(self):
        results = query("xyz123 foobar irrelevant garbage")
        assert results == []


class TestGetRegulationsForCategory:
    def test_carne(self):
        reg = get_regulations_for_category("carne")
        assert len(reg) > 0
        assert "carne" in reg.lower() or "FEFO" in reg

    def test_pescado(self):
        reg = get_regulations_for_category("pescado")
        assert len(reg) > 0

    def test_lacteos(self):
        reg = get_regulations_for_category("lacteos")
        assert len(reg) > 0

    def test_panaderia(self):
        reg = get_regulations_for_category("panaderia")
        assert len(reg) > 0

    def test_unknown_category_returns_general(self):
        reg = get_regulations_for_category("electrodomesticos")
        assert len(reg) > 0  # Falls back to general


class TestGetContextForDecision:
    def test_expired_product_has_alert(self):
        ctx = get_context_for_decision("carne", days_left=0, action_being_considered="retirar")
        assert "ALERTA" in ctx or "caducidad" in ctx.lower()

    def test_donation_includes_donation_info(self):
        ctx = get_context_for_decision("panaderia", days_left=1, action_being_considered="donar")
        assert "donación" in ctx.lower() or "banco" in ctx.lower()

    def test_discount_includes_legal_info(self):
        ctx = get_context_for_decision("lacteos", days_left=2, action_being_considered="rebajar")
        assert "descuento" in ctx.lower() or "precio" in ctx.lower()


class TestKnowledgeBaseEnrichment:
    def test_statistics_entry_returns_eurostat_data(self):
        results = query("porcentaje merma retail benchmark eurostat")
        assert len(results) > 0
        combined = " ".join(results).lower()
        assert "8%" in combined or "retail" in combined or "eurostat" in combined

    def test_csrd_query_returns_omnibus_info(self):
        results = query("csrd obligatorio normativa esg 2026")
        assert len(results) > 0
        combined = " ".join(results).lower()
        assert "ómnibus" in combined or "omnibus" in combined or "pyme" in combined

    def test_competitor_query_returns_winnow(self):
        results = query("competidor mercado winnow diferencial")
        assert len(results) > 0
        combined = " ".join(results).lower()
        assert "winnow" in combined or "wasteless" in combined

    def test_csrd_entry_has_correct_threshold(self):
        results = query("csrd umbral empleados")
        combined = " ".join(results)
        assert "1.000" in combined or "1000" in combined or "450" in combined

    def test_statistics_entry_has_fruit_percentage(self):
        results = query("frutas estadísticas porcentaje desperdiciadas")
        combined = " ".join(results).lower()
        assert "27%" in combined or "frutas" in combined or "verdura" in combined
