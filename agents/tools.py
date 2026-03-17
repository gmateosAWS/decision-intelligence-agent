"""
agents/tools.py  – FIXED (type contract aligned with workflow.py)
------------------------------------------------------------------
Cambios respecto a Mejora 1:
  • Las tres funciones aceptan ahora `state: dict` (AgentState) en lugar
    de `query: str`, en consonancia con cómo las llama workflow.py:
        raw_result = tool_fn(state)
  • Todas devuelven `dict` en lugar de `str`, en consonancia con lo que
    espera synthesizer_node:
        raw_text = "\\n".join(f"  {k}: {v}" for k, v in raw.items())
  • knowledge_tool extrae `state["query"]` correctamente antes de llamar
    a retrieve_knowledge().
  • optimization_tool y simulation_tool ya devolvían un dict internamente;
    se eliminó el str() innecesario.
"""

from __future__ import annotations

from typing import Any, Dict

from knowledge.retriever import retrieve_knowledge
from optimization.optimizer import optimize_price
from simulation.scenario_runner import run_scenario
from spec.spec_loader import get_spec
from system.system_model import SystemModel

# SystemModel loads the ML model once at import time (singleton pattern)
system_model = SystemModel()


def optimization_tool(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run a grid-search optimisation over the price range and return
    the scenario (price + Monte Carlo stats) with the highest
    expected profit.

    Returns a dict with keys: price, marketing, expected_profit,
    profit_std, profit_p10, profit_p90, expected_demand,
    demand_std, downside_risk_pct, n_runs.
    """
    result: Dict[str, Any] = optimize_price(system_model)
    return result


def simulation_tool(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run a Monte Carlo simulation using decision variable values from the
    planner's extracted params, falling back to spec defaults for any
    variable not mentioned in the query.

    Domain coupling is intentionally confined to this function:
    `run_scenario` still uses positional parameters (price, marketing),
    so the mapping from generic `params` → runner signature lives here
    as a single adapter point.
    """
    spec = get_spec()
    extracted: Dict[str, float] = state.get("params") or {}

    # Build value map: extracted by planner > spec default
    var_values: Dict[str, float] = {
        var.name: float(extracted.get(var.name, var.default))
        for var in spec.decision_variables
    }
    # Add fixed_variables from the optimization config (e.g. marketing_spend)
    for name, val in spec.fixed_variables.items():
        if name not in var_values:
            var_values[name] = float(extracted.get(name, val))

    # Adapter: map generic var_values → run_scenario positional params
    price = var_values.get(
        "price",
        spec.get_decision_var("price").default,
    )
    marketing = var_values.get(
        "marketing_spend",
        spec.fixed_variables.get("marketing_spend", 10_000.0),
    )

    return run_scenario(system_model, price, marketing)


def knowledge_tool(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve relevant knowledge-base documents for the user's query
    using FAISS similarity search.

    Extracts the query string from the AgentState dict so the tool
    receives the correct type regardless of whether it is called
    directly or via workflow.py.

    Returns {"answer": <retrieved text>, "documents": <same text>}.
    The "documents" key allows the observer to detect a knowledge result
    and assign a confidence score of 0.9.
    """
    query: str = state.get("query", "") if isinstance(state, dict) else str(state)
    text = retrieve_knowledge(query)
    return {"answer": text, "documents": text}
