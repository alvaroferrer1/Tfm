"""Tests del Scanner Agent — busca productos en OpenFoodFacts."""
import pytest
from unittest.mock import patch, MagicMock
from backend.agents.scanner import lookup_barcode


def _mock_product(name_es="", name="", brand="", tags=None, image=""):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "status": 1,
        "product": {
            "product_name_es": name_es,
            "product_name": name,
            "brands": brand,
            "categories_tags": tags or [],
            "image_url": image,
        },
    }
    return mock_resp


class TestLookupBarcode:
    def test_returns_none_on_product_not_found(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": 0}
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("9999999999999")
        assert result is None

    def test_returns_product_info_when_found(self):
        mock_resp = _mock_product(
            name_es="Yogur natural Danone",
            brand="Danone",
            tags=["en:dairy", "en:yogurts"],
            image="https://example.com/image.jpg",
        )
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("3033490004743")
        assert result is not None
        assert result["name"] == "Yogur natural Danone"
        assert result["brand"] == "Danone"
        assert result["barcode"] == "3033490004743"

    def test_returns_none_on_network_error(self):
        with patch("backend.agents.scanner.requests.get", side_effect=Exception("timeout")):
            result = lookup_barcode("8410031001001")
        assert result is None

    def test_falls_back_to_generic_name(self):
        mock_resp = _mock_product(name="Generic Yogurt", brand="Test", tags=[])
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("1234567890123")
        assert result is not None
        assert result["name"] == "Generic Yogurt"

    def test_category_tag_cleaned(self):
        mock_resp = _mock_product(name_es="Leche entera", brand="Mercadona", tags=["en:milks", "en:dairy"])
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("8480000000001")
        assert "en:" not in result["category"]

    def test_result_has_all_required_keys(self):
        mock_resp = _mock_product(name_es="Producto Test", brand="Marca", tags=["en:food"])
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("0000000000000")
        required_keys = {"barcode", "name", "brand", "category", "image_url"}
        assert required_keys.issubset(result.keys())

    def test_barcode_preserved_in_result(self):
        barcode = "8410031001001"
        mock_resp = _mock_product(name_es="Leche", brand="LaCentral", tags=["en:milks"])
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode(barcode)
        assert result["barcode"] == barcode

    def test_empty_categories_returns_empty_string(self):
        mock_resp = _mock_product(name_es="Producto sin categoría", brand="X", tags=[])
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("1111111111111")
        assert result["category"] == ""

    def test_image_url_preserved(self):
        url = "https://images.openfoodfacts.org/test.jpg"
        mock_resp = _mock_product(name_es="Test", brand="T", tags=[], image=url)
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("2222222222222")
        assert result["image_url"] == url

    def test_missing_image_url_defaults_empty(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": 1,
            "product": {
                "product_name_es": "Sin imagen",
                "brands": "X",
                "categories_tags": [],
            },
        }
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("3333333333333")
        assert result["image_url"] == ""

    def test_status_missing_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"product": {}}
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("4444444444444")
        assert result is None

    def test_json_decode_error_returns_none(self):
        with patch("backend.agents.scanner.requests.get", side_effect=ValueError("JSON error")):
            result = lookup_barcode("5555555555555")
        assert result is None

    def test_es_name_takes_priority_over_generic(self):
        mock_resp = _mock_product(name_es="Yogur ES", name="Yogur Generic")
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("6666666666666")
        assert result["name"] == "Yogur ES"

    def test_category_uses_first_tag(self):
        mock_resp = _mock_product(name_es="P", tags=["en:first-category", "en:second-category"])
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("7777777777777")
        assert result["category"] == "first-category"

    def test_none_categories_tags_defaults_empty(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": 1,
            "product": {
                "product_name_es": "Producto",
                "brands": "X",
                "categories_tags": None,
            },
        }
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("8888888888888")
        assert result["category"] == ""

    def test_connection_timeout_returns_none(self):
        import requests as req
        with patch("backend.agents.scanner.requests.get", side_effect=req.exceptions.Timeout):
            result = lookup_barcode("9876543210987")
        assert result is None
