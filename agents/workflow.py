from langgraph.graph import END, StateGraph

from agents.planner import planner_node
from agents.state import AgentState
from agents.tools import knowledge_tool, optimization_tool, simulation_tool


def tool_node(state: AgentState):
    action = state["action"]

    if "optimization" in action:
        result = optimization_tool(state["query"])

    elif "simulation" in action:
        result = simulation_tool(state["query"])

    else:
        result = knowledge_tool(state["query"])

    state["answer"] = result

    return state


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("tool", tool_node)

    graph.set_entry_point("planner")

    graph.add_edge("planner", "tool")
    graph.add_edge("tool", END)

    return graph.compile()
