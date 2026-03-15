"""
memory/session_manager.py
--------------------------
CRUD and listing of conversation sessions stored in the SQLite DB.

API
---
  SessionManager.list_sessions()       -> list[dict]
  SessionManager.get_session(sid)      -> dict | None
  SessionManager.delete_session(sid)   -> bool
  SessionManager.print_sessions()      -> None   (CLI pretty-print)
  SessionManager.session_info(sid)     -> None   (CLI detail view)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

_DB_PATH = Path("data") / "checkpoints.db"


class SessionManager:
    """
    Read-only and management interface for agent_sessions rows.

    All methods open a fresh connection so the class is safe to use
    from the REPL without holding a long-lived connection.
    """

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    def list_sessions() -> List[Dict]:
        """
        Return all sessions ordered by last_active DESC.
        Returns an empty list if the DB or table does not exist yet.
        """
        if not _DB_PATH.exists():
            return []
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT session_id, title, created_at,
                       last_active, turn_count
                FROM   agent_sessions
                ORDER  BY last_active DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    @staticmethod
    def get_session(session_id: str) -> Optional[Dict]:
        """Return a single session row or None."""
        if not _DB_PATH.exists():
            return None
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT session_id, title, created_at,
                       last_active, turn_count
                FROM   agent_sessions
                WHERE  session_id = ?
                """,
                (session_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def delete_session(session_id: str) -> bool:
        """
        Delete a session row from agent_sessions.
        Returns True if a row was deleted, False if not found.
        Note: LangGraph checkpoint data for the thread is not removed.
        """
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
            sid = s["session_id"][:36]
            ts = s["last_active"][:19].replace("T", " ")
            title = s["title"][:35]
            print(f"  {idx:<4} {sid:<38}" f"{s['turn_count']:<7} {ts:<22} {title}")
        print()

    @classmethod
    def session_info(cls, session_id: str) -> None:
        """Print detailed info about a single session."""
        s = cls.get_session(session_id)
        if s is None:
            print(f"  Session '{session_id}' not found.")
            return
        print(f"\n  Session ID   : {s['session_id']}")
        print(f"  Title        : {s['title']}")
        print(f"  Created      : {s['created_at']}")
        print(f"  Last active  : {s['last_active']}")
        print(f"  Turn count   : {s['turn_count']}\n")
