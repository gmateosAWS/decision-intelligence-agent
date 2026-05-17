"""Add *_variant_label columns to agent_runs for A/B observability (item 10.2).

Revision ID: 009
Revises: 008
Create Date: 2026-05-17

Adds three nullable Text columns to agent_runs so that every run records
which prompt variant was served for each LLM stage. NULL means the stage
ran before 10.2 was deployed (or in SQLite/FAISS fallback mode).
"""

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs", sa.Column("planner_variant_label", sa.Text(), nullable=True)
    )
    op.add_column(
        "agent_runs", sa.Column("synthesizer_variant_label", sa.Text(), nullable=True)
    )
    op.add_column(
        "agent_runs", sa.Column("judge_variant_label", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "judge_variant_label")
    op.drop_column("agent_runs", "synthesizer_variant_label")
    op.drop_column("agent_runs", "planner_variant_label")
