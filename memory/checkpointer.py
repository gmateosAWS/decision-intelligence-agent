"""
memory/checkpointer.py
----------------------
Singleton SqliteSaver for LangGraph persistent checkpointing.

The checkpointer stores the full LangGraph state after every node so
that a conversation thread can be resumed from any point.

SQLite file location: data/checkpoints.db  (auto-created on first use)

Additional agent_sessions table tracks:
    session_id  TEXT PRIMARY KEY
    title       TEXT     – first user query (trimmed to 60 chars)
    created_at  TEXT     – ISO timestamp
    last_active TEXT     – ISO timestamp updated on every turn
    turn_count  INTEGER  – incremented on every turn
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
        _checkpointer = SqliteSaver.from_conn_string(str(_DB_PATH))
        _ensure_sessions_table()
    return _checkpointer


def register_turn(
    session_id: str,
    query: str,
    *,
    is_new: bool = False,
) -> None:
    """
    Upsert a row in agent_sessions for *session_id*.

    If *is_new* is True the row is inserted with title = first 60 chars
    of *query*.  Otherwise the existing row's last_active and turn_count
    are updated.
    """
    now = _utcnow()
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        if is_new:
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
        else:
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
