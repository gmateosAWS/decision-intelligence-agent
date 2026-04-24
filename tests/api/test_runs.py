"""tests/api/test_runs.py — /v1/runs endpoint tests."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock


def _make_run_row(run_id: str = "abc123def456", action: str = "optimization"):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.run_id = run_id
    row.session_id = uuid.uuid4()
    row.timestamp = "2026-04-24T10:00:00+00:00"
    row.query = "What price maximises profit?"
    row.action = action
    row.success = True
    row.total_latency_ms = 1230.5
    row.judge_score = 0.95
    row.confidence_score = 1.0
    row.spec_version = "1.0.0"
    row.answer_length = 180
    row.reasoning = "User wants optimization."
    row.raw_result = {"optimal_price": 48.64}
    row.error = None
    return row


def test_list_runs_without_db_returns_503(client):
    """Without DATABASE_URL set the endpoint returns 503."""
    import os

    if os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is set — this test is for no-DB mode only")

    response = client.get("/v1/runs")
    assert response.status_code == 503


def test_list_runs_with_db(client):
    """With DATABASE_URL and a mocked session, returns a list."""
    import os

    os.environ["DATABASE_URL"] = "postgresql://test"
    try:
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [_make_run_row()]

        from api.dependencies import get_db
        from api.main import app

        app.dependency_overrides[get_db] = lambda: mock_session
        response = client.get("/v1/runs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["runs"][0]["action"] == "optimization"
    finally:
        from api.dependencies import get_db
        from api.main import app

        app.dependency_overrides.pop(get_db, None)
        os.environ.pop("DATABASE_URL", None)


def test_get_run_not_found(client):
    import os

    os.environ["DATABASE_URL"] = "postgresql://test"
    try:
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        from api.dependencies import get_db
        from api.main import app

        app.dependency_overrides[get_db] = lambda: mock_session
        response = client.get("/v1/runs/nonexistent-run-id")
        assert response.status_code == 404
    finally:
        from api.dependencies import get_db
        from api.main import app

        app.dependency_overrides.pop(get_db, None)
        os.environ.pop("DATABASE_URL", None)


def test_filter_runs_by_invalid_session_uuid(client):
    import os

    os.environ["DATABASE_URL"] = "postgresql://test"
    try:
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.order_by.return_value = mock_query

        from api.dependencies import get_db
        from api.main import app

        app.dependency_overrides[get_db] = lambda: mock_session
        response = client.get("/v1/runs?session_id=not-a-uuid")
        assert response.status_code == 400
    finally:
        from api.dependencies import get_db
        from api.main import app

        app.dependency_overrides.pop(get_db, None)
        os.environ.pop("DATABASE_URL", None)


import pytest  # noqa: E402 — needed for skip
