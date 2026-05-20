"""Tests para backend/core/reflexion.py — sin Supabase real."""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_db(memory_store: dict):
    """Mock database con dict en memoria."""
    def get_memory(store_id, key):
        return memory_store.get(f"{store_id}:{key}")

    def set_memory(store_id, key, value):
        memory_store[f"{store_id}:{key}"] = value

    mock_db = MagicMock()
    mock_db.get_memory = get_memory
    mock_db.set_memory = set_memory
    return mock_db


# ── load_reflexions ───────────────────────────────────────────────────────────

class TestLoadReflexions:
    def test_empty_db_returns_empty(self):
        from backend.core.reflexion import load_reflexions
        with patch("backend.core.database.get_memory", return_value=None):
            assert load_reflexions("test-store") == []

    def test_returns_non_empty_slots(self):
        from backend.core.reflexion import load_reflexions
        answers = {"chuwi_reflexion_00": "leccion A", "chuwi_reflexion_01": None}

        def fake_get(store_id, key):
            return answers.get(key)

        with patch("backend.core.database.get_memory", side_effect=fake_get):
            result = load_reflexions("test-store")
        assert "leccion A" in result
        assert len(result) == 1

    def test_db_error_returns_empty(self):
        from backend.core.reflexion import load_reflexions
        with patch("backend.core.database.get_memory", side_effect=RuntimeError("DB down")):
            result = load_reflexions("test-store")
        assert result == []


# ── get_reflexion_context ─────────────────────────────────────────────────────

class TestGetReflexionContext:
    def test_empty_lessons_returns_empty_string(self):
        from backend.core.reflexion import get_reflexion_context
        with patch("backend.core.database.get_memory", return_value=None):
            assert get_reflexion_context("store") == ""

    def test_lessons_wrapped_in_context_block(self):
        from backend.core.reflexion import get_reflexion_context
        with patch("backend.core.database.get_memory", return_value="leccion de prueba"):
            ctx = get_reflexion_context("store")
        assert "LECCIONES APRENDIDAS" in ctx
        assert "leccion de prueba" in ctx


# ── save_reflexion ────────────────────────────────────────────────────────────

class TestSaveReflexion:
    def test_saves_to_memory(self):
        from backend.core.reflexion import save_reflexion
        saved = {}
        with patch("backend.core.database.get_memory", return_value="0"), \
             patch("backend.core.database.set_memory", side_effect=lambda s, k, v: saved.update({k: v})):
            save_reflexion("store", "nueva leccion")
        assert any("chuwi_reflexion" in k for k in saved)

    def test_truncates_long_lesson(self):
        from backend.core.reflexion import save_reflexion
        saved = {}
        long_lesson = "x" * 500
        with patch("backend.core.database.get_memory", return_value="0"), \
             patch("backend.core.database.set_memory", side_effect=lambda s, k, v: saved.update({k: v})):
            save_reflexion("store", long_lesson)
        stored = [v for k, v in saved.items() if "reflexion_0" in k]
        assert stored and len(stored[0]) <= 200

    def test_db_error_does_not_raise(self):
        from backend.core.reflexion import save_reflexion
        with patch("backend.core.database.get_memory", side_effect=RuntimeError("boom")):
            save_reflexion("store", "leccion")  # must not raise

    def test_pointer_increments(self):
        from backend.core.reflexion import save_reflexion
        saved = {}
        with patch("backend.core.database.get_memory", return_value="2"), \
             patch("backend.core.database.set_memory", side_effect=lambda s, k, v: saved.update({k: v})):
            save_reflexion("store", "leccion")
        # slot 2 should be written, pointer should advance to 3
        assert saved.get("chuwi_reflexion_ptr") == "3"
        assert saved.get("chuwi_reflexion_02") == "leccion"


# ── async_generate_and_save ───────────────────────────────────────────────────

class TestAsyncGenerateAndSave:
    def test_skips_short_exchanges(self):
        import asyncio
        from backend.core.reflexion import async_generate_and_save
        with patch("backend.core.llm.call_fast") as mock_llm:
            asyncio.run(
                async_generate_and_save("store", "hola", "ok")
            )
        mock_llm.assert_not_called()

    def test_calls_haiku_for_long_exchanges(self):
        import asyncio
        from backend.core.reflexion import async_generate_and_save
        with patch("backend.core.llm.call_fast", return_value="Lección generada.") as mock_llm, \
             patch("backend.core.reflexion.save_reflexion") as mock_save:
            asyncio.run(
                async_generate_and_save(
                    "store",
                    "Cuánto stock de manzanas hay en la tienda?",
                    "Hay 45 unidades de manzanas Golden. El lote vence en 3 días.",
                )
            )
        mock_llm.assert_called_once()
        mock_save.assert_called_once()

    def test_llm_error_does_not_raise(self):
        import asyncio
        from backend.core.reflexion import async_generate_and_save
        with patch("backend.core.llm.call_fast", side_effect=RuntimeError("API error")):
            asyncio.run(
                async_generate_and_save(
                    "store",
                    "Pregunta larga de prueba que supere el umbral mínimo de 80 chars totales",
                    "Respuesta también larga de prueba para asegurarnos de que pasa el filtro",
                )
            )  # must not raise
