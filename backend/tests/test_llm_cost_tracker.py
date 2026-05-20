"""Tests para el token cost tracker de backend/core/llm.py."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock


class TestTokenCostTracker:
    def _make_usage(self, input_tok=1000, output_tok=500,
                    cache_read=0, cache_write=0):
        u = MagicMock()
        u.input_tokens = input_tok
        u.output_tokens = output_tok
        u.cache_read_input_tokens = cache_read
        u.cache_creation_input_tokens = cache_write
        return u

    def test_track_cost_returns_floats(self):
        from backend.core.llm import _track_cost
        usage = self._make_usage()
        actual, baseline = _track_cost(usage, "claude-sonnet-4-6")
        assert isinstance(actual, float)
        assert isinstance(baseline, float)

    def test_actual_less_than_baseline_with_cache_read(self):
        from backend.core.llm import _track_cost
        usage = self._make_usage(input_tok=100, cache_read=5000)
        actual, baseline = _track_cost(usage, "claude-sonnet-4-6")
        assert actual < baseline

    def test_no_cache_actual_equals_baseline(self):
        from backend.core.llm import _track_cost, _cost_tracker
        usage = self._make_usage(input_tok=1000, output_tok=500,
                                  cache_read=0, cache_write=0)
        actual, baseline = _track_cost(usage, "claude-sonnet-4-6")
        assert abs(actual - baseline) < 1e-9

    def test_get_cost_summary_returns_dict(self):
        from backend.core.llm import get_cost_summary
        summary = get_cost_summary()
        required = {"total_usd", "saved_usd", "saving_pct", "calls",
                    "cache_hit_pct", "input_tokens", "output_tokens",
                    "cache_read_tokens"}
        assert required.issubset(summary.keys())

    def test_cost_accumulates(self):
        from backend.core.llm import _track_cost, get_cost_summary
        before = get_cost_summary()["total_usd"]
        usage = self._make_usage(input_tok=10000, output_tok=5000)
        _track_cost(usage, "claude-sonnet-4-6")
        after = get_cost_summary()["total_usd"]
        assert after > before

    def test_haiku_cheaper_than_opus(self):
        from backend.core.llm import _track_cost
        usage = self._make_usage(input_tok=1000, output_tok=500)
        haiku_actual, _ = _track_cost(usage, "claude-haiku-4-5-20251001")
        opus_actual, _  = _track_cost(usage, "claude-opus-4-7")
        assert haiku_actual < opus_actual

    def test_mock_usage_safe(self):
        """MagicMock con attrs no definidos no debe romper _track_cost."""
        from backend.core.llm import _track_cost
        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        # cache attrs no definidos → MagicMock() → debe devolver 0 vía _tok()
        actual, baseline = _track_cost(mock_usage, "claude-sonnet-4-6")
        assert isinstance(actual, float)
        assert isinstance(baseline, float)

    def test_saving_pct_zero_when_no_calls(self):
        from backend.core.llm import get_cost_summary, _cost_tracker
        # Reset artificial para este test
        old_calls = _cost_tracker["calls"]
        _cost_tracker["calls"] = 0
        _cost_tracker["cache_hits"] = 0
        summary = get_cost_summary()
        assert summary["cache_hit_pct"] == 0
        _cost_tracker["calls"] = old_calls  # restaurar
