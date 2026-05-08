"""
tests/ci/test_smoke.py
----------------------
Smoke tests for CI: verify all main modules import without error and that
the API health endpoints respond correctly.

These tests run on every push (no DB, no LLM keys required). They catch
import-time IO regressions — the class of bug that caused the
'KeyError: agents.planner' incident (fixed in audit-P02).
"""

from __future__ import annotations


def test_imports_succeed() -> None:
    """All main modules must import cleanly — no import-time IO or missing deps."""
    import agents.llm_factory  # noqa: F401
    import agents.planner  # noqa: F401
    import agents.state  # noqa: F401
    import agents.tools  # noqa: F401
    import agents.workflow  # noqa: F401
    import api.main  # noqa: F401
    import api.routers.health  # noqa: F401
    import api.routers.query  # noqa: F401
    import config.settings  # noqa: F401
    import evaluation.metrics  # noqa: F401
    import evaluation.observer  # noqa: F401
    import knowledge.retriever  # noqa: F401
    import memory.checkpointer  # noqa: F401
    import optimization.optimizer  # noqa: F401
    import simulation.montecarlo  # noqa: F401
    import spec.spec_loader  # noqa: F401
    import system.system_graph  # noqa: F401
    import system.system_model  # noqa: F401


def test_api_healthz(client) -> None:
    """/healthz always returns 200 with status=ok."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_readyz_returns_expected_fields(client) -> None:
    """/readyz returns status, postgres and spec_loaded fields."""
    response = client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "postgres" in data
    assert "spec_loaded" in data
    assert data["status"] in ("ready", "degraded")


def test_api_debug_config_no_secrets(client) -> None:
    """/v1/debug/config exposes LLM config but never API keys."""
    response = client.get("/v1/debug/config")
    assert response.status_code == 200
    data = response.json()
    assert "planner_provider" in data
    assert "planner_model" in data
    assert "api_key" not in str(data).lower()
