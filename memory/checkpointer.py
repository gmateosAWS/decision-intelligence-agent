"""
memory/checkpointer.py  – FIXED (register_turn simplificado)
-------------------------------------------------------------
Cambio: eliminada la bifurcación if/else idéntica en register_turn().
Ambas ramas hacían exactamente el mismo UPSERT SQL, por lo que la
condición `is_new` no tenía efecto real. El parámetro se mantiene en
la firma para compatibilidad hacia atrás (app.py lo pasa).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from langgraph.checkpoint.sqlite import SqliteSaver

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DB_PATH = Path("data") / "checkpoints.db"
_checkpointer: Optional[SqliteSaver] = None


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_checkpointer() -> SqliteSaver:
    """
    Return (and lazily create) the singleton SqliteSaver.

    The checkpointer is opened once per process and reused for every
    graph compilation.  The agent_sessions table is created alongside
    the standard LangGraph checkpoint tables.
    """
    global _checkpointer  # noqa: PLW0603
    if _checkpointer is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _checkpointer = SqliteSaver(conn)
        _ensure_sessions_table()
    return _checkpointer


def register_turn(
    session_id: str,
    query: str,
    *,
    is_new: bool = False,  # noqa: ARG001  kept for API compatibility
) -> None:
    """
    Upsert a row in agent_sessions for *session_id*.

    On first insert the title is set to the first 60 chars of *query*.
    Subsequent calls (same session_id) increment turn_count and update
    last_active; the title is preserved from the first insert.

    Note: `is_new` is accepted but has no effect – the UPSERT handles
    both cases correctly via ON CONFLICT.
    """
    now = _utcnow()
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.execute(
            """
            INSERT INTO agent_sessions
                (session_id, title, created_at, last_active, turn_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(session_id) DO UPDATE SET
                last_active = excluded.last_active,
                turn_count  = turn_count + 1
            """,
            (session_id, query[:60], now, now),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _ensure_sessions_table() -> None:
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id  TEXT PRIMARY KEY,
                title       TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL,
                last_active TEXT    NOT NULL,
                turn_count  INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
