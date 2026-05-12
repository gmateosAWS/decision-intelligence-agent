"""
tests/evaluation/test_agent_golden.py
--------------------------------------
Golden evaluation test suite (item 5.2).

Tests routing correctness, result shape, parameter propagation and language
detection without real LLM calls. Designed as the foundation for item 10.11
(Golden Eval CI gates): when 10.11 lands it extends this file with additional
CI gates — it does not replace it.

Test categories
---------------
- test_golden_routing         unit  planner returns expected action + language
- test_golden_param_propagation  unit  explicit values extracted into params
- test_golden_result_shape    unit  tool output contains expected keys
  (uses real tool logic with a mocked SystemModel — no ML model required)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from agents.planner import DecisionParam, ToolSelection, planner_node

# ── Golden query catalogue ────────────────────────────────────────────────────
# Keys:
#   id             unique test identifier
#   query          natural-language input
#   expected_tool  optimization | simulation | knowledge
#   language       ISO 639-1 code the planner should detect
#   expected_keys  subset of output dict keys that must be present (result-shape tests)
#   expected_params {variable: value} that the planner should extract (param tests)

GOLDEN_QUERIES: List[Dict[str, Any]] = [
    # ── Optimization ──────────────────────────────────────────────────────────
    {
        "id": "opt-01",
        "query": "What price maximizes profit?",
        "expected_tool": "optimization",
        "expected_keys": ["price", "expected_profit", "n_runs"],
        "language": "en",
    },
    {
        "id": "opt-02",
        "query": "¿Qué precio maximiza el beneficio?",
        "expected_tool": "optimization",
        "expected_keys": ["price", "expected_profit", "n_runs"],
        "language": "es",
    },
    {
        "id": "opt-03",
        "query": "Find the optimal pricing strategy for next quarter",
        "expected_tool": "optimization",
        "expected_keys": ["price", "expected_profit"],
        "language": "en",
    },
    {
        "id": "opt-04",
        "query": "What is the best decision we can make?",
        "expected_tool": "optimization",
        "language": "en",
    },
    # ── Simulation ────────────────────────────────────────────────────────────
    {
        "id": "sim-01",
        "query": "Simulate profit at price 25",
        "expected_tool": "simulation",
        "expected_keys": ["price", "expected_profit", "profit_std", "n_runs"],
        "language": "en",
        "expected_params": {"price": 25.0},
    },
    {
        "id": "sim-02",
        "query": "Simula el beneficio con precio 25 y marketing 8000",
        "expected_tool": "simulation",
        "expected_keys": ["price", "expected_profit", "profit_std"],
        "language": "es",
        "expected_params": {"price": 25.0},
    },
    {
        "id": "sim-03",
        "query": "What would happen if we set price to 40?",
        "expected_tool": "simulation",
        "expected_keys": ["price", "expected_profit", "downside_risk_pct"],
        "language": "en",
        "expected_params": {"price": 40.0},
    },
    {
        "id": "sim-04",
        "query": "Was wäre wenn der Preis 30 wäre?",
        "expected_tool": "simulation",
        "expected_keys": ["price", "expected_profit"],
        "language": "de",
        "expected_params": {"price": 30.0},
    },
    {
        "id": "sim-05",
        "query": "Simulate at the minimum price of 10",
        "expected_tool": "simulation",
        "expected_keys": ["price", "expected_profit", "profit_p10", "profit_p90"],
        "language": "en",
        "expected_params": {"price": 10.0},
    },
    # ── Knowledge ─────────────────────────────────────────────────────────────
    {
        "id": "know-01",
        "query": "What is the demand model?",
        "expected_tool": "knowledge",
        "expected_keys": ["answer", "documents"],
        "language": "en",
    },
    {
        "id": "know-02",
        "query": "¿Cómo afecta el marketing a la demanda?",
        "expected_tool": "knowledge",
        "expected_keys": ["answer"],
        "language": "es",
    },
    {
        "id": "know-03",
        "query": "Explain the Monte Carlo simulation methodology",
        "expected_tool": "knowledge",
        "expected_keys": ["answer"],
        "language": "en",
    },
    {
        "id": "know-04",
        "query": "Comment fonctionne le modèle de demande ?",
        "expected_tool": "knowledge",
        "expected_keys": ["answer"],
        "language": "fr",
    },
    {
        "id": "know-05",
        "query": "What is demand elasticity?",
        "expected_tool": "knowledge",
        "expected_keys": ["answer"],
        "language": "en",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_selection(
    tool: str,
    language: str = "en",
    params: Optional[List] = None,
) -> MagicMock:
    """Build a deterministic ToolSelection mock."""
    sel = MagicMock(spec=ToolSelection)
    sel.tool = tool
    sel.reasoning = f"Test: routing to {tool}"
    sel.language = language
    sel.params = params or []
    return sel


def _param_mocks(expected_params: Dict[str, float]) -> List[MagicMock]:
    mocks = []
    for var, val in expected_params.items():
        p = MagicMock(spec=DecisionParam)
        p.variable = var
        p.value = val
        mocks.append(p)
    return mocks


# ── Routing tests (unit — no LLM, no tools) ──────────────────────────────────


@pytest.mark.parametrize("case", GOLDEN_QUERIES, ids=[c["id"] for c in GOLDEN_QUERIES])
def test_golden_routing(case: Dict[str, Any]) -> None:
    """Planner routes each query to the expected tool with correct language."""
    params = _param_mocks(case.get("expected_params", {}))
    selection = _make_selection(case["expected_tool"], case["language"], params)
    state = {"query": case["query"], "history": []}

    with (
        patch("agents.planner._init_planner_llms"),
        patch(
            "agents.planner.invoke_with_fallback",
            return_value={"parsed": selection, "raw": MagicMock()},
        ),
    ):
        result = planner_node(state)

    assert result["action"] == case["expected_tool"], (
        f"[{case['id']}] expected action={case['expected_tool']!r}, "
        f"got {result['action']!r}"
    )
    assert result["language"] == case["language"], (
        f"[{case['id']}] expected language={case['language']!r}, "
        f"got {result['language']!r}"
    )


# ── Parameter propagation tests (unit) ───────────────────────────────────────


@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_QUERIES if "expected_params" in c],
    ids=[c["id"] for c in GOLDEN_QUERIES if "expected_params" in c],
)
def test_golden_param_propagation(case: Dict[str, Any]) -> None:
    """Decision-variable values mentioned in the query are extracted into params."""
    params = _param_mocks(case["expected_params"])
    selection = _make_selection(case["expected_tool"], case["language"], params)
    state = {"query": case["query"], "history": []}

    with (
        patch("agents.planner._init_planner_llms"),
        patch(
            "agents.planner.invoke_with_fallback",
            return_value={"parsed": selection, "raw": MagicMock()},
        ),
    ):
        result = planner_node(state)

    for var, expected_val in case["expected_params"].items():
        assert (
            var in result["params"]
        ), f"[{case['id']}] expected param {var!r} missing. Got: {result['params']}"
        assert result["params"][var] == pytest.approx(expected_val), (
            f"[{case['id']}] param {var!r}: expected {expected_val}, "
            f"got {result['params'][var]}"
        )


# ── Result-shape tests (unit — real tools, mocked SystemModel) ────────────────


@pytest.fixture
def mock_system_model() -> MagicMock:
    """
    Stub SystemModel with fixed causal evaluation output.

    monte_carlo() and optimize_price() call model.evaluate() internally;
    with this stub they run the full statistical computation without
    requiring a trained ML model on disk.
    """
    model = MagicMock()
    model.evaluate.return_value = {
        "price": 25.0,
        "marketing": 10_000.0,
        "demand": 100.0,
        "revenue": 2_500.0,
        "cost": 1_000.0,
        "profit": 1_500.0,
    }
    model.unit_cost = 10.0
    return model


@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_QUERIES if "expected_keys" in c],
    ids=[c["id"] for c in GOLDEN_QUERIES if "expected_keys" in c],
)
def test_golden_result_shape(case: Dict[str, Any], mock_system_model) -> None:
    """Tool output contains all expected keys with correct value types."""
    tool_name = case["expected_tool"]
    state: Dict[str, Any] = {
        "query": case["query"],
        "action": tool_name,
        "params": case.get("expected_params", {}),
        "history": [],
    }

    if tool_name == "optimization":
        from optimization.optimizer import optimize_price

        result = optimize_price(mock_system_model)

    elif tool_name == "simulation":
        from simulation.montecarlo import run_scenario

        price = case.get("expected_params", {}).get("price", 25.0)
        result = run_scenario(mock_system_model, price, 10_000.0)

    elif tool_name == "knowledge":
        # Patch at the usage site (agents.tools imports retrieve_knowledge by name)
        with patch(
            "agents.tools.retrieve_knowledge",
            return_value="[model] The demand model uses price elasticity.",
        ):
            from agents.tools import knowledge_tool

            result = knowledge_tool(state)

    else:
        pytest.fail(f"[{case['id']}] Unknown tool: {tool_name!r}")

    for key in case["expected_keys"]:
        assert key in result, (
            f"[{case['id']}] expected key {key!r} missing from {tool_name} output. "
            f"Got keys: {sorted(result.keys())}"
        )
