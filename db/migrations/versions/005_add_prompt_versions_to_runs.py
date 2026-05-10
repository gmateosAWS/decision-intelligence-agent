"""Add prompt_version columns to agent_runs — Prompt Registry traceability (item 10.1)

Revision ID: 005
Revises: 004
Create Date: 2026-05-10

Each run now records which prompt version was used by the planner,
synthesizer, and judge. Foundation for the LineageRecord (item 10.10):
every recommendation is tied to the exact prompt artifacts that produced it.
NULL means the run predates the registry or the registry was unavailable.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs", sa.Column("planner_prompt_version", sa.Text(), nullable=True)
    )
    op.add_column(
        "agent_runs", sa.Column("synthesizer_prompt_version", sa.Text(), nullable=True)
    )
    op.add_column(
        "agent_runs", sa.Column("judge_prompt_version", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "judge_prompt_version")
    op.drop_column("agent_runs", "synthesizer_prompt_version")
    op.drop_column("agent_runs", "planner_prompt_version")
