"""Tests del Memory System — sin red (mocking database)."""
from unittest.mock import patch, MagicMock
import pytest
from backend.core import memory as mem


STORE_ID = "demo-store-001"


class TestMemory:
    def test_recall_returns_none_when_not_found(self):
        with patch("backend.core.memory.database.get_memory", return_value=None):
            result = mem.recall(STORE_ID, "nonexistent_key")
            assert result is None

    def test_recall_returns_value_when_found(self):
        with patch("backend.core.memory.database.get_memory", return_value="pan se vende bien mañanas"):
            result = mem.recall(STORE_ID, "categoria_panaderia_velocidad")
            assert result == "pan se vende bien mañanas"

    def test_remember_calls_database(self):
        with patch("backend.core.memory.database.set_memory") as mock:
            mem.remember(STORE_ID, "test_key", "test_value")
            mock.assert_called_once_with(STORE_ID, "test_key", "test_value")

    def test_recall_category_velocity_uses_correct_key(self):
        with patch("backend.core.memory.database.get_memory") as mock:
            mock.return_value = "alta"
            mem.recall_category_velocity(STORE_ID, "carne")
            mock.assert_called_once_with(STORE_ID, "categoria_carne_velocidad")

    def test_remember_category_velocity_uses_correct_key(self):
        with patch("backend.core.memory.database.set_memory") as mock:
            mem.remember_category_velocity(STORE_ID, "pescado", "baja en verano")
            mock.assert_called_once_with(STORE_ID, "categoria_pescado_velocidad", "baja en verano")

    def test_build_memory_context_with_no_data(self):
        with patch("backend.core.memory.database.get_memory", return_value=None):
            ctx = mem.build_memory_context(STORE_ID, categories=["carne", "pescado"])
            assert "Sin patrones" in ctx

    def test_build_memory_context_with_data(self):
        def mock_get(store_id, key):
            if "carne" in key:
                return "se vende rápido los lunes"
            return None

        with patch("backend.core.memory.database.get_memory", side_effect=mock_get):
            ctx = mem.build_memory_context(STORE_ID, categories=["carne", "pescado"])
            assert "carne" in ctx.lower()
            assert "lunes" in ctx

    def test_record_daily_stats_saves_to_memory(self):
        with patch("backend.core.memory.database.set_memory") as mock:
            mem.record_daily_stats(STORE_ID, value_lost=45.50, items_discarded=3)
            mock.assert_called_once()
            call_args = mock.call_args[0]
            assert STORE_ID in call_args
            assert "45.50" in call_args[2]

    def test_remember_silently_handles_error(self):
        with patch("backend.core.memory.database.set_memory", side_effect=Exception("DB down")):
            result = mem.remember(STORE_ID, "key", "value")
        assert result is None  # error silenciado, no propaga excepción

    def test_recall_silently_handles_error(self):
        with patch("backend.core.memory.database.get_memory", side_effect=Exception("DB down")):
            result = mem.recall(STORE_ID, "key")
            assert result is None
