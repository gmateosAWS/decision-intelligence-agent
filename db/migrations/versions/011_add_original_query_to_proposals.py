"""Add original_query column to state_proposals (hotfix 5.13).

Revision ID: 011
Revises: 010
Create Date: 2026-05-18

Stores the query that triggered the proactive gate so that the commit
endpoint can re-invoke the agent with bypass_gate=True after the user
approves the proposal (Bug 2 of hotfix/5.13-proactive-gate-and-resume).
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "state_proposals",
        sa.Column(
            "original_query",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("state_proposals", "original_query")
