"""tests/ci/conftest.py — Minimal fixtures for CI smoke tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """TestClient with graph dependency overridden (no LLM / DB required)."""
    from api.dependencies import get_graph
    from api.main import app

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {"answer": "ok", "action": "knowledge"}
    mock_graph.get_state.return_value = MagicMock(values={"history": []})
    app.dependency_overrides[get_graph] = lambda: mock_graph

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
