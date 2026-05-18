"""Add state_proposals and state_commits tables (item 5.13).

Revision ID: 010
Revises: 009
Create Date: 2026-05-18

Adds audit-quality persistence for user-driven state corrections:
  - state_proposals — one row per proactive/reactive proposal (5.13)
  - state_commits   — one row per committed decision, FK to proposal
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── state_proposals ────────────────────────────────────────────────────────
    op.create_table(
        "state_proposals",
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
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("mutations", JSONB, nullable=False),
        sa.Column(
            "triggered_signals",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_state_proposals_session_turn",
        "state_proposals",
        ["session_id", "turn_id"],
    )

    # ── state_commits ──────────────────────────────────────────────────────────
    op.create_table(
        "state_commits",
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
        sa.Column(
            "proposal_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("state_proposals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version_before", sa.Integer(), nullable=False),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column("applied_mutations", JSONB, nullable=False),
        sa.Column(
            "skipped_slots",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "committed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_state_commits_session",
        "state_commits",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_state_commits_session", table_name="state_commits")
    op.drop_table("state_commits")
    op.drop_index("idx_state_proposals_session_turn", table_name="state_proposals")
    op.drop_table("state_proposals")
