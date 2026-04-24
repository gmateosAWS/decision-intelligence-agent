"""tests/api/test_specs.py — /v1/specs endpoint tests."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

_YAML = """\
domain:
  name: test_domain
  description: Test
  version: '1.0.0'
variables:
  decisions:
    - name: price
      description: Price
      unit: EUR
      bounds: {min: 10, max: 50, steps: 10}
      default: 20
  intermediate: []
  targets:
    - name: profit
      description: Net profit
      unit: EUR
      formula: revenue - cost
      optimize: maximize
causal_relationships:
  - from: price
    to: profit
    type: direct
    description: price affects profit
constraints: []
business_parameters: {}
simulation:
  monte_carlo_runs: 100
  noise_std: 0.1
demand_model:
  base_demand: 100.0
  price_elasticity: -1.0
  marketing_effect: 0.001
  noise_sigma: 5.0
data_generation:
  n_samples: 100
  random_seed: 42
  price_min: 10.0
  price_max: 50.0
  marketing_min: 1000.0
  marketing_max: 20000.0
optimization:
  target: profit
  method: grid_search
  decision_variables: [price]
  fixed_variables: {}
"""


def _make_spec_row(status: str = "draft"):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.domain_name = "test_domain"
    row.version = "1.0.0"
    row.status = status
    row.created_at = "2026-04-24T10:00:00+00:00"
    row.description = "Test spec"
    row.yaml_content = _YAML
    return row


def _db_with_spec(spec_row):
    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.all.return_value = [spec_row]
    mock_session.get.return_value = spec_row
    return mock_session


def test_list_specs(client):
    spec = _make_spec_row()
    from api.dependencies import get_db
    from api.main import app

    app.dependency_overrides[get_db] = lambda: _db_with_spec(spec)
    try:
        response = client.get("/v1/specs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["specs"][0]["domain_name"] == "test_domain"
        assert data["specs"][0]["yaml_content"] is None  # not in list view
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_get_spec_detail_includes_yaml(client):
    spec = _make_spec_row()
    spec_id = str(spec.id)

    from api.dependencies import get_db
    from api.main import app

    app.dependency_overrides[get_db] = lambda: _db_with_spec(spec)
    try:
        response = client.get(f"/v1/specs/{spec_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["yaml_content"] is not None
        assert "price" in data["yaml_content"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_get_spec_invalid_uuid(client):
    from api.dependencies import get_db
    from api.main import app

    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        response = client.get("/v1/specs/not-a-uuid")
        assert response.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_create_spec_from_yaml(client):
    new_spec = _make_spec_row()
    with patch("spec.spec_repository.create_spec", return_value=new_spec):
        response = client.post(
            "/v1/specs",
            json={"yaml_content": _YAML, "version": "1.0.0"},
        )
    assert response.status_code == 201
    assert response.json()["domain_name"] == "test_domain"


def test_create_spec_invalid_yaml(client):
    response = client.post(
        "/v1/specs",
        json={"yaml_content": "not: valid: yaml: [[[", "version": "1.0.0"},
    )
    assert response.status_code == 422


def test_activate_spec(client):
    spec = _make_spec_row(status="active")
    spec_id = str(spec.id)
    with patch("spec.spec_repository.activate_spec", return_value=spec):
        response = client.put(f"/v1/specs/{spec_id}/activate")
    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_get_spec_versions(client):
    spec = _make_spec_row()
    spec_id = str(spec.id)

    ver = MagicMock()
    ver.id = uuid.uuid4()
    ver.spec_id = spec.id
    ver.version = "1.0.0"
    ver.change_summary = "Initial version"
    ver.created_at = "2026-04-24T10:00:00+00:00"

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.all.return_value = [ver]

    from api.dependencies import get_db
    from api.main import app

    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        response = client.get(f"/v1/specs/{spec_id}/versions")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["version"] == "1.0.0"
    finally:
        app.dependency_overrides.pop(get_db, None)
