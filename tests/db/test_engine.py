"""
tests/db/test_engine.py
-----------------------
Integration tests for db/engine.py.

Requires a running PostgreSQL instance (docker compose up -d).
Mark: @pytest.mark.integration
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_engine_connects():
    """get_engine() returns a connected engine when DATABASE_URL is set."""
    from db.engine import check_connection

    assert check_connection(), "Could not connect to PostgreSQL — is Docker running?"


@pytest.mark.integration
def test_get_session_context_manager():
    """get_session() commits on success and closes the session."""
    from sqlalchemy import text

    from db.engine import get_session

    with get_session() as session:
        result = session.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_engine_raises_without_database_url(monkeypatch):
    """get_engine() raises RuntimeError when DATABASE_URL is not set."""
    import db.engine as engine_mod

    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Reset singleton so it re-reads the env var
    engine_mod._engine = None

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        engine_mod.get_engine()

    # Restore state so other tests are unaffected
    engine_mod._engine = None
