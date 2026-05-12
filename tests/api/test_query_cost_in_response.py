"""Tests that QueryResponse includes cost fields (item 8.7.a+b)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from agents.runner import RunResult
from api.main import app

client = TestClient(app, raise_server_exceptions=False)


def _mock_run_result(**overrides) -> RunResult:
    defaults = dict(
        answer="ok",
        session_id=str(uuid.uuid4()),
        run_id="abc123",
        success=True,
        total_input_tokens=500,
        total_output_tokens=250,
        total_cost_usd=0.000225,
        llm_calls_count=3,
        budget_exceeded=False,
        budget_exceeded_reason=None,
    )
    defaults.update(overrides)
    return RunResult(**defaults)


def test_query_response_includes_cost_fields() -> None:
    # All imports in the endpoint are deferred (inside function body).
    # Patch at source modules so the deferred imports resolve to mocks.
    with (
        patch("agents.runner.run_query", return_value=_mock_run_result()),
        patch("evaluation.observer.AgentObserver"),
        patch("memory.checkpointer.register_turn"),
        patch("api.dependencies.get_graph"),
    ):
        resp = client.post("/v1/query", json={"query": "test"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_input_tokens"] == 500
    assert body["total_output_tokens"] == 250
    assert body["total_cost_usd"] == 0.000225
    assert body["llm_calls_count"] == 3
    assert body["budget_exceeded"] is False
    assert body["budget_exceeded_reason"] is None


def test_query_response_budget_exceeded_fields() -> None:
    with (
        patch(
            "agents.runner.run_query",
            return_value=_mock_run_result(
                budget_exceeded=True,
                budget_exceeded_reason="Cost limit reached ($1.01/$1.00)",
                success=False,
                error="Cost limit reached ($1.01/$1.00)",
                error_type="BudgetExceededError",
            ),
        ),
        patch("evaluation.observer.AgentObserver"),
        patch("memory.checkpointer.register_turn"),
        patch("api.dependencies.get_graph"),
    ):
        resp = client.post("/v1/query", json={"query": "test"})

    # BudgetExceededError is not LLMUnavailableError → 500
    assert resp.status_code == 500
