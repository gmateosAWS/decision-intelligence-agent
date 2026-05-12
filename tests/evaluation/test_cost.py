"""Tests for evaluation/cost.py — model pricing and cost calculation (item 8.7.a)."""

from __future__ import annotations

import pytest

from evaluation.cost import calculate_cost_usd, get_pricing, reload_pricing


def test_known_model_returns_pricing() -> None:
    pricing = get_pricing("gpt-4o-mini")
    assert pricing is not None
    assert pricing.input_per_1k_tokens > 0
    assert pricing.output_per_1k_tokens > 0


def test_unknown_model_falls_back_to_unknown_sentinel() -> None:
    pricing = get_pricing("nonexistent-model-xyz")
    assert pricing is not None
    # sentinel has -1 values
    assert pricing.input_per_1k_tokens == -1
    assert pricing.output_per_1k_tokens == -1


def test_calculate_cost_zero_tokens() -> None:
    assert calculate_cost_usd("gpt-4o-mini", 0, 0) == 0.0


def test_calculate_cost_known_model() -> None:
    cost = calculate_cost_usd("gpt-4o-mini", 1000, 1000)
    assert cost > 0
    # gpt-4o-mini: 0.00015 + 0.0006 = 0.00075
    assert abs(cost - 0.00075) < 1e-8


def test_calculate_cost_free_model_returns_zero() -> None:
    cost = calculate_cost_usd("llama3", 10000, 5000)
    assert cost == 0.0


def test_calculate_cost_unknown_sentinel_returns_zero() -> None:
    cost = calculate_cost_usd("nonexistent-model", 1000, 500)
    assert cost == 0.0


def test_reload_pricing_clears_cache() -> None:
    # Should not raise and re-loads without error
    reload_pricing()
    pricing = get_pricing("gpt-4o")
    assert pricing is not None
    assert pricing.input_per_1k_tokens == pytest.approx(0.005)
