"""tests/api/test_query.py — POST /v1/query endpoint tests."""

from __future__ import annotations

import uuid


def test_query_returns_answer_and_session(client):
    response = client.post("/v1/query", json={"query": "What price maximises profit?"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] != ""
    assert "session_id" in data
    assert "run_id" in data
    assert data["tool_used"] == "optimization"


def test_query_creates_new_session_when_omitted(client):
    r1 = client.post("/v1/query", json={"query": "Optimise price"})
    r2 = client.post("/v1/query", json={"query": "Simulate at price 30"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Each call without session_id gets a fresh UUID
    assert r1.json()["session_id"] != r2.json()["session_id"]


def test_query_with_existing_session_reuses_id(client, mock_graph):
    existing_id = str(uuid.uuid4())
    response = client.post(
        "/v1/query",
        json={"query": "What if price is 30?", "session_id": existing_id},
    )
    assert response.status_code == 200
    assert response.json()["session_id"] == existing_id


def test_query_returns_503_on_llm_unavailable(client, mock_graph):
    from agents.llm_factory import LLMUnavailableError

    mock_graph.invoke.side_effect = LLMUnavailableError("All providers failed")
    try:
        response = client.post("/v1/query", json={"query": "fail"})
        assert response.status_code in (500, 503)
    finally:
        # Restore default behaviour
        mock_graph.invoke.side_effect = None
        mock_graph.invoke.return_value = {
            "answer": "The optimal price is approximately EUR 48.64.",
            "action": "optimization",
            "reasoning": "User is asking for price optimization.",
            "raw_result": {"optimal_price": 48.64, "expected_profit": 2139.0},
            "judge_score": 0.95,
            "judge_passed": True,
            "judge_revised": False,
        }


def test_query_empty_string_rejected(client):
    response = client.post("/v1/query", json={"query": ""})
    assert response.status_code == 422
