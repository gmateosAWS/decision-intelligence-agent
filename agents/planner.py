"""
agents/planner.py
-----------------
LLM planner node for the Decision Intelligence Agent.

Responsibilities
----------------
- Tool selection via structured output (Pydantic schema ``ToolSelection``),
  eliminating fragile string parsing.
- System prompt built dynamically from the organizational spec: decision
  variable names, ranges and defaults are injected at runtime, so the
  planner stays domain-agnostic without manual prompt updates.
- Few-shot routing examples generated from the spec's first decision
  variable, covering optimization, simulation and knowledge queries.
- Chain-of-Thought reasoning enforced in the ``reasoning`` field: the LLM
  must articulate what the user is asking, whether concrete variable values
  are mentioned, whether the intent is exploratory or conceptual, and which
  tool fits best — before committing to a choice.
- Generic parameter extraction: any decision-variable values mentioned in
  the query are captured in ``params: Dict[str, float]`` using the exact
  variable names from the spec. Tools fall back to spec defaults for any
  missing key.
- Conversational context: the last ``HISTORY_WINDOW`` turns (env var,
  default 3) from ``state["history"]`` are prepended to the prompt so the
  LLM can resolve cross-turn references without re-asking the user.
"""

from __future__ import annotations

import os
from typing import Dict, List, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel

from agents.llm_factory import LLMUnavailableError, get_chat_model, invoke_with_fallback
from agents.state import AgentState
from spec.spec_loader import get_spec

load_dotenv()

_PLANNER_PROVIDER = os.getenv("PLANNER_PROVIDER", "openai")
_PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gpt-4o-mini")
_FALLBACK_PROVIDER = os.getenv("FALLBACK_PROVIDER", "")
_FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")

_llm = get_chat_model(_PLANNER_PROVIDER, _PLANNER_MODEL, temperature=0)


class DecisionParam(BaseModel):
    """Un par variable-valor extraído de la query del usuario."""

    variable: str  # nombre exacto de la variable del spec
    value: float  # valor numérico mencionado


class ToolSelection(BaseModel):
    """Selección de herramienta con razonamiento y parámetros extraídos."""

    tool: Literal["optimization", "simulation", "knowledge"]
    reasoning: str
    params: List[DecisionParam] = []  # vacío si no se mencionan valores


_llm_structured = _llm.with_structured_output(ToolSelection)

_fallback_llm_structured: Optional[object] = None
if _FALLBACK_PROVIDER and _FALLBACK_MODEL:
    _fallback_llm = get_chat_model(_FALLBACK_PROVIDER, _FALLBACK_MODEL, temperature=0)
    _fallback_llm_structured = _fallback_llm.with_structured_output(ToolSelection)

_HISTORY_WINDOW = int(os.getenv("HISTORY_WINDOW", "3"))


def _build_few_shot_examples(spec) -> str:
    """
    Builds 3 dynamic routing examples from the first decision variable in the spec.

    One example per tool: optimization (find the optimal value), simulation
    (evaluate a specific value), and knowledge (explain the model).
    """
    v0 = spec.decision_variables[0]
    sim_value = v0.default
    return (
        f"EXAMPLES\n"
        f"--------\n"
        f'User: "What is the optimal {v0.name}?"\n'
        f"→ tool: optimization | reasoning: The user is asking for the {v0.name} that"
        f" maximises profit, which requires searching the full range"
        f" {v0.bounds_min}–{v0.bounds_max}. | params: {{}}\n\n"
        f'User: "What would happen if {v0.name} is {sim_value}?"\n'
        f"→ tool: simulation | reasoning: The user specifies a concrete {v0.name}"
        f" value and asks for the expected outcome under uncertainty."
        f' | params: {{"{v0.name}": {sim_value}}}\n\n'
        f'User: "How does the demand model work?"\n'
        f"→ tool: knowledge | reasoning: The user is asking for an explanation of the"
        f" methodology, not a specific decision or scenario. | params: {{}}"
    )


def _build_system_prompt() -> str:
    """Construye el system prompt dinámicamente desde el spec."""
    spec = get_spec()
    vars_desc = "\n".join(
        f"   - {v.name}: {v.description} ({v.unit}, "
        f"rango {v.bounds_min}–{v.bounds_max}, defecto {v.default})"
        for v in spec.decision_variables
    )
    examples = _build_few_shot_examples(spec)
    return (
        f"You are the planner of a Decision Intelligence system\n"
        f"for a {spec.domain_name} business.\n"
        f"The system models how decision variables affect demand,\n"
        f"revenue, cost and profit.\n\n"
        f"You have three tools available:\n\n"
        f"1. OPTIMIZATION\n"
        f"   Use when the user asks: what is the best price? what price maximises\n"
        f"   profit? what decision should I make? find the optimal...\n"
        f"   The tool searches the full decision variable range and returns the\n"
        f"   combination that maximises expected profit.\n\n"
        f"2. SIMULATION\n"
        f"   Use when the user asks: what happens if X is Y? simulate scenario...\n"
        f"   what would profit be at value Z? what is the expected outcome?\n"
        f"   The tool evaluates a specific scenario under uncertainty\n"
        f"   using Monte Carlo simulation.\n\n"
        f"3. KNOWLEDGE\n"
        f"   Use when the user asks: how does the model work? what is demand\n"
        f"   elasticity? explain the methodology, what does Monte Carlo mean?\n"
        f"   The tool retrieves relevant explanations from the knowledge base.\n\n"
        f"{examples}\n\n"
        f"If the user mentions specific values for decision variables, extract\n"
        f"them into the `params` dict using the exact variable name as key.\n"
        f"Decision variables available:\n"
        f"{vars_desc}\n"
        f"Leave params empty if no specific values are mentioned.\n\n"
        f"Before selecting a tool, reason step by step in the `reasoning` field:\n"
        f"  1. What is the user asking for?\n"
        f"  2. Does the query mention concrete values for any decision variable?\n"
        f"  3. Is this an exploration/optimization question or a request to"
        f" understand\n"
        f"     how the system works?\n"
        f"  4. Which tool fits best and why?\n\n"
        f"Select the single most appropriate tool for the user's query."
    )


_SYSTEM_PROMPT = _build_system_prompt()


def planner_node(state: AgentState) -> Dict:
    """
    Selects the best tool for the current query and extracts any
    decision-variable values mentioned in the query into `params`.

    Returns: {action, reasoning, params}
    """
    query = state["query"]
    history: List[Dict[str, str]] = state.get("history") or []

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

    recent = history[-_HISTORY_WINDOW:]
    for turn in recent:
        user_q = turn.get("query", "")
        assistant_a = turn.get("answer", "")
        if user_q:
            messages.append({"role": "user", "content": user_q})
        if assistant_a:
            messages.append({"role": "assistant", "content": assistant_a})

    messages.append({"role": "user", "content": query})

    try:
        selection: ToolSelection = invoke_with_fallback(
            _llm_structured,
            messages,
            fallback=_fallback_llm_structured,
        )
        return {
            "action": selection.tool,
            "reasoning": selection.reasoning,
            "params": {p.variable: p.value for p in selection.params},
        }
    except (LLMUnavailableError, Exception) as exc:
        return {
            "action": "knowledge",
            "reasoning": (
                f"Planner unavailable ({exc}). Defaulting to knowledge tool."
            ),
            "params": {},
        }
