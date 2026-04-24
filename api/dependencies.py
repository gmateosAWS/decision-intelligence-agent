"""api/dependencies.py — FastAPI dependency providers."""

from __future__ import annotations

from functools import lru_cache
from typing import Generator

from sqlalchemy.orm import Session


@lru_cache(maxsize=1)
def get_graph():
    """Return the compiled LangGraph agent (process-level singleton)."""
    from agents.workflow import build_graph
    from memory.checkpointer import get_checkpointer

    return build_graph(checkpointer=get_checkpointer())


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session; requires DATABASE_URL."""
    from db.engine import get_session

    with get_session() as session:
        yield session
