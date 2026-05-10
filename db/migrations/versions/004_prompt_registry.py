"""Create prompts table — Prompt Registry (item 10.1)

Revision ID: 004
Revises: 003
Create Date: 2026-05-10

First concrete GovernableArtifact table. Stores versioned prompt templates
with lifecycle status (draft → certified → deprecated).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEMVER_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE prompts (
            id              TEXT        NOT NULL,
            version         TEXT        NOT NULL,
            status          TEXT        NOT NULL DEFAULT 'draft',
            stage           TEXT        NOT NULL,
            content         TEXT        NOT NULL,
            variables       JSONB       NOT NULL DEFAULT '[]',
            owner           TEXT        NOT NULL DEFAULT '',
            description     TEXT        NOT NULL DEFAULT '',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            changed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            sunset_date     DATE,
            replacement_id  TEXT,
            adr             TEXT,
            PRIMARY KEY (id, version),
            CONSTRAINT ck_prompts_version_semver
                CHECK (version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'),
            CONSTRAINT ck_prompts_status
                CHECK (status IN ('draft', 'certified', 'deprecated'))
        )
        """
    )
    op.execute("CREATE INDEX idx_prompts_stage  ON prompts(stage)")
    op.execute("CREATE INDEX idx_prompts_status ON prompts(status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prompts CASCADE")
