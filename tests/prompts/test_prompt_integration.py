"""
tests/prompts/test_prompt_integration.py
-----------------------------------------
Integration tests: verify that agents use the registry prompt when available
and fall back to the inline template when the registry is empty/unavailable.

No LLM calls are made — planner LLMs are mocked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from prompts.models import PromptRecord, PromptStatus


def _make_certified(stage: str, content: str, version: str = "2.0.0") -> PromptRecord:
    now = datetime.now(timezone.utc)
    return PromptRecord(
        id=stage,
        version=version,
        status=PromptStatus.CERTIFIED,
        stage=stage,
        content=content,
        variables=[],
        created_at=now,
        changed_at=now,
    )


def _reset_planner_cache():
    """Reset module-level prompt cache so tests don't bleed into each other."""
    import agents.planner as planner_mod

    planner_mod._SYSTEM_PROMPT = None
    planner_mod._SYSTEM_PROMPT_VERSION = None
    planner_mod._llm = None
    planner_mod._llm_structured = None
    planner_mod._fallback_llm_structured = None


@pytest.fixture(autouse=True)
def reset_caches():
    _reset_planner_cache()
    yield
    _reset_planner_cache()


# ---------------------------------------------------------------------------
# Planner — prompt comes from registry
# ---------------------------------------------------------------------------


def test_planner_uses_registry_prompt_when_available(monkeypatch):
    """Planner renders registry prompt when certified prompt is available."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    registry_content = (
        "REGISTRY PLANNER PROMPT for {domain_name}. {examples} | {vars_description}"
    )
    certified = _make_certified("planner", registry_content, "2.0.0")

    mock_selection = MagicMock()
    mock_selection.tool = "knowledge"
    mock_selection.reasoning = "test"
    mock_selection.params = []
    mock_selection.language = "en"

    with (
        patch("prompts.registry.get_certified_prompt", return_value=certified),
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner.invoke_with_fallback", return_value=mock_selection),
        patch("agents.planner.get_spec") as mock_spec,
    ):
        spec = MagicMock()
        spec.domain_name = "TestDomain"
        spec.decision_variables = [
            MagicMock(
                name="price",
                description="Price",
                unit="EUR",
                bounds_min=10,
                bounds_max=50,
                default=25,
            )
        ]
        spec.autonomy_policy.get_level.return_value = MagicMock(value="auto")
        mock_spec.return_value = spec

        from agents.planner import _get_system_prompt

        prompt, version = _get_system_prompt()

    assert "REGISTRY PLANNER PROMPT" in prompt
    assert "TestDomain" in prompt
    assert version == "2.0.0"


def test_planner_falls_back_to_inline_when_registry_empty(monkeypatch):
    """When registry returns None, planner uses the inline PLANNER_SYSTEM_TEMPLATE."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with patch("agents.planner.get_spec") as mock_spec:
        spec = MagicMock()
        spec.domain_name = "RetailDomain"
        spec.decision_variables = [
            MagicMock(
                name="price",
                description="Price",
                unit="EUR",
                bounds_min=10,
                bounds_max=50,
                default=25,
            )
        ]
        mock_spec.return_value = spec

        from agents.planner import _get_system_prompt

        prompt, version = _get_system_prompt()

    assert "RetailDomain" in prompt
    assert "OPTIMIZATION" in prompt
    assert version is None


# ---------------------------------------------------------------------------
# planner_node returns prompt_version in state
# ---------------------------------------------------------------------------


def test_planner_node_returns_prompt_version_in_state(monkeypatch):
    """planner_node() must include planner_prompt_version in the returned dict."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    certified = _make_certified(
        "planner",
        "Prompt for {domain_name}. {examples} | {vars_description}",
        "3.0.0",
    )
    mock_selection = MagicMock()
    mock_selection.tool = "simulation"
    mock_selection.reasoning = "test"
    mock_selection.params = []
    mock_selection.language = "es"

    with (
        patch("prompts.registry.get_certified_prompt", return_value=certified),
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner.invoke_with_fallback", return_value=mock_selection),
        patch("agents.planner.get_spec") as mock_spec,
    ):
        spec = MagicMock()
        spec.domain_name = "D"
        spec.decision_variables = [
            MagicMock(
                name="x",
                description="x",
                unit="u",
                bounds_min=1,
                bounds_max=10,
                default=5,
            )
        ]
        spec.autonomy_policy.get_level.return_value = MagicMock(value="auto")
        mock_spec.return_value = spec

        from agents.planner import planner_node

        result = planner_node({"query": "simulate at x=5", "history": []})

    assert result["planner_prompt_version"] == "3.0.0"
