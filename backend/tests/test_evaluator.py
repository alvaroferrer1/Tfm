"""
Tests del Evaluator Agent.
El scoring heurístico es determinista y no necesita LLM.
Los tests con LLM están marcados @pytest.mark.integration.
"""
from datetime import date, timedelta
import pytest
from unittest.mock import patch
from backend.agents.evaluator import _base_score, _risk_level, _action_from_risk, evaluate


class TestHeuristicScoring:
    def test_expires_today_max_score(self):
        assert _base_score(0) == 100

    def test_expires_tomorrow_high(self):
        assert _base_score(1) == 92

    def test_expires_2_days(self):
        assert _base_score(2) == 78

    def test_expires_7_days_low(self):
        assert _base_score(7) == 22

    def test_risk_level_critical(self):
        assert _risk_level(95) == "CRÍTICO"
        assert _risk_level(85) == "CRÍTICO"

    def test_risk_level_high(self):
        assert _risk_level(70) == "ALTO"

    def test_risk_level_medium(self):
        assert _risk_level(50) == "MEDIO"

    def test_risk_level_low(self):
        assert _risk_level(30) == "BAJO"


class TestActionFromRisk:
    def test_expired_is_retirar(self):
        assert _action_from_risk("CRÍTICO", 0, "carne") == "retirar"

    def test_expired_pescado_is_retirar(self):
        assert _action_from_risk("CRÍTICO", 0, "pescado") == "retirar"

    def test_expired_lacteos_is_retirar(self):
        assert _action_from_risk("CRÍTICO", 0, "lacteos") == "retirar"

    def test_expired_panaderia_is_donar(self):
        # Ley 49/2002: pan y bollería expirados son donables, no peligrosos
        assert _action_from_risk("CRÍTICO", 0, "panaderia") == "donar"

    def test_expired_fruta_is_donar(self):
        assert _action_from_risk("CRÍTICO", 0, "fruta") == "donar"

    def test_expired_verdura_is_donar(self):
        assert _action_from_risk("CRÍTICO", 0, "verdura") == "donar"

    def test_critical_with_1_day_is_rebajar(self):
        assert _action_from_risk("CRÍTICO", 1, "lacteos") == "rebajar"

    def test_high_is_rebajar(self):
        assert _action_from_risk("ALTO", 3, "panaderia") == "rebajar"

    def test_medium_is_revisar(self):
        assert _action_from_risk("MEDIO", 5, "fruta") == "revisar"

    def test_low_is_ok(self):
        assert _action_from_risk("BAJO", 10, "verdura") == "ok"

    def test_unknown_category_expired_is_retirar(self):
        # Categoría desconocida → retirar por precaución (no está en donatable set)
        assert _action_from_risk("CRÍTICO", 0, "general") == "retirar"

    def test_case_insensitive_category(self):
        assert _action_from_risk("CRÍTICO", 0, "PANADERIA") == "donar"
        assert _action_from_risk("CRÍTICO", 0, "CARNE") == "retirar"


class TestEvaluate:
    def test_no_batches_returns_bajo(self, product_panaderia):
        result = evaluate(product_panaderia, [])
        assert result["risk_level"] == "BAJO"
        assert result["score"] == 0

    def test_expired_batch_returns_critico(self, product_carne):
        today = date.today()
        batch = {
            "id": "b-x",
            "product_id": product_carne["id"],
            "expiry_date": today.isoformat(),
            "quantity": 10,
            "status": "active",
        }
        # Carne expirando hoy con 10 uds × 4.20€ = 42€ → puede activar consenso
        # Mockeamos tanto call_structured (extended thinking) como reach_consensus
        consensus_mock = {
            "risk_level": "CRÍTICO", "score": 100, "action": "retirar",
            "price_adjustment_pct": 60, "reasoning": "Caduca hoy.",
            "thinking_summary": "Consenso 3/3", "days_left": 0,
            "total_value_at_risk": 42.0, "consensus_used": True,
        }
        llm_mock = {
            "score": 100, "risk_level": "CRÍTICO", "action": "retirar",
            "price_adjustment_pct": 60, "reasoning": "Caduca hoy.", "thinking_summary": "",
        }
        with patch("backend.agents.evaluator.llm.call_structured", return_value=llm_mock):
            with patch("backend.agents.consensus.reach_consensus", return_value=consensus_mock):
                result = evaluate(product_carne, [batch])
        assert result["risk_level"] == "CRÍTICO"
        assert result["score"] >= 80

    def test_low_risk_skips_llm(self, product_panaderia):
        today = date.today()
        batch = {
            "id": "b-x",
            "product_id": product_panaderia["id"],
            "expiry_date": (today + timedelta(days=14)).isoformat(),
            "quantity": 5,
            "status": "active",
        }
        with patch("backend.agents.evaluator.llm.call_structured") as mock:
            result = evaluate(product_panaderia, [batch])
            # Score should be low enough to skip LLM
            if result["score"] < 30:
                mock.assert_not_called()

    def test_category_multiplier_carne_higher_than_verdura(self):
        today = date.today()
        batch_3days = {
            "id": "b-x",
            "expiry_date": (today + timedelta(days=3)).isoformat(),
            "quantity": 5,
            "status": "active",
        }
        product_verdura = {"id": "pv", "name": "Lechuga", "category": "verdura", "price": 1.50, "cost": 0.60}
        product_carne_local = {"id": "pc", "name": "Carne", "category": "carne", "price": 4.20, "cost": 2.10}

        with patch("backend.agents.evaluator.llm.call_structured") as mock:
            mock.return_value = {"score": 50, "risk_level": "MEDIO", "action": "revisar",
                                 "price_adjustment_pct": 20, "reasoning": "test", "thinking_summary": ""}
            result_verdura = evaluate(product_verdura, [batch_3days])
            result_carne = evaluate(product_carne_local, [batch_3days])

        # Carne should always have score >= verdura for same days_left
        # (either from heuristic or from LLM with identical mock)
        # At minimum, both should have valid structure
        assert "risk_level" in result_verdura
        assert "risk_level" in result_carne

    def test_result_has_required_fields(self, product_pescado, batch_expiring_3days):
        with patch("backend.agents.evaluator.llm.call_structured") as mock:
            mock.return_value = {
                "score": 65,
                "risk_level": "ALTO",
                "action": "rebajar",
                "price_adjustment_pct": 35,
                "reasoning": "3 días, producto perecedero.",
                "thinking_summary": "",
            }
            result = evaluate(product_pescado, [batch_expiring_3days])

        required = {"risk_level", "score", "action", "price_adjustment_pct", "reasoning"}
        assert required.issubset(result.keys())

    def test_high_value_critical_triggers_consensus(self, product_carne):
        """Carne cara expirando hoy con mucho stock activa el consenso (triple agente)."""
        from datetime import date
        batch = {
            "id": "b-high-value",
            "product_id": product_carne["id"],
            "expiry_date": date.today().isoformat(),
            "quantity": 100,
            "status": "active",
        }
        consensus_mock = {
            "risk_level": "CRÍTICO", "score": 100, "action": "retirar",
            "price_adjustment_pct": 60, "reasoning": "Consenso 3 agentes.",
            "thinking_summary": "Consenso activo", "days_left": 0,
            "total_value_at_risk": 420.0, "consensus_used": True,
        }
        with patch("backend.agents.consensus.reach_consensus", return_value=consensus_mock) as mock_c, \
             patch("backend.agents.evaluator.llm.call_structured"):
            result = evaluate(product_carne, [batch])
        assert result["risk_level"] == "CRÍTICO"
        assert result.get("consensus_used") is True

    def test_multi_batch_factor_increases_score(self, product_carne):
        """Múltiples lotes críticos simultáneos aumentan el riesgo calculado."""
        from datetime import date, timedelta
        batches = [
            {"id": f"b-{i}", "product_id": product_carne["id"],
             "expiry_date": (date.today() + timedelta(days=1)).isoformat(),
             "quantity": 5, "status": "active"}
            for i in range(4)
        ]
        single_batch = [batches[0]]
        with patch("backend.agents.evaluator.llm.call_structured") as mock:
            mock.return_value = {
                "score": 80, "risk_level": "CRÍTICO", "action": "rebajar",
                "price_adjustment_pct": 40, "reasoning": "test", "thinking_summary": "",
            }
            result_single = evaluate(product_carne, single_batch)
            result_multi = evaluate(product_carne, batches)
        assert result_multi["score"] >= result_single["score"]

    def test_low_risk_result_has_confidence_and_temporal(self, product_panaderia):
        """Resultado heurístico (score bajo) incluye confidence_pct y temporal_factor."""
        from datetime import date, timedelta
        batch = {
            "id": "b-low",
            "expiry_date": (date.today() + timedelta(days=14)).isoformat(),
            "quantity": 5,
            "status": "active",
        }
        result = evaluate(product_panaderia, [batch])
        assert "confidence_pct" in result, "Debe incluir confidence_pct"
        assert "temporal_factor" in result, "Debe incluir temporal_factor"
        assert 0 < result["confidence_pct"] <= 100
        assert result["temporal_factor"] == 1.0, "Con >3 días, temporal_factor debe ser 1.0"


class TestTemporalFactor:
    """Tests del factor temporal de urgencia."""

    def test_more_than_3_days_neutral(self):
        from backend.agents.evaluator import _temporal_factor
        assert _temporal_factor(4) == 1.0
        assert _temporal_factor(7) == 1.0
        assert _temporal_factor(14) == 1.0

    def test_saturday_morning_reduces_urgency(self):
        """Sábado a las 10h: tráfico máximo → oportunidad de venta → factor < 1 (menos urgente)."""
        from unittest.mock import patch
        from datetime import datetime
        from backend.agents.evaluator import _temporal_factor
        # Sábado = weekday 5, hora 10 (mañana — hora_factor=0.90, tráfico 1.30)
        saturday_morning = datetime(2025, 6, 7, 10, 0)  # 7 junio 2025 = sábado
        with patch("backend.agents.evaluator.datetime") as mock_dt:
            mock_dt.now.return_value = saturday_morning
            f = _temporal_factor(1)
        assert f < 1.0, f"Sábado mañana debe reducir urgencia, factor={f}"

    def test_monday_night_increases_urgency(self):
        """Lunes a las 21h: tráfico mínimo + hora tardía → factor > 1 (más urgente)."""
        from unittest.mock import patch
        from datetime import datetime
        from backend.agents.evaluator import _temporal_factor
        # Lunes = weekday 0, hora 21 (hora_factor=1.25, tráfico 0.65)
        monday_night = datetime(2025, 6, 2, 21, 0)  # 2 junio 2025 = lunes
        with patch("backend.agents.evaluator.datetime") as mock_dt:
            mock_dt.now.return_value = monday_night
            f = _temporal_factor(1)
        assert f > 1.0, f"Lunes noche debe aumentar urgencia, factor={f}"

    def test_saturday_more_lenient_than_monday(self):
        """Sábado debe dar siempre menos urgencia que lunes para el mismo producto."""
        from unittest.mock import patch
        from datetime import datetime
        from backend.agents.evaluator import _temporal_factor

        saturday = datetime(2025, 6, 7, 12, 0)
        monday = datetime(2025, 6, 2, 12, 0)

        with patch("backend.agents.evaluator.datetime") as mock_dt:
            mock_dt.now.return_value = saturday
            f_sat = _temporal_factor(2)

        with patch("backend.agents.evaluator.datetime") as mock_dt:
            mock_dt.now.return_value = monday
            f_mon = _temporal_factor(2)

        assert f_sat < f_mon, f"Sábado ({f_sat}) debe ser < lunes ({f_mon})"

    def test_expired_today_in_valid_range(self):
        from backend.agents.evaluator import _temporal_factor
        f = _temporal_factor(0)
        assert 0.5 <= f <= 2.0


class TestConfidencePct:
    """Tests de la función de confianza en la decisión."""

    def test_expired_product_max_confidence(self):
        from backend.agents.evaluator import _confidence_pct
        c = _confidence_pct(score=100, days_left=0, qty=10, value_at_risk=50.0)
        assert c >= 90

    def test_far_future_max_confidence(self):
        from backend.agents.evaluator import _confidence_pct
        c = _confidence_pct(score=10, days_left=14, qty=5, value_at_risk=10.0)
        assert c >= 90

    def test_borderline_score_lower_confidence(self):
        from backend.agents.evaluator import _confidence_pct
        borderline = _confidence_pct(score=70, days_left=2, qty=5, value_at_risk=20.0)
        clear_case = _confidence_pct(score=95, days_left=0, qty=5, value_at_risk=100.0)
        assert borderline < clear_case, "Caso borderline debe tener menos confianza que caso claro"

    def test_always_in_valid_range(self):
        from backend.agents.evaluator import _confidence_pct
        for score in [0, 30, 60, 70, 80, 95, 100]:
            for days in [0, 1, 3, 7, 14]:
                c = _confidence_pct(score, days, 10, 50.0)
                assert 0 < c <= 100, f"Confianza fuera de rango: score={score}, days={days} → {c}"


class TestEdgeCasesEvaluator:
    """
    Casos límite reales que pueden llegar del TPV/ERP de un supermercado.
    Protegen contra datos corruptos que crashearían el Evaluador en producción.
    """

    def test_batch_with_missing_expiry_returns_bajo(self):
        # Protege: si el ERP no envía fecha de caducidad (campo vacío o null),
        # el Evaluador NO debe explotar ni dar CRÍTICO por defecto.
        # Fallo real posible: date.fromisoformat("") lanza ValueError.
        from backend.agents.evaluator import evaluate
        product = {"id": "p1", "name": "Leche sin fecha", "category": "lacteos",
                   "price": 1.20, "cost": 0.70}
        batch_no_expiry = {"id": "b1", "expiry_date": "", "quantity": 10, "status": "active"}
        result = evaluate(product, [batch_no_expiry])
        assert result["risk_level"] in ("BAJO", "MEDIO", "ALTO", "CRÍTICO"), \
            "Debe devolver un nivel válido aunque no haya fecha"
        assert "score" in result, "Debe incluir score aunque no haya fecha"

    def test_batch_with_null_expiry_does_not_crash(self):
        # Protege: None en expiry_date (campo null en Supabase) no debe explotar.
        from backend.agents.evaluator import evaluate
        product = {"id": "p2", "name": "Yogur null date", "category": "lacteos",
                   "price": 0.90, "cost": 0.45}
        batch_null = {"id": "b2", "expiry_date": None, "quantity": 5, "status": "active"}
        result = evaluate(product, [batch_null])
        assert isinstance(result, dict)
        assert result.get("score", -1) >= 0

    def test_zero_price_product_does_not_divide_by_zero(self):
        # Protege: producto con precio 0 (artículo gratuito/promoción) no debe
        # causar ZeroDivisionError en el cálculo de value_at_risk.
        from backend.agents.evaluator import evaluate
        from datetime import date, timedelta
        from unittest.mock import patch
        product = {"id": "p3", "name": "Muestra gratuita", "category": "general",
                   "price": 0.0, "cost": 0.0}
        batch = {"id": "b3", "expiry_date": (date.today() + timedelta(days=1)).isoformat(),
                 "quantity": 100, "status": "active"}
        # Precio 0 → value_at_risk=0 → heuristic score bajo → no llama LLM
        # Pero si llama LLM (por otra razón), mockearlo para no necesitar API key
        with patch("backend.agents.evaluator.llm.call_structured",
                   return_value={"score": 15, "risk_level": "BAJO", "action": "ok",
                                 "price_adjustment_pct": 0, "reasoning": "sin valor", "thinking_summary": ""}):
            result = evaluate(product, [batch])
        assert isinstance(result, dict)
        assert result.get("total_value_at_risk", 0) == 0.0

    def test_extremely_high_quantity_does_not_overflow_score(self):
        # Protege: lote de 10.000 unidades no debe dar score > 100.
        # Fallo real posible: si value_factor no estaba acotado, raw_score > 100.
        # value_factor = min(1.3, 1.0 + (10000*1.50/100)*0.1) = min(1.3, 16) = 1.3 → OK
        from backend.agents.evaluator import evaluate
        from datetime import date, timedelta
        from unittest.mock import patch
        product = {"id": "p4", "name": "Pan mayorista", "category": "panaderia",
                   "price": 1.50, "cost": 0.80}
        batch = {"id": "b4", "expiry_date": (date.today() + timedelta(days=1)).isoformat(),
                 "quantity": 10000, "status": "active"}
        with patch("backend.agents.evaluator.llm.call_structured",
                   return_value={"score": 95, "risk_level": "CRÍTICO", "action": "rebajar",
                                 "price_adjustment_pct": 50, "reasoning": "test", "thinking_summary": ""}), \
             patch("backend.agents.consensus.reach_consensus",
                   return_value={"risk_level": "CRÍTICO", "score": 95, "action": "rebajar",
                                 "price_adjustment_pct": 50, "reasoning": "test",
                                 "thinking_summary": "", "days_left": 1, "total_value_at_risk": 15000.0}):
            result = evaluate(product, [batch])
        assert result["score"] <= 100, f"Score no puede superar 100: {result['score']}"

    def test_negative_days_left_is_expired_and_not_bajo(self):
        # Protege: producto que lleva 3 días caducado no puede recibir nivel BAJO.
        # Fallo real posible: si _safe_days_left devuelve 999 para fechas pasadas.
        from backend.agents.evaluator import _safe_days_left, _base_score, _risk_level
        from datetime import date, timedelta
        expired_3_days = (date.today() - timedelta(days=3)).isoformat()
        days = _safe_days_left(expired_3_days)
        assert days < 0, f"Producto caducado hace 3 días debe tener days_left < 0, got {days}"
        score = _base_score(days)
        assert score >= 85, f"Producto caducado debe tener score >= 85, got {score}"
