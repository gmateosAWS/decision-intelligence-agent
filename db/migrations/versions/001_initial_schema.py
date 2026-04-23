"""Initial schema: agent_sessions, agent_runs, knowledge_documents

Revision ID: 001
Revises:
Create Date: 2026-04-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable required extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "agent_sessions",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_active",
            postgresql.TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column(
            "timestamp",
            postgresql.TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("query", sa.Text(), nullable=False),
        # Planner
        sa.Column("action", sa.Text()),
        sa.Column("reasoning", sa.Text()),
        sa.Column("planner_latency_ms", sa.Float()),
        sa.Column("planner_model", sa.Text()),
        # Tool
        sa.Column("tool_latency_ms", sa.Float()),
        sa.Column("confidence_score", sa.Float()),
        # Synthesizer
        sa.Column("synthesizer_latency_ms", sa.Float()),
        sa.Column("answer_length", sa.Integer()),
        sa.Column("synthesizer_model", sa.Text()),
        # Judge
        sa.Column("judge_latency_ms", sa.Float()),
        sa.Column("judge_score", sa.Float()),
        sa.Column("judge_passed", sa.Boolean()),
        sa.Column("judge_revised", sa.Boolean()),
        sa.Column("judge_feedback", sa.Text()),
        sa.Column("judge_model", sa.Text()),
        # Overall
        sa.Column("total_latency_ms", sa.Float()),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("error", sa.Text()),
        # Extra
        sa.Column("fallback_triggered", sa.Boolean(), server_default="false"),
        sa.Column("raw_result", postgresql.JSONB()),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.session_id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index("idx_runs_session", "agent_runs", ["session_id"])
    op.create_index("idx_runs_timestamp", "agent_runs", ["timestamp"])

    op.create_table(
        "knowledge_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.Text()),
        sa.Column(
            "embedding",
            sa.Text(),  # placeholder — raw DDL below handles the real vector type
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Replace the placeholder column with the real vector type
    op.execute(
        "ALTER TABLE knowledge_documents "
        "ALTER COLUMN embedding TYPE vector(1536) USING NULL"
    )
    op.execute(
        "CREATE INDEX idx_knowledge_embedding ON knowledge_documents "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 5)"
    )


def downgrade() -> None:
    op.drop_table("knowledge_documents")
    op.drop_index("idx_runs_timestamp", table_name="agent_runs")
    op.drop_index("idx_runs_session", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_table("agent_sessions")
