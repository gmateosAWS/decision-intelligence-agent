"""
memory/session_manager.py
--------------------------
CRUD and listing of conversation sessions.

Backend selection:
  DATABASE_URL set  → SQLAlchemy queries against agent_sessions (Postgres)
  DATABASE_URL unset → SQLite queries (original behaviour, for dev without Docker)

Public API (unchanged):
  SessionManager.list_sessions()       -> list[dict]
  SessionManager.get_session(sid)      -> dict | None
  SessionManager.delete_session(sid)   -> bool
  SessionManager.print_sessions()      -> None
  SessionManager.session_info(sid)     -> None
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path("data") / "checkpoints.db"


def _use_postgres() -> bool:
    return bool(os.getenv("DATABASE_URL", ""))


class SessionManager:
    """Read and management interface for agent_sessions rows."""

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    def list_sessions() -> List[Dict]:
        """Return all sessions ordered by last_active DESC."""
        if _use_postgres():
            return _pg_list_sessions()
        return _sq_list_sessions()

    @staticmethod
    def get_session(session_id: str) -> Optional[Dict]:
        """Return a single session row or None."""
        if _use_postgres():
            return _pg_get_session(session_id)
        return _sq_get_session(session_id)

    @staticmethod
    def delete_session(session_id: str) -> bool:
        """
        Delete a session row.
        Returns True if a row was deleted, False if not found.
        Note: LangGraph checkpoint data for the thread is not removed.
        """
        if _use_postgres():
            return _pg_delete_session(session_id)
        return _sq_delete_session(session_id)

    # ------------------------------------------------------------------
    # CLI helpers
    # ------------------------------------------------------------------

    @classmethod
    def print_sessions(cls) -> None:
        """Print a numbered table of all sessions to stdout."""
        sessions = cls.list_sessions()
        if not sessions:
            print("  (no sessions yet)")
            return
        print(
            f"\n  {'#':<4} {'Session ID':<38}" f"{'Turns':<7} {'Last active':<22} Title"
        )
        print("  " + "-" * 90)
        for idx, s in enumerate(sessions, 1):
            sid = str(s["session_id"])[:36]
            ts = str(s.get("last_active", ""))[:19].replace("T", " ")
            title = str(s.get("title", ""))[:35]
            print(f"  {idx:<4} {sid:<38}{s['turn_count']:<7} {ts:<22} {title}")
        print()

    @classmethod
    def session_info(cls, session_id: str) -> None:
        """Print detailed info about a single session."""
        s = cls.get_session(session_id)
        if s is None:
            print(f"  Session '{session_id}' not found.")
            return
        print(f"\n  Session ID   : {s['session_id']}")
        print(f"  Title        : {s.get('title', '')}")
        print(f"  Created      : {s.get('created_at', '')}")
        print(f"  Last active  : {s.get('last_active', '')}")
        print(f"  Turn count   : {s.get('turn_count', 0)}\n")


# ---------------------------------------------------------------------------
# Postgres backend
# ---------------------------------------------------------------------------


def _row_to_dict(session_obj) -> Dict:
    return {
        "session_id": str(session_obj.session_id),
        "title": session_obj.title,
        "created_at": (
            session_obj.created_at.isoformat() if session_obj.created_at else None
        ),
        "last_active": (
            session_obj.last_active.isoformat() if session_obj.last_active else None
        ),
        "turn_count": session_obj.turn_count,
    }


def _parse_uuid(session_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(session_id)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, session_id)


def _pg_list_sessions() -> List[Dict]:
    try:
        from sqlalchemy import desc

        from db.engine import get_session
        from db.models import AgentSession

        with get_session() as session:
            rows = (
                session.query(AgentSession)
                .order_by(desc(AgentSession.last_active))
                .all()
            )
            return [_row_to_dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.error("list_sessions (postgres) failed: %s", exc)
        return []


def _pg_get_session(session_id: str) -> Optional[Dict]:
    try:
        from db.engine import get_session
        from db.models import AgentSession

        with get_session() as session:
            row = session.get(AgentSession, _parse_uuid(session_id))
            return _row_to_dict(row) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.error("get_session (postgres) failed: %s", exc)
        return None


def _pg_delete_session(session_id: str) -> bool:
    try:
        from db.engine import get_session
        from db.models import AgentSession

        with get_session() as session:
            row = session.get(AgentSession, _parse_uuid(session_id))
            if row is None:
                return False
            session.delete(row)
            return True
    except Exception as exc:  # noqa: BLE001
        logger.error("delete_session (postgres) failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# SQLite backend (original behaviour)
# ---------------------------------------------------------------------------


def _sq_list_sessions() -> List[Dict]:
    if not _DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT session_id, title, created_at, last_active, turn_count
            FROM   agent_sessions
            ORDER  BY last_active DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _sq_get_session(session_id: str) -> Optional[Dict]:
    if not _DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT session_id, title, created_at, last_active, turn_count
            FROM   agent_sessions
            WHERE  session_id = ?
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _sq_delete_session(session_id: str) -> bool:
    if not _DB_PATH.exists():
        return False
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        cur = conn.execute(
            "DELETE FROM agent_sessions WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
