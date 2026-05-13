"""Add analytical_state to agent_sessions + session_state_transitions table (item 5.10).

Revision ID: 007
Revises: 006
Create Date: 2026-05-13

Adds ActiveAnalyticalState persistence to the memory layer:
  - agent_sessions.analytical_state         JSONB   — serialised state snapshot
  - agent_sessions.analytical_state_version INTEGER — monotonic version counter
  - session_state_transitions               TABLE   — immutable mutation audit log
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── agent_sessions: state snapshot columns ──────────────────────────────
    op.add_column(
        "agent_sessions",
        sa.Column(
            "analytical_state",
            JSONB,
            nullable=True,
        ),
    )
    op.add_column(
        "agent_sessions",
        sa.Column(
            "analytical_state_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # ── session_state_transitions: append-only audit log ───────────────────
    op.create_table(
        "session_state_transitions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_id", sa.Integer(), nullable=False),
        sa.Column("version_before", sa.Integer(), nullable=False),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("op", sa.Text(), nullable=False),
        sa.Column("before", JSONB, nullable=True),
        sa.Column("after", JSONB, nullable=True),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_session_state_transitions_session",
        "session_state_transitions",
        ["session_id", "turn_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_session_state_transitions_session",
        table_name="session_state_transitions",
    )
    op.drop_table("session_state_transitions")
    op.drop_column("agent_sessions", "analytical_state_version")
    op.drop_column("agent_sessions", "analytical_state")
