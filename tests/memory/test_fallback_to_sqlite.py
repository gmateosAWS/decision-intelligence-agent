"""
tests/memory/test_fallback_to_sqlite.py
----------------------------------------
Unit test verifying that get_checkpointer() falls back to SqliteSaver
when DATABASE_URL is not configured.  No Docker required.
"""

from __future__ import annotations


def test_sqlite_fallback_when_no_database_url(monkeypatch, tmp_path):
    """
    When DATABASE_URL is absent, get_checkpointer() returns a SqliteSaver
    and does not raise.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    import memory.checkpointer as cp_mod

    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Point the DB path to a temp location so the test is isolated
    monkeypatch.setattr(cp_mod, "_DB_PATH", tmp_path / "test_checkpoints.db")
    # Reset the singleton
    cp_mod._checkpointer = None

    checkpointer = cp_mod.get_checkpointer()

    assert isinstance(checkpointer, SqliteSaver)

    # Clean up singleton
    cp_mod._checkpointer = None
