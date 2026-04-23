"""Add specs, spec_versions tables and spec traceability columns on agent_runs

Revision ID: 002
Revises: 001
Create Date: 2026-04-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "specs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("domain_name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("yaml_content", sa.Text(), nullable=False),
        sa.Column("parsed_content", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.UniqueConstraint("domain_name", "version", name="uq_specs_domain_version"),
    )

    op.create_table(
        "spec_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("spec_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("yaml_content", sa.Text(), nullable=False),
        sa.Column("parsed_content", postgresql.JSONB(), nullable=False),
        sa.Column("change_summary", sa.Text()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.Text()),
        sa.ForeignKeyConstraint(["spec_id"], ["specs.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_spec_versions_spec", "spec_versions", ["spec_id"])

    # Add spec traceability columns to agent_runs
    op.add_column("agent_runs", sa.Column("spec_id", postgresql.UUID(as_uuid=True)))
    op.add_column("agent_runs", sa.Column("spec_version", sa.Text()))
    op.create_foreign_key(
        "fk_agent_runs_spec_id",
        "agent_runs",
        "specs",
        ["spec_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_runs_spec_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "spec_version")
    op.drop_column("agent_runs", "spec_id")
    op.drop_index("idx_spec_versions_spec", table_name="spec_versions")
    op.drop_table("spec_versions")
    op.drop_table("specs")
