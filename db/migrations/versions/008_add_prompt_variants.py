"""Add prompt_variants table for A/B testing (item 10.2).

Revision ID: 008
Revises: 007
Create Date: 2026-05-17

Adds the prompt_variants table that tracks A/B routing entries:
  - One CHAMPION per stage (baseline, receives remaining traffic)
  - Zero or more CANDIDATEs per stage (each receives rollout_percentage% of traffic)
  - Deterministic routing: sha256(session_id|stage) → bucket → variant
"""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_variants",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("prompt_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("variant_label", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "rollout_percentage",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "changed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("owner", sa.Text(), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(
            ["prompt_id", "version"],
            ["prompts.id", "prompts.version"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("stage", "variant_label"),
        sa.CheckConstraint(
            "status IN ('draft', 'candidate', 'champion', 'deprecated')",
            name="ck_prompt_variants_status",
        ),
        sa.CheckConstraint(
            "rollout_percentage BETWEEN 0 AND 100",
            name="ck_prompt_variants_rollout_pct",
        ),
    )
    op.create_index("idx_prompt_variants_stage", "prompt_variants", ["stage"])
    op.create_index(
        "idx_prompt_variants_stage_status",
        "prompt_variants",
        ["stage", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_prompt_variants_stage_status", table_name="prompt_variants")
    op.drop_index("idx_prompt_variants_stage", table_name="prompt_variants")
    op.drop_table("prompt_variants")
