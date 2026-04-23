"""
tests/db/test_models.py
-----------------------
Integration tests for ORM CRUD operations.

Requires a running PostgreSQL instance (docker compose up -d).
Mark: @pytest.mark.integration
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture(scope="module")
def db_session():
    """Yield a transactional session, roll back after the module."""
    from db.engine import get_session_factory

    factory = get_session_factory()
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.mark.integration
def test_session_crud(db_session):
    """Insert, retrieve, and delete an AgentSession row."""
    from db.models import AgentSession

    sid = uuid.uuid4()
    row = AgentSession(session_id=sid, title="test session", turn_count=0)
    db_session.add(row)
    db_session.flush()

    fetched = db_session.get(AgentSession, sid)
    assert fetched is not None
    assert fetched.title == "test session"

    db_session.delete(fetched)
    db_session.flush()
    assert db_session.get(AgentSession, sid) is None


@pytest.mark.integration
def test_run_crud(db_session):
    """Insert and retrieve an AgentRun row (no session FK)."""
    from db.models import AgentRun

    run_id = uuid.uuid4().hex[:12]
    row = AgentRun(run_id=run_id, query="what is the optimal price?", success=True)
    db_session.add(row)
    db_session.flush()

    fetched = db_session.query(AgentRun).filter_by(run_id=run_id).first()
    assert fetched is not None
    assert fetched.query == "what is the optimal price?"

    db_session.delete(fetched)
    db_session.flush()


@pytest.mark.integration
def test_knowledge_insert_and_search(db_session):
    """Insert a KnowledgeDocument and verify cosine search returns it."""
    from sqlalchemy import text

    from db.models import KnowledgeDocument

    # Use a dummy 1536-dim vector (all zeros except first element)
    embedding = [0.0] * 1536
    embedding[0] = 1.0

    doc = KnowledgeDocument(
        content="test knowledge chunk",
        category="test",
        embedding=embedding,
    )
    db_session.add(doc)
    db_session.flush()

    # Cosine search for the same vector — should return this doc at top
    vec_literal = "[" + ",".join(str(v) for v in embedding) + "]"
    rows = db_session.execute(
        text(
            "SELECT content FROM knowledge_documents "
            "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT 1"
        ),
        {"vec": vec_literal},
    ).fetchall()

    assert rows, "Expected at least one result from pgvector search"
    assert rows[0][0] == "test knowledge chunk"

    db_session.delete(doc)
    db_session.flush()
