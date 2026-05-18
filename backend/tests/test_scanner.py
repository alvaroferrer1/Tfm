"""Tests del Scanner Agent — busca productos en OpenFoodFacts."""
import pytest
from unittest.mock import patch, MagicMock
from backend.agents.scanner import lookup_barcode


class TestLookupBarcode:
    def test_returns_none_on_product_not_found(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": 0}
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("9999999999999")
        assert result is None

    def test_returns_product_info_when_found(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": 1,
            "product": {
                "product_name_es": "Yogur natural Danone",
                "brands": "Danone",
                "categories_tags": ["en:dairy", "en:yogurts"],
                "image_url": "https://example.com/image.jpg",
            },
        }
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
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": 1,
            "product": {
                "product_name": "Generic Yogurt",
                "product_name_es": "",
                "brands": "Test",
                "categories_tags": [],
            },
        }
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("1234567890123")
        assert result is not None
        assert result["name"] == "Generic Yogurt"

    def test_category_tag_cleaned(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": 1,
            "product": {
                "product_name_es": "Leche entera",
                "brands": "Mercadona",
                "categories_tags": ["en:milks", "en:dairy"],
                "image_url": "",
            },
        }
        with patch("backend.agents.scanner.requests.get", return_value=mock_resp):
            result = lookup_barcode("8480000000001")
        # "en:milks" → "milks" (removed "en:" prefix)
        assert "en:" not in result["category"]
