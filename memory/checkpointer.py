"""
memory/checkpointer.py
----------------------
LangGraph checkpointer with dual-backend support.

- DATABASE_URL set  → PostgresSaver (langgraph-checkpoint-postgres)
- DATABASE_URL unset → SqliteSaver  (original behaviour, for dev without Docker)
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path("data") / "checkpoints.db"

# Union type covers both backends for type-checkers
_checkpointer: Optional[object] = None


def get_checkpointer():
    """
    Return (and lazily create) the singleton checkpointer.

    Uses PostgresSaver when DATABASE_URL is configured; falls back to
    SqliteSaver so developers can run without Docker.
    """
    global _checkpointer  # noqa: PLW0603
    if _checkpointer is None:
        _checkpointer = _build_checkpointer()
    return _checkpointer


def register_turn(
    session_id: str,
    query: str,
    *,
    is_new: bool = False,  # noqa: ARG001 kept for API compatibility
) -> None:
    """
    Upsert a row in agent_sessions for *session_id*.

    Delegates to the Postgres or SQLite backend depending on DATABASE_URL.
    """
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        _register_turn_postgres(session_id, query)
    else:
        _register_turn_sqlite(session_id, query)


# ---------------------------------------------------------------------------
# Backend builders
# ---------------------------------------------------------------------------


def _build_checkpointer():
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        return _build_postgres_checkpointer(database_url)
    return _build_sqlite_checkpointer()


def _build_postgres_checkpointer(database_url: str):
    try:
        import psycopg  # noqa: F401 — ensure driver is installed
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore[import]

        conn = psycopg.connect(database_url, autocommit=True)
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()
        logger.info("Using PostgresSaver checkpointer")
        return checkpointer
    except Exception as exc:
        logger.warning(
            "PostgresSaver unavailable (%s) — falling back to SQLite checkpointer", exc
        )
        return _build_sqlite_checkpointer()


def _build_sqlite_checkpointer():
    from langgraph.checkpoint.sqlite import SqliteSaver

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    _ensure_sessions_table_sqlite()
    logger.info("Using SqliteSaver checkpointer (DATABASE_URL not set)")
    return checkpointer


# ---------------------------------------------------------------------------
# Postgres session helpers
# ---------------------------------------------------------------------------


def _register_turn_postgres(session_id: str, query: str) -> None:
    try:
        import uuid

        from db.engine import get_session
        from db.models import AgentSession

        with get_session() as session:
            try:
                sid = uuid.UUID(session_id)
            except ValueError:
                # session_id might be a plain string from legacy callers
                sid = uuid.uuid5(uuid.NAMESPACE_DNS, session_id)

            existing = session.get(AgentSession, sid)
            now = datetime.now(timezone.utc)
            if existing is None:
                session.add(
                    AgentSession(
                        session_id=sid,
                        title=query[:60],
                        created_at=now,
                        last_active=now,
                        turn_count=1,
                    )
                )
            else:
                existing.last_active = now
                existing.turn_count = (existing.turn_count or 0) + 1
    except Exception as exc:  # noqa: BLE001
        logger.error("register_turn (postgres) failed: %s", exc)


# ---------------------------------------------------------------------------
# SQLite session helpers (original behaviour)
# ---------------------------------------------------------------------------


def _register_turn_sqlite(session_id: str, query: str) -> None:
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


def _ensure_sessions_table_sqlite() -> None:
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
