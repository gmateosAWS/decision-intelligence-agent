"""Tests for budget integration in agents/runner.py (item 8.7.b)."""

from __future__ import annotations

from unittest.mock import MagicMock

from agents.runner import RunResult, run_query
from evaluation.budget import BudgetExceededError, BudgetTracker, RunBudget

# ---------------------------------------------------------------------------
# RunResult fields
# ---------------------------------------------------------------------------


def test_run_result_has_cost_fields() -> None:
    r = RunResult(answer="hi", session_id="s", run_id="r", success=True)
    assert r.total_input_tokens == 0
    assert r.total_output_tokens == 0
    assert r.total_cost_usd == 0.0
    assert r.llm_calls_count == 0
    assert r.budget_exceeded is False
    assert r.budget_exceeded_reason is None


def test_run_result_budget_exceeded_fields() -> None:
    r = RunResult(
        answer="stopped",
        session_id="s",
        run_id="r",
        success=False,
        budget_exceeded=True,
        budget_exceeded_reason="Cost limit reached ($1.00/$0.50)",
    )
    assert r.budget_exceeded is True
    assert "Cost limit" in r.budget_exceeded_reason


# ---------------------------------------------------------------------------
# run_query — budget exceeded path
# ---------------------------------------------------------------------------


def _make_observer():
    obs = MagicMock()
    obs.langsmith_config.return_value = {"configurable": {}}
    obs.start_run.return_value = "run123"
    obs.end_run.return_value = {}
    obs.record_cost = MagicMock()
    return obs


def _make_graph_raise_budget(tracker_holder):
    """Return a fake graph whose invoke() raises BudgetExceededError."""

    def _invoke(state, config):
        bt = config["configurable"].get("budget_tracker")
        if bt is not None:
            tracker_holder.append(bt)
        budget = RunBudget(max_llm_calls=1)
        t = BudgetTracker(budget=budget)
        t.record_call(100, 50, 0.001)
        raise BudgetExceededError("LLM call limit reached (1/1)", t)

    g = MagicMock()
    g.invoke.side_effect = _invoke
    return g


def test_run_query_returns_budget_exceeded_result(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    tracker_holder = []
    graph = _make_graph_raise_budget(tracker_holder)
    observer = _make_observer()

    result = run_query("test query", "session_abc", observer, graph)

    assert result.success is False
    assert result.budget_exceeded is True
    assert result.error_type == "BudgetExceededError"
    assert "Budget ceiling reached" in result.answer
    observer.record_cost.assert_called()
