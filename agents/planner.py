"""
agents/planner.py  ← CORREGIDO
────────────────────────────────
Cambios:
  1. System prompt completo: el LLM ahora sabe qué es el sistema
      y qué hace cada tool.
  2. Structured output con Pydantic (ToolSelection): elimina
      el string matching frágil.
     El LLM devuelve un objeto tipado con 'tool' (Literal) y 'reasoning' (str).
  3. El estado se actualiza devolviendo un dict parcial
      (patrón correcto en LangGraph),
     no mutando el dict de estado directamente.
  4. Manejo de error con fallback a 'knowledge' si structured output falla.
"""

from __future__ import annotations

from typing import Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agents.state import AgentState

load_dotenv()

# ── LLM ───────────────────────────────────────────────────────────────────────
_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Structured output schema ──────────────────────────────────────────────────
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
   Use when the user asks: what is the best price? what price maximises profit?
   what decision should I make? find the optimal...
    The tool searches the full price range and returns the price
    that maximises expected profit.

2. SIMULATION
   Use when the user asks: what happens if price is X? simulate scenario...
   what would profit be at price Y? what is the expected outcome?
    The tool evaluates a specific scenario under uncertainty
    using Monte Carlo simulation.

3. KNOWLEDGE
   Use when the user asks: how does the model work? what is demand elasticity?
   explain the methodology, what does Monte Carlo mean? what are the assumptions?
    The tool retrieves relevant explanations from the system
    knowledge base.

Select the single most appropriate tool for the user's query.
Always provide a brief reasoning for your choice."""


def planner_node(state: AgentState) -> dict:
    """
    Selecciona la herramienta más adecuada para la query del usuario.

    Usa structured output para garantizar que la respuesta sea siempre
    un objeto tipado con tool ∈ {optimization, simulation, knowledge}.

    Returns:
        Actualización parcial del estado: {action, reasoning}
    """
    query = state["query"]

    try:
        selection: ToolSelection = _llm_structured.invoke(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ]
        )
        return {
            "action": selection.tool,
            "reasoning": selection.reasoning,
        }

    except Exception as e:
        # Fallback seguro: knowledge tool si structured output falla
        return {
            "action": "knowledge",
            "reasoning": (
                f"Structured output failed ({e}). " "Defaulting to knowledge tool."
            ),
        }
