"""Add semver CHECK constraint to specs.version and spec_versions.version

Revision ID: 003
Revises: 002
Create Date: 2026-05-09

Normalises any pre-existing non-semver version strings to '1.0.0' before
adding the constraint so the migration is safe on databases that were seeded
before formal versioning was enforced.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEMVER_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"


def upgrade() -> None:
    # Normalise spec_versions first (FK child) to avoid constraint violations
    # on the parent table update.
    op.execute(
        f"UPDATE spec_versions SET version = '1.0.0' "
        f"WHERE version !~ '{_SEMVER_PATTERN}'"
    )

    # For specs: rows with an invalid version that would collide with an
    # existing '1.0.0' row for the same domain are deleted (they are
    # duplicates that cannot be normalised without violating the unique
    # constraint). The remaining invalid rows are then set to '1.0.0'.
    op.execute(
        f"""
        DELETE FROM specs
        WHERE version !~ '{_SEMVER_PATTERN}'
          AND (domain_name, '1.0.0') IN (
            SELECT domain_name, version FROM specs WHERE version = '1.0.0'
          )
        """
    )
    op.execute(
        f"UPDATE specs SET version = '1.0.0' " f"WHERE version !~ '{_SEMVER_PATTERN}'"
    )

    # Add CHECK constraints — valid semver only from this point forward.
    op.execute(
        f"ALTER TABLE specs ADD CONSTRAINT ck_specs_version_semver "
        f"CHECK (version ~ '{_SEMVER_PATTERN}')"
    )
    op.execute(
        f"ALTER TABLE spec_versions ADD CONSTRAINT ck_spec_versions_version_semver "
        f"CHECK (version ~ '{_SEMVER_PATTERN}')"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE spec_versions DROP CONSTRAINT IF EXISTS "
        "ck_spec_versions_version_semver"
    )
    op.execute("ALTER TABLE specs DROP CONSTRAINT IF EXISTS ck_specs_version_semver")
