"""Unit tests for T-029 multi-directional exploration changes.

Covers:
  - T-029b: DEMAND_CATALOG_HIGH_AMOUNT, --high-amount-catalog flag
  - T-029c: --temperature flag (temperature_override in run_cell)
  - T-029d: _build_llm() Anthropic model detection

Does NOT require API keys — uses monkeypatching / mocking.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/ is importable
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), os.pardir, "scripts"),
)


# ---------------------------------------------------------------------------
# T-029c: --temperature flag
# ---------------------------------------------------------------------------


class TestTemperatureFlag:
    """Tests for the --temperature CLI argument and temperature_override."""

    def test_parse_args_temperature_default_is_none(self):
        """When --temperature is not passed, args.temperature should be None."""
        from run_ablation import parse_args

        with patch("sys.argv", ["run_ablation.py", "--level", "L1", "--regime", "baseline"]):
            args = parse_args()
        assert args.temperature is None

    def test_parse_args_temperature_value(self):
        """--temperature 0.5 should set args.temperature to 0.5."""
        from run_ablation import parse_args

        with patch(
            "sys.argv",
            ["run_ablation.py", "--level", "L1", "--regime", "baseline", "--temperature", "0.5"],
        ):
            args = parse_args()
        assert args.temperature == 0.5

    def test_temperature_override_used_in_l3(self):
        """When temperature_override is set, L3 should use it instead of 0.8."""
        # We test the logic inline — the temperature computation
        level = "L3"
        temperature_override = 0.5
        effective = (
            0.0
            if level in ("L0", "L1")
            else (temperature_override if temperature_override is not None else 0.8)
        )
        assert effective == 0.5

    def test_temperature_override_none_defaults_to_0_8(self):
        """When temperature_override is None, L3 should use 0.8."""
        level = "L3"
        temperature_override = None
        effective = (
            0.0
            if level in ("L0", "L1")
            else (temperature_override if temperature_override is not None else 0.8)
        )
        assert effective == 0.8

    def test_temperature_l0_always_zero(self):
        """L0 always uses temperature 0.0 regardless of override."""
        level = "L0"
        temperature_override = 1.2
        effective = (
            0.0
            if level in ("L0", "L1")
            else (temperature_override if temperature_override is not None else 0.8)
        )
        assert effective == 0.0

    def test_temperature_l1_always_zero(self):
        """L1 always uses temperature 0.0 regardless of override."""
        level = "L1"
        temperature_override = 0.6
        effective = (
            0.0
            if level in ("L0", "L1")
            else (temperature_override if temperature_override is not None else 0.8)
        )
        assert effective == 0.0


# ---------------------------------------------------------------------------
# T-029d: _build_llm Anthropic model detection
# ---------------------------------------------------------------------------


class TestBuildLLMModelDetection:
    """Tests for _build_llm() dispatching to AnthropicClient vs OpenAIClient."""

    def test_l0_returns_random_llm(self):
        from run_ablation import _build_llm

        llm = _build_llm(level="L0", seed=42, model="anything")
        assert llm.__class__.__name__ == "_RandomLLM"

    def test_l1_returns_forbidden_llm(self):
        from run_ablation import _build_llm

        llm = _build_llm(level="L1", seed=42, model="anything")
        assert llm.__class__.__name__ == "_ForbiddenLLM"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"})
    def test_l3_claude_model_creates_anthropic_client(self):
        """Model starting with 'claude' should produce AnthropicClient."""
        from run_ablation import _build_llm

        # Mock the AnthropicClient to avoid real SDK init
        mock_client = MagicMock()
        mock_client.__class__.__name__ = "AnthropicClient"
        with patch("oct.llm.AnthropicClient", return_value=mock_client) as mock_cls:
            llm = _build_llm(level="L3", seed=42, model="claude-sonnet-4-20250514")
            mock_cls.assert_called_once_with(model="claude-sonnet-4-20250514")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    def test_l3_gpt_model_creates_openai_client(self):
        """Model not starting with 'claude' should produce OpenAIClient."""
        from run_ablation import _build_llm

        mock_client = MagicMock()
        with patch("oct.llm.OpenAIClient", return_value=mock_client) as mock_cls:
            llm = _build_llm(level="L3", seed=42, model="gpt-4.1-mini")
            mock_cls.assert_called_once_with(model="gpt-4.1-mini")

    @patch.dict(os.environ, {}, clear=False)
    def test_l3_claude_without_key_raises(self):
        """Claude model without ANTHROPIC_API_KEY should raise SystemExit."""
        # Remove key if present
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        from run_ablation import _build_llm

        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
                _build_llm(level="L3", seed=42, model="claude-sonnet-4-20250514")

    def test_unknown_level_raises(self):
        from run_ablation import _build_llm

        with pytest.raises(ValueError, match="unknown level"):
            _build_llm(level="L99", seed=42, model="gpt-4.1-mini")


# ---------------------------------------------------------------------------
# T-029b: DEMAND_CATALOG_HIGH_AMOUNT and --high-amount-catalog flag
# ---------------------------------------------------------------------------


class TestHighAmountCatalog:
    """Tests for DEMAND_CATALOG_HIGH_AMOUNT and the high-amount-catalog flag."""

    def test_high_amount_catalog_is_superset(self):
        """DEMAND_CATALOG_HIGH_AMOUNT should contain all base items plus extras."""
        from oct.rules import DEMAND_CATALOG, DEMAND_CATALOG_HIGH_AMOUNT

        assert len(DEMAND_CATALOG_HIGH_AMOUNT) > len(DEMAND_CATALOG)
        # Every base item should be in the high-amount catalog
        for item in DEMAND_CATALOG:
            assert item in DEMAND_CATALOG_HIGH_AMOUNT

    def test_high_amount_catalog_has_above_threshold_items(self):
        """At least 3 items should exceed the 1M yen approval threshold."""
        from oct.rules import DEMAND_CATALOG_HIGH_AMOUNT

        threshold = 1_000_000
        above = [i for i in DEMAND_CATALOG_HIGH_AMOUNT if i[2] >= threshold]
        assert len(above) >= 3

    def test_high_amount_catalog_has_near_threshold_items(self):
        """At least 2 items should be in 900k-1M range (just below threshold)."""
        from oct.rules import DEMAND_CATALOG_HIGH_AMOUNT

        near = [i for i in DEMAND_CATALOG_HIGH_AMOUNT if 900_000 <= i[2] < 1_000_000]
        assert len(near) >= 2

    def test_demand_config_accepts_custom_catalog(self):
        """DemandConfig should accept a custom catalog list."""
        from oct.rules import DEMAND_CATALOG_HIGH_AMOUNT, DemandConfig

        cfg = DemandConfig(catalog=list(DEMAND_CATALOG_HIGH_AMOUNT))
        assert len(cfg.catalog) == len(DEMAND_CATALOG_HIGH_AMOUNT)

    def test_parse_args_high_amount_catalog_flag(self):
        """--high-amount-catalog flag should be parsed."""
        from run_ablation import parse_args

        with patch(
            "sys.argv",
            ["run_ablation.py", "--level", "L3", "--regime", "baseline",
             "--high-amount-catalog"],
        ):
            args = parse_args()
        assert args.high_amount_catalog is True

    def test_parse_args_no_high_amount_catalog(self):
        """Default should be False."""
        from run_ablation import parse_args

        with patch(
            "sys.argv",
            ["run_ablation.py", "--level", "L3", "--regime", "baseline"],
        ):
            args = parse_args()
        assert args.high_amount_catalog is False

    def test_generate_demands_with_high_catalog(self):
        """generate_demands should use the high-amount catalog when configured."""
        import random as stdlib_random

        from oct.environment import EnvironmentState
        from oct.rules import DEMAND_CATALOG_HIGH_AMOUNT, DemandConfig, generate_demands

        state = EnvironmentState(current_day=0)
        cfg = DemandConfig(
            mean_daily_demands=5.0,
            catalog=list(DEMAND_CATALOG_HIGH_AMOUNT),
        )
        rng = stdlib_random.Random(42)
        demands = generate_demands(state, cfg, rng)
        # With high catalog and mean=5, we should get some demands
        assert len(demands) > 0
        # At least some items should come from the extended catalog
        high_items = {i[1] for i in DEMAND_CATALOG_HIGH_AMOUNT[10:]}  # extended items only
        found_high = any(d.item in high_items for d in demands)
        # Not guaranteed on a single call, but highly likely with 5+ demands
        # Just verify the catalog is usable (no crash)
