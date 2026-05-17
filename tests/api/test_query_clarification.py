"""
tests/api/test_query_clarification.py
----------------------------------------
Verify that POST /v1/query returns HTTP 200 with clarification fields
when the agent detects an ungrounded token (item 5.9).

No actual agent invocation — run_query is mocked.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_query_returns_200_with_clarification_fields_on_ungrounded_token():
    """POST /v1/query returns 200 (not 500) when clarification_needed=True."""
    from agents.runner import RunResult

    clarification_result = RunResult(
        answer="I could not recognise 'price' as a variable in this domain.",
        session_id="test-session",
        run_id="run-001",
        success=False,
        error=None,
        error_type=None,
        latencies={},
        clarification_needed=True,
        clarification_message=(
            "I could not recognise 'price' as a variable in this domain. "
            "Valid variables are: bed_capacity, staffing_ratio, patient_throughput."
        ),
    )

    with patch("agents.runner.run_query", return_value=clarification_result):
        response = client.post(
            "/v1/query",
            json={"query": "simulate at price=30"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["clarification_needed"] is True
    assert body["clarification_message"] is not None
    assert "price" in body["clarification_message"]
