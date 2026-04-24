"""
tests/api/conftest.py
---------------------
Shared fixtures for API tests.

All tests use FastAPI's TestClient with dependency overrides so no live
LLM, DB, or Postgres instance is required.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def mock_graph():
    """A MagicMock graph that returns a well-formed optimization result."""
    g = MagicMock()
    g.invoke.return_value = {
        "answer": "The optimal price is approximately EUR 48.64.",
        "action": "optimization",
        "reasoning": "User is asking for price optimization.",
        "raw_result": {"optimal_price": 48.64, "expected_profit": 2139.0},
        "judge_score": 0.95,
        "judge_passed": True,
        "judge_revised": False,
    }
    g.get_state.return_value = MagicMock(values={"history": []})
    return g


@pytest.fixture(scope="module")
def client(mock_graph):
    """TestClient with the graph dependency overridden."""
    from api.dependencies import get_graph
    from api.main import app

    app.dependency_overrides[get_graph] = lambda: mock_graph

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
