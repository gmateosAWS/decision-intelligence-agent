"""tests/api/test_sessions.py — /v1/sessions endpoint tests."""

from __future__ import annotations

from unittest.mock import patch

_SAMPLE_SESSIONS = [
    {
        "session_id": "aaaa-bbbb-cccc-dddd",
        "title": "What price maximises profit?",
        "created_at": "2026-04-24T10:00:00+00:00",
        "last_active": "2026-04-24T10:05:00+00:00",
        "turn_count": 3,
    },
    {
        "session_id": "eeee-ffff-0000-1111",
        "title": "Simulate at price 30",
        "created_at": "2026-04-24T09:00:00+00:00",
        "last_active": "2026-04-24T09:10:00+00:00",
        "turn_count": 1,
    },
]


def test_list_sessions_returns_list(client):
    with patch(
        "memory.session_manager.SessionManager.list_sessions",
        return_value=_SAMPLE_SESSIONS,
    ):
        response = client.get("/v1/sessions")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["sessions"]) == 2
    assert data["sessions"][0]["title"] == "What price maximises profit?"


def test_list_sessions_pagination(client):
    with patch(
        "memory.session_manager.SessionManager.list_sessions",
        return_value=_SAMPLE_SESSIONS,
    ):
        response = client.get("/v1/sessions?skip=1&limit=1")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["session_id"] == "eeee-ffff-0000-1111"


def test_get_session_returns_detail(client):
    sid = "aaaa-bbbb-cccc-dddd"
    with patch(
        "memory.session_manager.SessionManager.get_session",
        return_value=_SAMPLE_SESSIONS[0],
    ):
        response = client.get(f"/v1/sessions/{sid}")
    assert response.status_code == 200
    assert response.json()["session_id"] == sid
    assert response.json()["turn_count"] == 3


def test_get_session_not_found(client):
    with patch(
        "memory.session_manager.SessionManager.get_session",
        return_value=None,
    ):
        response = client.get("/v1/sessions/nonexistent")
    assert response.status_code == 404


def test_delete_session_returns_204(client):
    with patch(
        "memory.session_manager.SessionManager.delete_session",
        return_value=True,
    ):
        response = client.delete("/v1/sessions/aaaa-bbbb-cccc-dddd")
    assert response.status_code == 204


def test_delete_session_not_found(client):
    with patch(
        "memory.session_manager.SessionManager.delete_session",
        return_value=False,
    ):
        response = client.delete("/v1/sessions/nonexistent")
    assert response.status_code == 404
