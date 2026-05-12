"""Tests for evaluation/budget.py — RunBudget + BudgetTracker + BudgetExceededError."""

from __future__ import annotations

import pytest

from evaluation.budget import BudgetExceededError, BudgetTracker, RunBudget

# ---------------------------------------------------------------------------
# RunBudget
# ---------------------------------------------------------------------------


def test_run_budget_from_env_zero_when_unset(monkeypatch) -> None:
    for key in [
        "RUN_MAX_LLM_CALLS",
        "RUN_MAX_WALLCLOCK_S",
        "RUN_MAX_COST_USD",
        "RUN_MAX_TOKENS",
    ]:
        monkeypatch.delenv(key, raising=False)
    budget = RunBudget.from_env()
    assert budget.max_llm_calls == 0
    assert budget.max_wallclock_s == 0.0
    assert budget.max_cost_usd == 0.0
    assert budget.max_tokens == 0


def test_run_budget_from_env_reads_values(monkeypatch) -> None:
    monkeypatch.setenv("RUN_MAX_LLM_CALLS", "10")
    monkeypatch.setenv("RUN_MAX_WALLCLOCK_S", "30.5")
    monkeypatch.setenv("RUN_MAX_COST_USD", "0.5")
    monkeypatch.setenv("RUN_MAX_TOKENS", "20000")
    budget = RunBudget.from_env()
    assert budget.max_llm_calls == 10
    assert budget.max_wallclock_s == pytest.approx(30.5)
    assert budget.max_cost_usd == pytest.approx(0.5)
    assert budget.max_tokens == 20000


# ---------------------------------------------------------------------------
# BudgetTracker
# ---------------------------------------------------------------------------


def _unlimited_tracker() -> BudgetTracker:
    return BudgetTracker(budget=RunBudget())


def test_tracker_initial_state() -> None:
    t = _unlimited_tracker()
    assert t.llm_calls == 0
    assert t.total_input_tokens == 0
    assert t.total_output_tokens == 0
    assert t.total_cost_usd == 0.0
    assert t.total_tokens == 0


def test_tracker_record_call_accumulates() -> None:
    t = _unlimited_tracker()
    t.record_call(100, 50, 0.001)
    t.record_call(200, 80, 0.002)
    assert t.llm_calls == 2
    assert t.total_input_tokens == 300
    assert t.total_output_tokens == 130
    assert t.total_cost_usd == pytest.approx(0.003)
    assert t.total_tokens == 430


def test_check_returns_none_when_within_limits() -> None:
    t = _unlimited_tracker()
    t.record_call(100, 50, 0.001)
    assert t.check() is None


def test_check_returns_reason_when_calls_exceeded() -> None:
    budget = RunBudget(max_llm_calls=2)
    t = BudgetTracker(budget=budget)
    t.record_call(100, 50, 0.001)
    t.record_call(100, 50, 0.001)
    reason = t.check()
    assert reason is not None
    assert "LLM call limit" in reason


def test_check_returns_reason_when_cost_exceeded() -> None:
    budget = RunBudget(max_cost_usd=0.001)
    t = BudgetTracker(budget=budget)
    t.record_call(10000, 5000, 0.005)
    reason = t.check()
    assert reason is not None
    assert "Cost limit" in reason


def test_check_returns_reason_when_tokens_exceeded() -> None:
    budget = RunBudget(max_tokens=100)
    t = BudgetTracker(budget=budget)
    t.record_call(60, 60, 0.0)
    reason = t.check()
    assert reason is not None
    assert "Token limit" in reason


def test_raise_if_exceeded_raises_budget_exceeded_error() -> None:
    budget = RunBudget(max_llm_calls=1)
    t = BudgetTracker(budget=budget)
    t.record_call(10, 10, 0.0)
    with pytest.raises(BudgetExceededError) as exc_info:
        t.raise_if_exceeded()
    assert exc_info.value.tracker is t
    assert "LLM call limit" in exc_info.value.reason


def test_raise_if_exceeded_does_not_raise_when_within_limits() -> None:
    t = _unlimited_tracker()
    t.record_call(100, 50, 0.001)
    t.raise_if_exceeded()  # should not raise
