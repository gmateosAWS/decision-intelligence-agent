"""
tests/agents/test_planner.py
-----------------------------
Unit tests for agents/planner.py — all offline (no real LLM calls).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agents.planner import ToolSelection, planner_node

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_selection(
    tool: str = "optimization",
    reasoning: str = "test reasoning",
    params=None,
    language: str = "en",
) -> MagicMock:
    sel = MagicMock(spec=ToolSelection)
    sel.tool = tool
    sel.reasoning = reasoning
    sel.params = params or []
    sel.language = language
    return sel


def _state(query: str = "What is the optimal price?") -> dict:
    return {"query": query, "history": []}


# ---------------------------------------------------------------------------
# language field propagation
# ---------------------------------------------------------------------------


def test_planner_returns_language_field():
    """planner_node result must include a 'language' key."""
    sel = _make_selection(language="en")
    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner.invoke_with_fallback", return_value=sel),
    ):
        result = planner_node(_state())
    assert "language" in result
    assert result["language"] == "en"


def test_planner_detects_spanish():
    """When the model returns 'es', planner_node propagates language='es'."""
    sel = _make_selection(tool="optimization", language="es")
    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner.invoke_with_fallback", return_value=sel),
    ):
        result = planner_node(_state("¿Cuál es el precio óptimo?"))
    assert result["language"] == "es"


def test_planner_detects_french():
    """language field is passed through for any ISO code the model returns."""
    sel = _make_selection(tool="knowledge", language="fr")
    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner.invoke_with_fallback", return_value=sel),
    ):
        result = planner_node(_state("Comment fonctionne le modèle ?"))
    assert result["language"] == "fr"


def test_planner_fallback_defaults_language_to_en():
    """On LLM failure the error-fallback dict must contain language='en'."""
    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner.invoke_with_fallback", side_effect=Exception("down")),
    ):
        result = planner_node(_state())
    assert result.get("language") == "en"


# ---------------------------------------------------------------------------
# Sanity: existing fields still present alongside language
# ---------------------------------------------------------------------------


def test_planner_returns_action_reasoning_params_and_language():
    """All four keys — action, reasoning, params, language — are returned."""
    sel = _make_selection(
        tool="simulation", reasoning="Concrete value given.", language="de"
    )
    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner.invoke_with_fallback", return_value=sel),
    ):
        result = planner_node(_state("Was wäre wenn der Preis 50 wäre?"))
    assert result["action"] == "simulation"
    assert "Concrete value" in result["reasoning"]
    assert result["params"] == {}
    assert result["language"] == "de"
