"""tests/api/test_health.py — Health endpoint tests (no DB required)."""

from __future__ import annotations


def test_healthz_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_returns_status_fields(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "postgres" in data
    assert "spec_loaded" in data
    assert data["status"] in ("ready", "degraded")


def test_debug_config_returns_llm_settings(client):
    response = client.get("/v1/debug/config")
    assert response.status_code == 200
    data = response.json()
    assert "planner_provider" in data
    assert "planner_model" in data
    assert "synthesizer_provider" in data
    assert "judge_provider" in data
    # No secrets in the response
    assert "api_key" not in str(data).lower()
