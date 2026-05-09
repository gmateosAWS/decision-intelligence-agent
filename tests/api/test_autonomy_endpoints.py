"""
tests/api/test_autonomy_endpoints.py
--------------------------------------
Unit tests for GET /v1/specs/{id}/autonomy and PUT /v1/specs/{id}/autonomy.

Uses FastAPI TestClient with get_db overridden — no live database required.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from api.dependencies import get_db
from api.main import app

_SPEC_ID = uuid.uuid4()
_DOMAIN = "test_domain"

_SAMPLE_PARSED = {
    "domain": {"name": _DOMAIN, "description": "test", "version": "1.0.0"},
    "variables": {
        "decisions": [
            {
                "name": "price",
                "description": "price",
                "unit": "EUR",
                "bounds": {"min": 10, "max": 50, "steps": 10},
                "default": 25,
            }
        ],
        "intermediate": [],
        "targets": [{"name": "profit", "description": "profit", "unit": "EUR"}],
    },
    "causal_relationships": [{"from": "price", "to": "profit", "type": "direct"}],
    "autonomy_policy": {
        "default_level": "auto",
        "tools": [
            {"tool": "optimization", "level": "human_confirms", "reason": "test"},
        ],
    },
}

_SAMPLE_YAML = yaml.dump(_SAMPLE_PARSED, allow_unicode=True, sort_keys=False)


def _make_spec(version: str = "1.0.0") -> MagicMock:
    m = MagicMock()
    m.id = _SPEC_ID
    m.version = version
    m.domain_name = _DOMAIN
    m.yaml_content = _SAMPLE_YAML
    m.parsed_content = _SAMPLE_PARSED
    m.status = "active"
    m.created_at = "2026-05-09T00:00:00"
    m.description = None
    return m


@pytest.fixture()
def client():
    db_mock = MagicMock()
    db_mock.get.return_value = _make_spec()
    app.dependency_overrides[get_db] = lambda: db_mock
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, db_mock
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /v1/specs/{id}/autonomy
# ---------------------------------------------------------------------------


def test_get_autonomy_policy_returns_policy(client) -> None:
    c, _ = client
    resp = c.get(f"/v1/specs/{_SPEC_ID}/autonomy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_level"] == "auto"
    tools_by_name = {t["tool"]: t for t in data["tools"]}
    assert tools_by_name["optimization"]["level"] == "human_confirms"


def test_get_autonomy_policy_not_found(client) -> None:
    c, db = client
    db.get.return_value = None
    resp = c.get(f"/v1/specs/{_SPEC_ID}/autonomy")
    assert resp.status_code == 404


def test_get_autonomy_policy_invalid_id(client) -> None:
    c, _ = client
    resp = c.get("/v1/specs/not-a-uuid/autonomy")
    assert resp.status_code == 400


def test_get_autonomy_policy_missing_section(client) -> None:
    """Spec YAML with no autonomy_policy section returns all-auto defaults."""
    c, db = client
    spec = _make_spec()
    parsed_no_policy = dict(_SAMPLE_PARSED)
    parsed_no_policy.pop("autonomy_policy", None)
    spec.parsed_content = parsed_no_policy
    db.get.return_value = spec
    resp = c.get(f"/v1/specs/{_SPEC_ID}/autonomy")
    assert resp.status_code == 200
    assert resp.json()["default_level"] == "auto"
    assert resp.json()["tools"] == []


# ---------------------------------------------------------------------------
# PUT /v1/specs/{id}/autonomy
# ---------------------------------------------------------------------------


def test_update_autonomy_policy_creates_new_version(client) -> None:
    c, db = client
    new_spec = _make_spec("1.1.0")

    with (
        patch("spec.spec_repository.update_spec", return_value=new_spec),
        patch("spec.spec_repository.activate_spec", return_value=new_spec),
    ):
        resp = c.put(
            f"/v1/specs/{_SPEC_ID}/autonomy",
            json={"default_level": "human_confirms"},
        )

    assert resp.status_code == 200


def test_update_autonomy_policy_not_found(client) -> None:
    c, db = client
    db.get.return_value = None
    resp = c.put(
        f"/v1/specs/{_SPEC_ID}/autonomy",
        json={"default_level": "auto"},
    )
    assert resp.status_code == 404


def test_update_autonomy_policy_invalid_id(client) -> None:
    c, _ = client
    resp = c.put("/v1/specs/bad-id/autonomy", json={"default_level": "auto"})
    assert resp.status_code == 400
