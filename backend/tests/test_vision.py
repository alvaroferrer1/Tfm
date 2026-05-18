"""
Tests del Vision Agent.
vision.py usa get_client().messages.create() con tool_use estructurado.
Mockeamos get_client para no llamar a la API real.
"""
from unittest.mock import patch, MagicMock
import base64
import pytest

from backend.agents.vision import (
    analyze_product_photo,
    analyze_from_telegram_file,
    format_vision_result,
)


_FAKE_B64 = base64.b64encode(b"fake-image-data").decode()


def _make_vision_response(structured: dict) -> MagicMock:
    """Construye un mock de respuesta Anthropic con un bloque tool_use."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "vision_analysis"
    block.input = structured

    response = MagicMock()
    response.content = [block]
    response.usage = MagicMock(input_tokens=100, output_tokens=50)
    return response


def _mock_client(structured: dict):
    """Contexto: parcha get_client() (importado dentro de vision.py) para devolver structured."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_vision_response(structured)
    return patch("backend.core.llm.get_client", return_value=mock_client)


class TestAnalyzeProductPhoto:
    def test_good_product_parsed_correctly(self):
        structured = {
            "condition": "bueno", "issues": [], "visible_date": "20/06/2026",
            "action": "ok", "urgency": "ninguna", "confidence": 92,
            "diagnosis": "El producto está en perfecto estado.",
            "full_analysis": "Sin problemas.",
        }
        with _mock_client(structured):
            result = analyze_product_photo(_FAKE_B64, product_name="Yogur natural")

        assert result["condition"] == "bueno"
        assert result["action"] == "ok"
        assert result["urgency"] == "ninguna"
        assert result["confidence"] == 92
        assert result["visible_date"] == "20/06/2026"
        assert result["issues"] == []

    def test_deteriorated_product_parsed_correctly(self):
        structured = {
            "condition": "deteriorado",
            "issues": ["manchas marrones en la superficie", "envase abollado"],
            "visible_date": None,
            "action": "rebajar", "urgency": "hoy", "confidence": 78,
            "diagnosis": "Producto deteriorado visualmente.",
            "full_analysis": "Aplicar descuento del 30%.",
        }
        with _mock_client(structured):
            result = analyze_product_photo(_FAKE_B64, category="fruta")

        assert result["condition"] == "deteriorado"
        assert result["action"] == "rebajar"
        assert result["urgency"] == "hoy"
        assert result["confidence"] == 78
        assert len(result["issues"]) == 2
        assert result["visible_date"] is None

    def test_critical_product_requires_immediate_action(self):
        structured = {
            "condition": "posiblemente_expirado",
            "issues": ["moho visible en la parte superior"],
            "visible_date": "01/05/2026",
            "action": "retirar", "urgency": "inmediata", "confidence": 95,
            "diagnosis": "Retirar inmediatamente.",
            "full_analysis": "Signos evidentes de expiración.",
        }
        with _mock_client(structured):
            result = analyze_product_photo(_FAKE_B64, days_left=0)

        assert result["condition"] == "posiblemente_expirado"
        assert result["action"] == "retirar"
        assert result["urgency"] == "inmediata"
        assert result["confidence"] == 95

    def test_all_required_keys_present(self):
        structured = {
            "condition": "bueno", "issues": [], "visible_date": None,
            "action": "ok", "urgency": "ninguna", "confidence": 88,
            "diagnosis": "Producto ok.", "full_analysis": "Sin problemas.",
        }
        with _mock_client(structured):
            result = analyze_product_photo(_FAKE_B64)

        required = {"condition", "issues", "action", "urgency", "visible_date",
                    "date_matches", "confidence", "diagnosis", "full_analysis"}
        assert required.issubset(result.keys())

    def test_llm_error_returns_safe_fallback(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("timeout")
        with patch("backend.core.llm.get_client", return_value=mock_client):
            result = analyze_product_photo(_FAKE_B64)

        assert result["condition"] == "no_identificado"
        assert result["action"] == "revisar"
        assert result["confidence"] == 0
        assert "Error" in result["diagnosis"]

    def test_partial_response_does_not_crash(self):
        structured = {
            "condition": "danado",
            "issues": [],
            "visible_date": None,
            "action": "retirar",
            "urgency": "normal",
            "confidence": 50,
            "diagnosis": "Revisar.",
            "full_analysis": "",
        }
        with _mock_client(structured):
            result = analyze_product_photo(_FAKE_B64)

        assert result["condition"] == "danado"
        assert result["action"] == "retirar"

    def test_invalid_condition_value_falls_through(self):
        structured = {
            "condition": "no_identificado",
            "issues": [],
            "visible_date": None,
            "action": "ok",
            "urgency": "ninguna",
            "confidence": 80,
            "diagnosis": "test",
            "full_analysis": "",
        }
        with _mock_client(structured):
            result = analyze_product_photo(_FAKE_B64)

        assert result["condition"] == "no_identificado"
        assert result["action"] == "ok"

    def test_context_sent_includes_product_name_and_days(self):
        structured = {
            "condition": "bueno", "issues": [], "visible_date": None,
            "action": "ok", "urgency": "ninguna", "confidence": 90,
            "diagnosis": "Ok.", "full_analysis": "",
        }
        captured_messages = []

        def capture_create(**kwargs):
            captured_messages.append(kwargs.get("messages", []))
            return _make_vision_response(structured)

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = capture_create

        with patch("backend.core.llm.get_client", return_value=mock_client):
            analyze_product_photo(_FAKE_B64, product_name="Leche entera", days_left=2, category="lacteos")

        assert len(captured_messages) == 1
        msg_content = str(captured_messages[0])
        assert "Leche entera" in msg_content
        assert "2" in msg_content
        assert "lacteos" in msg_content


class TestAnalyzeFromTelegramFile:
    def test_bytes_converted_to_base64(self):
        raw_bytes = b"\xff\xd8\xff\xe0test-jpeg-data"
        expected_b64 = base64.b64encode(raw_bytes).decode()
        captured = {}

        def capture_create(**kwargs):
            msgs = kwargs.get("messages", [])
            for msg in msgs:
                for block in (msg.get("content") or []):
                    if isinstance(block, dict) and block.get("type") == "image":
                        captured["b64"] = block["source"]["data"]
            structured = {
                "condition": "bueno", "issues": [], "visible_date": None,
                "action": "ok", "urgency": "ninguna", "confidence": 88,
                "diagnosis": "Ok.", "full_analysis": "",
            }
            return _make_vision_response(structured)

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = capture_create

        with patch("backend.core.llm.get_client", return_value=mock_client):
            result = analyze_from_telegram_file(raw_bytes, product_name="Pan")

        assert captured.get("b64") == expected_b64
        assert result["condition"] == "bueno"

    def test_jpeg_media_type_used(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_vision_response({
            "condition": "bueno", "issues": [], "visible_date": None,
            "action": "ok", "urgency": "ninguna", "confidence": 80,
            "diagnosis": "ok", "full_analysis": "",
        })
        with patch("backend.core.llm.get_client", return_value=mock_client):
            analyze_from_telegram_file(b"fake-bytes")

        call_kwargs = mock_client.messages.create.call_args[1]
        msg_content = call_kwargs["messages"][0]["content"]
        image_block = next(b for b in msg_content if isinstance(b, dict) and b.get("type") == "image")
        assert image_block["source"]["media_type"] == "image/jpeg"


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
