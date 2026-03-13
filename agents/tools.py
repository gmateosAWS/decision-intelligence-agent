"""
agents/tools.py  (MODIFIED — Mejora 1: spec-driven)
─────────────────────────────────────────────────────
Simulation tool now uses spec defaults instead of hardcoded values.
The agent operates within the parameters declared in the organizational spec.
"""

from knowledge.retriever import retrieve_knowledge
from optimization.optimizer import optimize_price
from simulation.scenario_runner import run_scenario
from spec.spec_loader import get_spec
from system.system_model import SystemModel

system_model = SystemModel()


def optimization_tool(query: str) -> str:
    result = optimize_price(system_model)
    return str(result)


def simulation_tool(query: str) -> str:
    """
    Run a simulation using the default decision values from the spec.
    Previously: hardcoded price=30, marketing=10.
    Now: uses spec.decision_variables[price].default and
         spec.fixed_variables[marketing_spend].
    """
    spec = get_spec()
    price_var = spec.get_decision_var("price")
    default_price = price_var.default
    default_marketing = spec.fixed_variables.get(
        "marketing_spend",
        spec.get_decision_var("marketing_spend").default,
    )
    result = run_scenario(system_model, default_price, default_marketing)
    return str(result)


def knowledge_tool(query: str) -> str:
    return retrieve_knowledge(query)
