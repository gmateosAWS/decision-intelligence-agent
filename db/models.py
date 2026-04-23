"""
db/models.py
------------
SQLAlchemy ORM models for the three Postgres tables:

  - AgentSession   — one row per conversation thread
  - AgentRun       — one row per agent invocation (replaces JSONL)
  - KnowledgeDocument — one row per knowledge chunk (replaces FAISS)

The ``Base`` declarative base is also imported by Alembic's env.py so
that ``Base.metadata.create_all()`` / autogenerate work correctly.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func

TIMESTAMPTZ = TIMESTAMP(timezone=True)

try:
    from pgvector.sqlalchemy import Vector

    _VECTOR_AVAILABLE = True
except ImportError:
    _VECTOR_AVAILABLE = False
    Vector = None  # type: ignore[assignment,misc]


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class AgentSession(Base):
    """One row per conversation session (thread_id)."""

    __tablename__ = "agent_sessions"

    session_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title = Column(Text, nullable=False, default="")
    created_at = Column(TIMESTAMPTZ, nullable=False, server_default=func.now())
    last_active = Column(TIMESTAMPTZ, nullable=False, server_default=func.now())
    turn_count = Column(Integer, nullable=False, default=0)

    runs = relationship(
        "AgentRun", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AgentSession id={self.session_id} title={self.title!r}>"


class AgentRun(Base):
    """One row per agent invocation — mirrors the RunRecord dataclass."""

    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id = Column(Text, nullable=False)
    timestamp = Column(
        TIMESTAMPTZ, nullable=False, server_default=func.now(), index=True
    )
    query = Column(Text, nullable=False)

    # Planner
    action = Column(Text)
    reasoning = Column(Text)
    planner_latency_ms = Column(Float)
    planner_model = Column(Text)

    # Tool
    tool_latency_ms = Column(Float)
    confidence_score = Column(Float)

    # Synthesizer
    synthesizer_latency_ms = Column(Float)
    answer_length = Column(Integer)
    synthesizer_model = Column(Text)

    # Judge
    judge_latency_ms = Column(Float)
    judge_score = Column(Float)
    judge_passed = Column(Boolean)
    judge_revised = Column(Boolean)
    judge_feedback = Column(Text)
    judge_model = Column(Text)

    # Overall
    total_latency_ms = Column(Float)
    success = Column(Boolean, nullable=False, default=True)
    error = Column(Text)

    # Extra fields
    fallback_triggered = Column(Boolean, default=False)
    raw_result = Column(JSONB)

    # Spec traceability
    spec_id = Column(
        UUID(as_uuid=True),
        ForeignKey("specs.id", ondelete="SET NULL"),
        nullable=True,
    )
    spec_version = Column(Text)

    session = relationship("AgentSession", back_populates="runs")

    def __repr__(self) -> str:
        return f"<AgentRun run_id={self.run_id} action={self.action}>"


class Spec(Base):
    """One row per (domain_name, version) — the spec stored as DB object."""

    __tablename__ = "specs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_name = Column(Text, nullable=False)
    version = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="draft")  # draft / active / archived
    yaml_content = Column(Text, nullable=False)
    parsed_content = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMPTZ, nullable=False, server_default=func.now())
    created_by = Column(Text)
    description = Column(Text)

    versions = relationship(
        "SpecVersion", back_populates="spec", cascade="all, delete-orphan"
    )

    __table_args__ = (
        __import__("sqlalchemy").UniqueConstraint("domain_name", "version"),
    )

    def __repr__(self) -> str:
        return f"<Spec {self.domain_name}@{self.version} status={self.status}>"


class SpecVersion(Base):
    """Audit log — one row per historical version of a spec."""

    __tablename__ = "spec_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    spec_id = Column(
        UUID(as_uuid=True),
        ForeignKey("specs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Text, nullable=False)
    yaml_content = Column(Text, nullable=False)
    parsed_content = Column(JSONB, nullable=False)
    change_summary = Column(Text)
    created_at = Column(TIMESTAMPTZ, nullable=False, server_default=func.now())
    created_by = Column(Text)

    spec = relationship("Spec", back_populates="versions")

    def __repr__(self) -> str:
        return f"<SpecVersion spec_id={self.spec_id} version={self.version}>"


def _build_knowledge_document_class() -> type:
    """Build KnowledgeDocument with or without the pgvector column."""

    attrs: dict = {
        "__tablename__": "knowledge_documents",
        "id": Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        "content": Column(Text, nullable=False),
        "category": Column(Text),
        "created_at": Column(TIMESTAMPTZ, nullable=False, server_default=func.now()),
        "__repr__": lambda self: (
            f"<KnowledgeDocument id={self.id} category={self.category}>"
        ),
    }

    if _VECTOR_AVAILABLE and Vector is not None:
        attrs["embedding"] = Column(Vector(1536))
    else:
        # Graceful degradation: store embeddings as JSONB when pgvector not installed
        attrs["embedding"] = Column(JSONB)

    return type("KnowledgeDocument", (Base,), attrs)


KnowledgeDocument = _build_knowledge_document_class()
