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
- Prompt Registry integration (item 10.1): the system prompt template is
  read from the certified "planner" registry entry; falls back to the
  inline PLANNER_SYSTEM_TEMPLATE when the registry is unavailable.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from prompts.registry import PLANNER_SYSTEM_TEMPLATE, get_prompt_template
from spec.spec_loader import get_spec

from .llm_factory import LLMUnavailableError, get_chat_model, invoke_with_fallback
from .state import AgentState

if TYPE_CHECKING:
    from evaluation.budget import BudgetTracker

load_dotenv()

_PLANNER_PROVIDER = os.getenv("PLANNER_PROVIDER", "openai")
_PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gpt-4o-mini")
_FALLBACK_PROVIDER = os.getenv("FALLBACK_PROVIDER", "")
_FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")

_llm = None
_llm_structured = None
_fallback_llm_structured = None


class DecisionParam(BaseModel):
    """Un par variable-valor extraído de la query del usuario."""

    variable: str  # nombre exacto de la variable del spec
    value: float  # valor numérico mencionado


class ToolSelection(BaseModel):
    """Selección de herramienta con razonamiento y parámetros extraídos."""

    tool: Literal["optimization", "simulation", "knowledge"]
    reasoning: str
    params: List[DecisionParam] = []  # vacío si no se mencionan valores
    language: str = Field(
        default="en",
        description=(
            "ISO 639-1 code of the user's query language "
            "(e.g. 'es', 'en', 'fr', 'de')"
        ),
    )


_HISTORY_WINDOW = int(os.getenv("HISTORY_WINDOW", "3"))


def _init_planner_llms() -> None:
    global _llm, _llm_structured, _fallback_llm_structured
    if _llm is not None:
        return
    _llm = get_chat_model(_PLANNER_PROVIDER, _PLANNER_MODEL, temperature=0)
    # include_raw=True: returns {"raw": AIMessage, "parsed": ToolSelection, ...}
    # so _record_usage() can extract token counts from the raw AIMessage.
    _llm_structured = _llm.with_structured_output(ToolSelection, include_raw=True)
    if _FALLBACK_PROVIDER and _FALLBACK_MODEL:
        _fallback_llm = get_chat_model(
            _FALLBACK_PROVIDER, _FALLBACK_MODEL, temperature=0
        )
        _fallback_llm_structured = _fallback_llm.with_structured_output(
            ToolSelection, include_raw=True
        )


def _build_few_shot_examples(spec: Any) -> str:
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


def _build_system_prompt(
    session_id: Optional[str] = None,
) -> tuple[str, Optional[str], Optional[str]]:
    """
    Build the rendered planner system prompt from the active spec.

    Reads the template from the Prompt Registry (certified "planner" prompt),
    routing deterministically to a variant when A/B variants are active.
    Falls back to PLANNER_SYSTEM_TEMPLATE when the registry is unavailable.
    Returns (rendered_prompt_str, version_or_None, variant_label_or_None).

    Template content and variant routing are cached in the registry layer;
    the spec render is fast because get_spec() caches internally.
    """
    spec = get_spec()
    vars_desc = "\n".join(
        f"   - {v.name}: {v.description} ({v.unit}, "
        f"rango {v.bounds_min}–{v.bounds_max}, defecto {v.default})"
        for v in spec.decision_variables
    )
    examples = _build_few_shot_examples(spec)
    template, version, variant_label = get_prompt_template(
        "planner", PLANNER_SYSTEM_TEMPLATE, session_id=session_id
    )
    rendered = template.format(
        domain_name=spec.domain_name,
        vars_description=vars_desc,
        examples=examples,
    )
    return rendered, version, variant_label


def planner_node(
    state: AgentState,
    tracker: Optional["BudgetTracker"] = None,
    active_state: Optional[Any] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Selects the best tool for the current query and extracts any
    decision-variable values mentioned in the query into `params`.

    active_state: frozen ActiveAnalyticalState snapshot from the MemoryService
    (typed as Any to avoid importing memory internals here — the boundary lint
    enforces that planner.py stays on the facade side).

    session_id: UUID string used for deterministic A/B variant routing (item 10.2).

    Returns: {action, reasoning, params, planner_prompt_version,
    planner_variant_label, ...}
    """
    _init_planner_llms()
    query = state["query"]
    history: List[Dict[str, str]] = state.get("history") or []

    system_prompt, prompt_version, variant_label = _build_system_prompt(session_id)
    messages = [{"role": "system", "content": system_prompt}]

    # Inject typed analytical state context when available (item 5.11).
    # This is complementary to history — the typed state takes priority for
    # structured facts; the history transcript provides raw conversational context.
    if active_state is not None:
        context_lines = []
        intent = getattr(active_state, "intent", None)
        if intent is not None:
            context_lines.append(f"- Previous turn intent: {intent.value}")
        sim_run = getattr(active_state, "active_simulation_run", None)
        if sim_run is not None:
            context_lines.append(
                f"- Active simulation run from a previous turn (run_id: {sim_run})."
                " Follow-ups about simulation results reference this run."
            )
        opt_run = getattr(active_state, "active_optimization_run", None)
        if opt_run is not None:
            context_lines.append(
                f"- Active optimization run from a previous turn (run_id: {opt_run})."
                " Follow-ups about optimization results reference this run."
            )
        metrics = getattr(active_state, "metrics", [])
        if metrics:
            metric_names = ", ".join(getattr(m, "name", str(m)) for m in metrics)
            context_lines.append(f"- Active metrics in scope: {metric_names}")
        if context_lines:
            messages.append(
                {
                    "role": "system",
                    "content": "TYPED ANALYTICAL STATE (from previous turns):\n"
                    + "\n".join(context_lines),
                }
            )

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
        output = invoke_with_fallback(
            _llm_structured,
            messages,
            fallback=_fallback_llm_structured,
            tracker=tracker,
            model=_PLANNER_MODEL,
        )
        selection: ToolSelection = output["parsed"]
        params_dict = {p.variable: p.value for p in selection.params}

        # Consult autonomy policy for the selected tool
        from spec.autonomy import AutonomyLevel

        policy_level = get_spec().autonomy_policy.get_level(selection.tool)

        result: dict[str, Any] = {
            "action": selection.tool,
            "reasoning": selection.reasoning,
            "params": params_dict,
            "language": selection.language,
            "requires_confirmation": False,
            "requires_approval": False,
            "confirmation_message": None,
            "planner_prompt_version": prompt_version,
            "planner_variant_label": variant_label,
        }

        if policy_level == AutonomyLevel.HUMAN_CONFIRMS:
            result["requires_confirmation"] = True
            result["confirmation_message"] = (
                f"The agent wants to run **{selection.tool}** "
                f"with parameters {params_dict or 'spec defaults'}. Confirm?"
            )
        elif policy_level == AutonomyLevel.HUMAN_APPROVES:
            result["requires_approval"] = True
            result["confirmation_message"] = (
                f"The agent proposes to run **{selection.tool}** "
                f"with parameters {params_dict or 'spec defaults'}. "
                "This action requires explicit approval before execution."
            )

        return result
    except (LLMUnavailableError, Exception) as exc:
        return {
            "action": "knowledge",
            "reasoning": (
                f"Planner unavailable ({exc}). Defaulting to knowledge tool."
            ),
            "params": {},
            "language": "en",
            "requires_confirmation": False,
            "requires_approval": False,
            "confirmation_message": None,
            "planner_prompt_version": prompt_version,
            "planner_variant_label": variant_label,
        }
