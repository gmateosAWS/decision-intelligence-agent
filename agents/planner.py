"""
agents/planner.py  – Mejora 3
-------------------------------
Cambios respecto a Mejora 2:
  • El prompt del sistema es el mismo.
  • planner_node ahora recibe el historial de conversación
    (state["history"]) y añade hasta 3 turnos anteriores como
    mensajes de usuario/asistente previos al mensaje actual.
    Esto permite que el LLM resuelva referencias como
    "¿y si el precio fuese 28?" cuando la pregunta anterior
    era sobre optimización de precios.
"""

from __future__ import annotations

from typing import Dict, List, Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agents.state import AgentState

load_dotenv()

# ── LLM ─────────────────────────────────────────────────────────────────────
_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Structured output schema ─────────────────────────────────────────────────
class ToolSelection(BaseModel):
    """Selección de herramienta con razonamiento explícito."""

    tool: Literal["optimization", "simulation", "knowledge"]
    reasoning: str


_llm_structured = _llm.with_structured_output(ToolSelection)

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are the planner of a Decision Intelligence system
for a retail business.
The system models how price and marketing investment affect demand,
revenue, cost and profit.

You have three tools available:

1. OPTIMIZATION
   Use when the user asks: what is the best price? what price maximises
   profit? what decision should I make? find the optimal...
   The tool searches the full price range and returns the price
   that maximises expected profit.

2. SIMULATION
   Use when the user asks: what happens if price is X? simulate scenario...
   what would profit be at price Y? what is the expected outcome?
   The tool evaluates a specific scenario under uncertainty
   using Monte Carlo simulation.

3. KNOWLEDGE
   Use when the user asks: how does the model work? what is demand
   elasticity? explain the methodology, what does Monte Carlo mean?
   what are the assumptions?
   The tool retrieves relevant explanations from the system
   knowledge base.

Select the single most appropriate tool for the user's query.
Always provide a brief reasoning for your choice."""

# Number of previous turns to include in context
_HISTORY_WINDOW = 3


def planner_node(state: AgentState) -> Dict:
    """
    Selects the best tool for the current query, optionally
    injecting the last _HISTORY_WINDOW conversation turns for context.

    Returns: {action, reasoning}
    """
    query = state["query"]
    history: List[Dict[str, str]] = state.get("history") or []

    # Build message list: system + recent history + current query
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

    # Inject the most recent turns (oldest first)
    recent = history[-_HISTORY_WINDOW:]
    for turn in recent:
        user_q = turn.get("query", "")
        assistant_a = turn.get("answer", "")
        if user_q:
            messages.append({"role": "user", "content": user_q})
        if assistant_a:
            messages.append({"role": "assistant", "content": assistant_a})

    # Current user message
    messages.append({"role": "user", "content": query})

    try:
        selection: ToolSelection = _llm_structured.invoke(messages)
        return {
            "action": selection.tool,
            "reasoning": selection.reasoning,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "action": "knowledge",
            "reasoning": (
                f"Structured output failed ({exc}). " "Defaulting to knowledge tool."
            ),
        }
