"""
tests/memory/test_checkpointer_postgres.py
------------------------------------------
Integration test for PostgresSaver checkpointer.

Requires a running PostgreSQL instance (docker compose up -d)
and DATABASE_URL set in the environment.

Mark: @pytest.mark.integration
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_saves_and_loads_state():
    """
    Build a minimal LangGraph graph with the Postgres checkpointer,
    invoke it with a thread_id, and verify the state is persisted.
    """
    from typing import TypedDict

    from langgraph.graph import END, StateGraph

    from memory.checkpointer import get_checkpointer

    class _State(TypedDict):
        value: int

    def increment(state: _State) -> _State:
        return {"value": state["value"] + 1}

    builder = StateGraph(_State)
    builder.add_node("increment", increment)
    builder.set_entry_point("increment")
    builder.add_edge("increment", END)

    checkpointer = get_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)

    thread_id = "test-pg-checkpointer"
    config = {"configurable": {"thread_id": thread_id}}

    graph.invoke({"value": 0}, config=config)
    state = graph.get_state(config)

    assert state.values["value"] == 1, "State not persisted by checkpointer"
