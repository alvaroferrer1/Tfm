"""
Tests del Vision Agent.
Sin llamadas reales a Claude — se mockea llm.call_vision.
"""
from unittest.mock import patch
import base64
import pytest

from backend.agents.vision import (
    analyze_product_photo,
    analyze_from_telegram_file,
    format_vision_result,
)


_FAKE_B64 = base64.b64encode(b"fake-image-data").decode()

_GOOD_RESPONSE = """\
ESTADO: bueno
PROBLEMAS: ninguno
FECHA VISIBLE: 20/06/2026
ACCIÓN: ok
URGENCIA: ninguna
CONFIANZA: 92
DIAGNÓSTICO: El producto está en perfecto estado. No se requiere acción.\
"""

_BAD_RESPONSE = """\
ESTADO: deteriorado
PROBLEMAS: manchas marrones en la superficie, envase abollado
FECHA VISIBLE: no visible
ACCIÓN: rebajar
URGENCIA: hoy
CONFIANZA: 78
DIAGNÓSTICO: Producto deteriorado visualmente. Aplicar descuento del 30% e informar al encargado.\
"""

_CRITICAL_RESPONSE = """\
ESTADO: posiblemente_expirado
PROBLEMAS: moho visible en la parte superior, olor rancio presumible, fecha borrosa
FECHA VISIBLE: 01/05/2026
ACCIÓN: retirar
URGENCIA: inmediata
CONFIANZA: 95
DIAGNÓSTICO: Retirar inmediatamente. Producto con signos evidentes de expiración.\
"""


class TestAnalyzeProductPhoto:
    def test_good_product_parsed_correctly(self):
        with patch("backend.agents.vision.llm.call_vision", return_value=_GOOD_RESPONSE):
            result = analyze_product_photo(_FAKE_B64, product_name="Yogur natural")

        assert result["condition"] == "bueno"
        assert result["action"] == "ok"
        assert result["urgency"] == "ninguna"
        assert result["confidence"] == 92
        assert result["visible_date"] == "20/06/2026"
        assert result["issues"] == []

    def test_deteriorated_product_parsed_correctly(self):
        with patch("backend.agents.vision.llm.call_vision", return_value=_BAD_RESPONSE):
            result = analyze_product_photo(_FAKE_B64, category="fruta")

        assert result["condition"] == "deteriorado"
        assert result["action"] == "rebajar"
        assert result["urgency"] == "hoy"
        assert result["confidence"] == 78
        assert len(result["issues"]) == 2
        assert result["visible_date"] is None

    def test_critical_product_requires_immediate_action(self):
        with patch("backend.agents.vision.llm.call_vision", return_value=_CRITICAL_RESPONSE):
            result = analyze_product_photo(_FAKE_B64, days_left=0)

        assert result["condition"] == "posiblemente_expirado"
        assert result["action"] == "retirar"
        assert result["urgency"] == "inmediata"
        assert result["confidence"] == 95

    def test_all_required_keys_present(self):
        with patch("backend.agents.vision.llm.call_vision", return_value=_GOOD_RESPONSE):
            result = analyze_product_photo(_FAKE_B64)

        required = {"condition", "issues", "action", "urgency", "visible_date",
                    "date_matches", "confidence", "diagnosis", "full_analysis"}
        assert required.issubset(result.keys())

    def test_llm_error_returns_safe_fallback(self):
        with patch("backend.agents.vision.llm.call_vision", side_effect=Exception("timeout")):
            result = analyze_product_photo(_FAKE_B64)

        assert result["condition"] == "no_identificado"
        assert result["action"] == "revisar"
        assert result["confidence"] == 0
        assert "Error" in result["diagnosis"]

    def test_partial_response_does_not_crash(self):
        partial = "ESTADO: dañado\nACCIÓN: retirar"
        with patch("backend.agents.vision.llm.call_vision", return_value=partial):
            result = analyze_product_photo(_FAKE_B64)

        assert result["condition"] == "dañado"
        assert result["action"] == "retirar"
        # Campos no presentes en la respuesta → valores por defecto
        assert result["confidence"] == 50
        assert result["urgency"] == "normal"

    def test_invalid_condition_value_uses_default(self):
        bad = "ESTADO: estupendo\nACCIÓN: ok\nURGENCIA: ninguna\nCONFIANZA: 80\nDIAGNÓSTICO: test"
        with patch("backend.agents.vision.llm.call_vision", return_value=bad):
            result = analyze_product_photo(_FAKE_B64)

        # Valor inválido → se mantiene el default "no_identificado"
        assert result["condition"] == "no_identificado"
        assert result["action"] == "ok"

    def test_context_sent_includes_product_name_and_days(self):
        captured = {}

        def fake_call_vision(image_base64, prompt, **kwargs):
            captured["prompt"] = prompt
            return _GOOD_RESPONSE

        with patch("backend.agents.vision.llm.call_vision", side_effect=fake_call_vision):
            analyze_product_photo(_FAKE_B64, product_name="Leche entera", days_left=2, category="lacteos")

        assert "Leche entera" in captured["prompt"]
        assert "2 días" in captured["prompt"]
        assert "lacteos" in captured["prompt"]


class TestAnalyzeFromTelegramFile:
    def test_bytes_converted_to_base64(self):
        captured = {}

        def fake_call_vision(image_base64, prompt, **kwargs):
            captured["b64"] = image_base64
            return _GOOD_RESPONSE

        raw_bytes = b"\xff\xd8\xff\xe0test-jpeg-data"
        with patch("backend.agents.vision.llm.call_vision", side_effect=fake_call_vision):
            result = analyze_from_telegram_file(raw_bytes, product_name="Pan")

        expected_b64 = base64.b64encode(raw_bytes).decode()
        assert captured["b64"] == expected_b64
        assert result["condition"] == "bueno"


class TestFormatVisionResult:
    def test_good_product_shows_verde(self):
        result = {
            "condition": "bueno", "action": "ok", "urgency": "ninguna",
            "issues": [], "visible_date": None, "confidence": 90,
            "diagnosis": "Producto en perfecto estado.",
        }
        text = format_vision_result(result)
        assert "VERDE" in text
        assert "OK" in text
        assert "90%" in text

    def test_critical_product_shows_rojo(self):
        result = {
            "condition": "posiblemente_expirado", "action": "retirar", "urgency": "inmediata",
            "issues": ["moho"], "visible_date": "01/05/2026", "confidence": 95,
            "diagnosis": "Retirar ahora.",
        }
        text = format_vision_result(result)
        assert "ROJO" in text
        assert "RETIRAR" in text
        assert "01/05/2026" in text
        assert "moho" in text

    def test_no_issues_line_when_empty(self):
        result = {
            "condition": "bueno", "action": "ok", "urgency": "ninguna",
            "issues": [], "visible_date": None, "confidence": 85,
            "diagnosis": "Ok.",
        }
        text = format_vision_result(result)
        assert "Problemas detectados" not in text

    def test_unknown_condition_shows_gris(self):
        result = {
            "condition": "no_identificado", "action": "revisar", "urgency": "normal",
            "issues": [], "visible_date": None, "confidence": 0,
            "diagnosis": "No se pudo identificar.",
        }
        text = format_vision_result(result)
        assert "GRIS" in text
