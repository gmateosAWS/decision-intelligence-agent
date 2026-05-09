"""
tests/api/test_specs_bump.py
-----------------------------
Unit tests for POST /v1/specs/{spec_id}/bump.

Uses FastAPI TestClient with get_db overridden and spec_repository functions
patched at source — no live database required.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db
from api.main import app

# ---------------------------------------------------------------------------
# Constants and helpers
# ---------------------------------------------------------------------------

_PARENT_ID = uuid.uuid4()
_DOMAIN = "retail_pricing"

_BASE_YAML = """\
domain:
  name: retail_pricing
variables:
  decisions:
    - name: price
      bounds: {min: 10.0, max: 50.0, steps: 10}
      default: 25.0
  targets:
    - name: profit
  intermediate: []
causal_relationships:
  - from: price
    to: profit
"""

_YAML_DESCRIPTION_CHANGE = _BASE_YAML.replace(
    "  name: retail_pricing\n",
    "  name: retail_pricing\n  description: Updated description\n",
)

_YAML_EXTRA_VARIABLE = _BASE_YAML.replace(
    "  targets:\n",
    "    - name: marketing\n"
    "      bounds: {min: 0, max: 10000, steps: 5}\n"
    "      default: 1000\n"
    "  targets:\n",
)


def _make_parent(version: str = "1.0.0") -> MagicMock:
    m = MagicMock()
    m.id = _PARENT_ID
    m.domain_name = _DOMAIN
    m.version = version
    m.yaml_content = _BASE_YAML
    return m


def _make_new_spec(version: str) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.domain_name = _DOMAIN
    m.version = version
    m.status = "draft"
    return m


# ---------------------------------------------------------------------------
# Fixture: TestClient with get_db dependency overridden
# ---------------------------------------------------------------------------


@pytest.fixture()
def api(request):
    """Yields (client, db_mock).  db_mock.get() returns the parent spec by default."""
    parent_version = getattr(request, "param", "1.0.0")
    db_mock = MagicMock()
    db_mock.get.return_value = _make_parent(parent_version)

    app.dependency_overrides[get_db] = lambda: db_mock
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, db_mock
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_bump_endpoint_auto_detect_patch(api) -> None:
    """Description-only change → auto-detected PATCH → version 1.0.1."""
    from spec.versioning import SpecVersion

    client, db = api
    new_spec = _make_new_spec("1.0.1")

    with (
        patch(
            "spec.spec_repository._max_version_for_domain",
            return_value=SpecVersion.parse("1.0.0"),
        ),
        patch("spec.spec_repository.update_spec", return_value=new_spec) as mock_update,
    ):
        resp = client.post(
            f"/v1/specs/{_PARENT_ID}/bump",
            json={"yaml_content": _YAML_DESCRIPTION_CHANGE},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["bump_type"] == "patch"
    assert data["auto_detected"] is True
    assert data["version"] == "1.0.1"
    assert uuid.UUID(data["spec_id"]) == new_spec.id
    mock_update.assert_called_once()


def test_bump_endpoint_auto_detect_major(api) -> None:
    """Added decision variable → auto-detected MAJOR → version 2.0.0."""
    from spec.versioning import SpecVersion

    client, db = api
    new_spec = _make_new_spec("2.0.0")

    with (
        patch(
            "spec.spec_repository._max_version_for_domain",
            return_value=SpecVersion.parse("1.0.0"),
        ),
        patch("spec.spec_repository.update_spec", return_value=new_spec),
    ):
        resp = client.post(
            f"/v1/specs/{_PARENT_ID}/bump",
            json={"yaml_content": _YAML_EXTRA_VARIABLE},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["bump_type"] == "major"
    assert data["auto_detected"] is True
    assert data["version"] == "2.0.0"


def test_bump_endpoint_explicit_type(api) -> None:
    """Explicit bump_type='minor' overrides auto-detection."""
    from spec.versioning import SpecVersion

    client, db = api
    new_spec = _make_new_spec("1.1.0")

    with (
        patch(
            "spec.spec_repository._max_version_for_domain",
            return_value=SpecVersion.parse("1.0.0"),
        ),
        patch("spec.spec_repository.update_spec", return_value=new_spec),
    ):
        resp = client.post(
            f"/v1/specs/{_PARENT_ID}/bump",
            json={
                "yaml_content": _YAML_DESCRIPTION_CHANGE,
                "bump_type": "minor",
                "change_summary": "Explicit minor bump",
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["bump_type"] == "minor"
    assert data["auto_detected"] is False
    assert data["version"] == "1.1.0"


def test_bump_endpoint_invalid_bump_type(api) -> None:
    """Unknown bump_type returns 422."""
    client, _ = api
    resp = client.post(
        f"/v1/specs/{_PARENT_ID}/bump",
        json={"yaml_content": _BASE_YAML, "bump_type": "superduper"},
    )
    assert resp.status_code == 422


def test_bump_endpoint_spec_not_found(api) -> None:
    """Missing spec_id returns 404."""
    client, db = api
    db.get.return_value = None  # spec not found

    resp = client.post(
        f"/v1/specs/{_PARENT_ID}/bump",
        json={"yaml_content": _BASE_YAML},
    )
    assert resp.status_code == 404


def test_bump_endpoint_invalid_spec_id(api) -> None:
    """Non-UUID spec_id returns 400."""
    client, _ = api
    resp = client.post(
        "/v1/specs/not-a-uuid/bump",
        json={"yaml_content": _BASE_YAML},
    )
    assert resp.status_code == 400
