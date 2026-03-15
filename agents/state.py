"""
agents/state.py  ← REESCRITO (archivo anterior tenía contenido incorrecto)
──────────────────────────────────────────────────────────────────────────
Define el estado tipado del agente LangGraph.

AgentState es el contrato entre todos los nodos del grafo:
  - planner_node  escribe: action, reasoning
  - tool_node     escribe: raw_result
  - synthesizer_node escribe: answer
  - Todos leen:   query

El uso de TypedDict con campos Optional garantiza que los nodos puedan
devolver actualizaciones parciales del estado sin romper el contrato.
"""

from typing import Optional

from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Estado completo del agente a lo largo de la ejecución del grafo."""

    # ── Input ─────────────────────────────────────────────────────────────────
    query: str  # Pregunta original del usuario

    # ── Planner output ────────────────────────────────────────────────────────
    action: Optional[str]  # Herramienta seleccionada: optimization|simulation|knowledge
    reasoning: Optional[str]  # Razonamiento del planner (para trazabilidad)

    # ── Tool output ───────────────────────────────────────────────────────────
    raw_result: Optional[str]  # Resultado crudo de la herramienta ejecutada

    # ── Synthesizer output ────────────────────────────────────────────────────
    answer: Optional[str]  # Respuesta final en lenguaje natural
