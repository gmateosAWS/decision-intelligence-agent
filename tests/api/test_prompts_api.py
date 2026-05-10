"""
tests/api/test_prompts_api.py
------------------------------
Unit tests for the Prompt Registry API endpoints (item 10.1).

No database required — registry functions are mocked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from prompts.models import PromptRecord, PromptStatus


def _make_record(
    prompt_id: str = "planner",
    version: str = "1.0.0",
    status: PromptStatus = PromptStatus.CERTIFIED,
    stage: str = "planner",
    content: str = "Hello {domain_name}",
) -> PromptRecord:
    now = datetime.now(timezone.utc)
    return PromptRecord(
        id=prompt_id,
        version=version,
        status=status,
        stage=stage,
        content=content,
        variables=["domain_name"],
        created_at=now,
        changed_at=now,
    )


@pytest.fixture(scope="module")
def client():
    from api.main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /v1/prompts
# ---------------------------------------------------------------------------


def test_list_prompts(client):
    records = [
        _make_record("planner", "1.0.0", PromptStatus.CERTIFIED, "planner"),
        _make_record("synthesizer", "1.0.0", PromptStatus.CERTIFIED, "synthesizer"),
    ]
    with patch("prompts.registry.list_prompts", return_value=records):
        resp = client.get("/v1/prompts")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    ids = {p["id"] for p in body["prompts"]}
    assert ids == {"planner", "synthesizer"}


def test_list_prompts_filter_by_stage(client):
    records = [_make_record("planner", "1.0.0", PromptStatus.CERTIFIED, "planner")]
    with patch("prompts.registry.list_prompts", return_value=records):
        resp = client.get("/v1/prompts?stage=planner")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_list_prompts_invalid_status_returns_400(client):
    resp = client.get("/v1/prompts?status=invalid_status")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /v1/prompts/{id}/{version}
# ---------------------------------------------------------------------------


def test_get_prompt(client):
    record = _make_record("planner", "1.0.0")
    with patch("prompts.registry.get_prompt", return_value=record):
        resp = client.get("/v1/prompts/planner/1.0.0")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "planner"
    assert body["version"] == "1.0.0"
    assert body["status"] == "certified"


def test_get_prompt_not_found(client):
    with patch("prompts.registry.get_prompt", return_value=None):
        resp = client.get("/v1/prompts/planner/9.9.9")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /v1/prompts
# ---------------------------------------------------------------------------


def test_create_prompt(client):
    created = _make_record(
        "planner", "2.0.0", PromptStatus.DRAFT, "planner", "New {domain_name}"
    )
    with patch("prompts.registry.create_prompt", return_value=created):
        resp = client.post(
            "/v1/prompts",
            json={
                "id": "planner",
                "stage": "planner",
                "content": "New {domain_name}",
                "version": "2.0.0",
                "variables": ["domain_name"],
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["version"] == "2.0.0"
    assert body["status"] == "draft"


def test_create_prompt_conflict_returns_409(client):
    with patch(
        "prompts.registry.create_prompt", side_effect=ValueError("already exists")
    ):
        resp = client.post(
            "/v1/prompts",
            json={
                "id": "planner",
                "stage": "planner",
                "content": "Hello {domain_name}",
                "version": "1.0.0",
            },
        )

    assert resp.status_code == 409


def test_create_prompt_no_db_returns_503(client):
    with patch("prompts.registry.create_prompt", side_effect=RuntimeError("no DB")):
        resp = client.post(
            "/v1/prompts",
            json={
                "id": "planner",
                "stage": "planner",
                "content": "Hello {domain_name}",
                "version": "1.0.0",
            },
        )

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# PUT /v1/prompts/{id}/{version}/certify
# ---------------------------------------------------------------------------


def test_certify_prompt(client):
    certified = _make_record("planner", "2.0.0", PromptStatus.CERTIFIED)
    with patch("prompts.registry.certify_prompt", return_value=certified):
        resp = client.put("/v1/prompts/planner/2.0.0/certify")

    assert resp.status_code == 200
    assert resp.json()["status"] == "certified"


def test_certify_prompt_not_found_returns_404(client):
    with patch("prompts.registry.certify_prompt", side_effect=ValueError("not found")):
        resp = client.put("/v1/prompts/planner/9.9.9/certify")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /v1/prompts/{id}/{version}/deprecate
# ---------------------------------------------------------------------------


def test_deprecate_prompt(client):
    deprecated = _make_record("planner", "1.0.0", PromptStatus.DEPRECATED)
    with patch("prompts.registry.deprecate_prompt", return_value=deprecated):
        resp = client.put(
            "/v1/prompts/planner/1.0.0/deprecate",
            json={"replacement_id": "planner"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "deprecated"


def test_deprecate_prompt_not_found_returns_404(client):
    with patch(
        "prompts.registry.deprecate_prompt", side_effect=ValueError("not found")
    ):
        resp = client.put("/v1/prompts/planner/9.9.9/deprecate")

    assert resp.status_code == 404
