"""Add cost-tracking columns to agent_runs (items 8.7.a + 8.7.b)

Revision ID: 006
Revises: 005
Create Date: 2026-05-12

Six new columns capture per-run LLM usage and budget enforcement:
  - total_input_tokens   INTEGER  cumulative input tokens across all LLM calls
  - total_output_tokens  INTEGER  cumulative output tokens
  - total_cost_usd       NUMERIC(10,6)  computed from model_pricing.yaml
  - llm_calls_count      INTEGER  number of invoke_with_fallback calls
  - budget_exceeded      BOOLEAN  True if a ceiling was hit mid-run
  - budget_exceeded_reason TEXT   human-readable ceiling description
"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "total_input_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "total_output_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "total_cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "llm_calls_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "budget_exceeded",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "budget_exceeded_reason",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "budget_exceeded_reason")
    op.drop_column("agent_runs", "budget_exceeded")
    op.drop_column("agent_runs", "llm_calls_count")
    op.drop_column("agent_runs", "total_cost_usd")
    op.drop_column("agent_runs", "total_output_tokens")
    op.drop_column("agent_runs", "total_input_tokens")
