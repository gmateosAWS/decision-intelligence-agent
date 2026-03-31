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

  – Mejora 5 (params genérico)
-------------------------------------------------
Cambios vs Mejora 4:
  • ToolSelection usa `params: Dict[str, float]` en lugar de campos
    fijos `price` y `marketing`. El schema es agnóstico al dominio.
  • El system prompt se genera dinámicamente desde el spec, listando
    las variables de decisión por nombre. Cambiar el YAML actualiza
    automáticamente lo que el planner sabe extraer.
  • planner_node devuelve {"action", "reasoning", "params"} —
    sin nombres de campo de dominio en el contrato de estado.
"""

from __future__ import annotations

import os
from typing import Dict, List, Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agents.state import AgentState
from spec.spec_loader import get_spec

load_dotenv()

_PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gpt-4o-mini")

_llm = ChatOpenAI(model=_PLANNER_MODEL, temperature=0)


class DecisionParam(BaseModel):
    """Un par variable-valor extraído de la query del usuario."""

    variable: str  # nombre exacto de la variable del spec
    value: float  # valor numérico mencionado


class ToolSelection(BaseModel):
    """Selección de herramienta con razonamiento y parámetros extraídos."""

    tool: Literal["optimization", "simulation", "knowledge"]
    reasoning: str
    params: List[DecisionParam] = []  # vacío si no se mencionan valores


# Volver al modo por defecto (json_schema estricto, compatible con List[objeto])
_llm_structured = _llm.with_structured_output(ToolSelection)


# Numero de turnos anteriores a incluir del historial (ajustable según necesidades)
_HISTORY_WINDOW = 3


def _build_system_prompt() -> str:
    """Construye el system prompt dinámicamente desde el spec."""
    spec = get_spec()
    vars_desc = "\n".join(
        f"   - {v.name}: {v.description} ({v.unit}, "
        f"rango {v.bounds_min}–{v.bounds_max}, defecto {v.default})"
        for v in spec.decision_variables
    )
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
        f"   using Monte Carlo simulation.\n"
        f"   If the user mentions specific values for decision variables, extract\n"
        f"   them into the `params` dict using the exact variable name as key.\n"
        f"   Decision variables available:\n"
        f"{vars_desc}\n"
        f"   Example: 'simulate at price 30' → params={{\"price\": 30.0}}\n"
        f"   Leave params empty ({{}}) if no specific values are mentioned.\n\n"
        f"3. KNOWLEDGE\n"
        f"   Use when the user asks: how does the model work? what is demand\n"
        f"   elasticity? explain the methodology, what does Monte Carlo mean?\n"
        f"   The tool retrieves relevant explanations from the knowledge base.\n\n"
        f"Select the single most appropriate tool for the user's query.\n"
        f"Always provide a brief reasoning for your choice."
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
        selection: ToolSelection = _llm_structured.invoke(messages)
        return {
            "action": selection.tool,
            "reasoning": selection.reasoning,
            "params": {p.variable: p.value for p in selection.params},
        }
    except Exception as exc:
        return {
            "action": "knowledge",
            "reasoning": (
                f"Structured output failed ({exc}). " "Defaulting to knowledge tool."
            ),
            "params": {},
        }
