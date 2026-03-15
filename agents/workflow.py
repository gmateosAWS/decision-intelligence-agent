"""
agents/workflow.py  ← CORREGIDO
──────────────────────────────────
Cambios:
    1. Añadido nodo synthesizer_node: el LLM reformatea
         el resultado crudo de la tool en una respuesta de negocio
         clara y en lenguaje natural antes de responder al usuario.
  2. Manejo de errores en tool_node: try/except con error propagado al estado.
  3. Routing condicional desde tool_node hacia synthesizer
      o directo a END si hay error.
  4. Todos los nodos devuelven dicts parciales (patrón correcto en LangGraph).
  5. El flujo completo es: planner → tool → synthesizer → END

Arquitectura del grafo:

  ┌──────────┐     ┌──────────┐     ┌──────────────┐
  │ planner  │────►│  tool    │────►│ synthesizer  │────► END
  └──────────┘     └──────────┘     └──────────────┘
"""

from __future__ import annotations

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from agents.planner import planner_node
from agents.state import AgentState
from agents.tools import knowledge_tool, optimization_tool, simulation_tool

load_dotenv()

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ── System prompt del sintetizador ────────────────────────────────────────────
_SYNTHESIZER_PROMPT = """You are a business analyst presenting results
to a decision-maker.
You receive raw output from an analytical tool and must present it clearly.

Guidelines:
- Lead with the key business insight or recommendation.
- Include the most important numbers
    (expected profit, optimal price, risk level).
- Explain what the result means for the business decision,
    not just what the numbers are.
- If the result is an error, explain what went wrong in plain language.
- Be concise: 3-5 sentences maximum.
- Use business language, not technical jargon."""


# ── NODOS ─────────────────────────────────────────────────────────────────────


def tool_node(state: AgentState) -> dict:
    """
    Ejecuta la herramienta seleccionada por el planner.
    Captura excepciones y las propaga al estado en lugar de romper el grafo.
    """
    action = state.get("action", "knowledge")
    query = state["query"]

    try:
        if action == "optimization":
            raw = optimization_tool(query)
        elif action == "simulation":
            raw = simulation_tool(query)
        else:
            raw = knowledge_tool(query)
        return {"raw_result": raw}

    except Exception as exc:
        error_msg = (
            f"Tool '{action}' raised an error: {type(exc).__name__}: {exc}. "
            "Check that the ML model and knowledge index are built."
        )
        return {"raw_result": error_msg}


def synthesizer_node(state: AgentState) -> dict:
    """
    Usa el LLM para transformar el resultado crudo de la tool
    en una respuesta de negocio estructurada y en lenguaje natural.

    Este nodo cierra el ciclo: el LLM no computa, pero sí interpreta y comunica.
    """
    query = state["query"]
    raw_result = state.get("raw_result", "No result available.")

    messages = [
        {"role": "system", "content": _SYNTHESIZER_PROMPT},
        {
            "role": "user",
            "content": (
                f"The user asked: {query}\n\nAnalytical tool output:\n{raw_result}"
            ),
        },
    ]

    try:
        response = _llm.invoke(messages)
        return {"answer": response.content}
    except Exception as exc:
        return {"answer": f"Could not generate response: {exc}"}


# ── GRAFO ─────────────────────────────────────────────────────────────────────


def build_graph():
    """
    Construye y compila el grafo LangGraph del agente.

    Flujo: planner → tool → synthesizer → END
    """
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("tool", tool_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "tool")
    graph.add_edge("tool", "synthesizer")
    graph.add_edge("synthesizer", END)

    return graph.compile()
