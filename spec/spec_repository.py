"""
spec/spec_repository.py
-----------------------
CRUD operations for the specs and spec_versions tables.

All functions require DATABASE_URL to be set. Callers that want YAML fallback
should check db.engine.check_connection() before calling these.

Public API
----------
  create_spec(yaml_content, domain_name, version?, *, created_by, description) -> Spec
  get_active_spec(domain_name) -> Spec | None
  get_spec_by_version(domain_name, version) -> Spec | None
  list_specs(domain_name?) -> List[Spec]
  update_spec(spec_id, yaml_content, new_version?, change_summary, *, created_by)
  activate_spec(spec_id) -> Spec
  seed_from_yaml(yaml_path) -> Spec   # idempotent — no-op if already seeded
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from spec.versioning import SpecVersion

import yaml

from db.engine import get_session
from db.models import Spec, SpecVersion

logger = logging.getLogger(__name__)

_INITIAL_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _max_version_for_domain(session: Any, domain_name: str) -> "SpecVersion":
    """Return the highest SpecVersion stored for *domain_name* in *session*."""
    from spec.versioning import SpecVersion

    rows = session.query(Spec.version).filter_by(domain_name=domain_name).all()
    versions = []
    for (v,) in rows:
        try:
            versions.append(SpecVersion.parse(v))
        except ValueError:
            pass
    return max(versions, default=SpecVersion(0, 0, 0))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_spec(
    yaml_content: str,
    domain_name: str,
    version: Optional[str] = None,
    *,
    created_by: Optional[str] = None,
    description: Optional[str] = None,
) -> Spec:
    """Insert a new spec row (status=draft) and record the first SpecVersion.

    *version* defaults to '1.0.0' if not provided. Raises ValueError for
    invalid semver strings.
    """
    from spec.versioning import validate_version

    if version is None:
        version = _INITIAL_VERSION
    elif not validate_version(version):
        raise ValueError(f"Invalid semver version: {version!r}. Expected X.Y.Z format.")

    parsed = yaml.safe_load(yaml_content)
    with get_session() as session:
        spec = Spec(
            domain_name=domain_name,
            version=version,
            status="draft",
            yaml_content=yaml_content,
            parsed_content=parsed,
            created_by=created_by,
            description=description,
        )
        session.add(spec)
        session.flush()  # populate spec.id before creating version

        session.add(
            SpecVersion(
                spec_id=spec.id,
                version=version,
                yaml_content=yaml_content,
                parsed_content=parsed,
                change_summary="Initial version",
                created_by=created_by,
            )
        )
        session.expunge(spec)
        return spec


def get_active_spec(domain_name: str) -> Optional[Spec]:
    """Return the single active spec for *domain_name*, or None."""
    with get_session() as session:
        row = (
            session.query(Spec)
            .filter_by(domain_name=domain_name, status="active")
            .first()
        )
        if row is not None:
            session.expunge(row)
        return row


def get_spec_by_version(domain_name: str, version: str) -> Optional[Spec]:
    """Return a spec by (domain_name, version), or None."""
    with get_session() as session:
        row = (
            session.query(Spec)
            .filter_by(domain_name=domain_name, version=version)
            .first()
        )
        if row is not None:
            session.expunge(row)
        return row


def list_specs(domain_name: Optional[str] = None) -> List[Spec]:
    """List all specs, optionally filtered by domain_name, newest first."""
    with get_session() as session:
        q = session.query(Spec)
        if domain_name:
            q = q.filter_by(domain_name=domain_name)
        rows = q.order_by(Spec.created_at.desc()).all()
        for r in rows:
            session.expunge(r)
        return rows


def update_spec(
    spec_id: uuid.UUID,
    yaml_content: str,
    new_version: Optional[str] = None,
    change_summary: Optional[str] = None,
    *,
    created_by: Optional[str] = None,
) -> Spec:
    """Create a new spec row derived from *spec_id* with the updated YAML.

    If *new_version* is None, the bump type is auto-detected by comparing
    the parent YAML with *yaml_content* and the version is bumped from the
    current maximum for the domain.

    Raises ValueError if:
    - *spec_id* not found
    - *new_version* is not valid semver
    - *new_version* is not strictly greater than the current maximum version
      for the domain

    The new row has status='draft'. Call activate_spec() to promote it.
    """
    from spec.versioning import BumpType, SpecVersion, detect_bump_type

    parsed = yaml.safe_load(yaml_content)

    with get_session() as session:
        parent = session.get(Spec, spec_id)
        if parent is None:
            raise ValueError(f"Spec {spec_id} not found")

        current_max = _max_version_for_domain(session, parent.domain_name)

        auto_detected_bump: Optional[BumpType] = None
        if new_version is None:
            auto_detected_bump = detect_bump_type(parent.yaml_content, yaml_content)
            new_sv = current_max.bump(auto_detected_bump)
            new_version = str(new_sv)
        else:
            try:
                new_sv = SpecVersion.parse(new_version)
            except ValueError as exc:
                raise ValueError(f"Invalid semver version: {new_version!r}") from exc

        if new_sv <= current_max:
            raise ValueError(
                f"New version {new_version} must be greater than the current "
                f"maximum {current_max} for domain '{parent.domain_name}'."
            )

        if change_summary is None:
            if auto_detected_bump is not None:
                change_summary = (
                    f"Auto-bumped ({auto_detected_bump.value}) from {parent.version}"
                )
            else:
                change_summary = f"Updated from {parent.version}"

        new_spec = Spec(
            domain_name=parent.domain_name,
            version=new_version,
            status="draft",
            yaml_content=yaml_content,
            parsed_content=parsed,
            created_by=created_by,
            description=parent.description,
        )
        session.add(new_spec)
        session.flush()

        session.add(
            SpecVersion(
                spec_id=new_spec.id,
                version=new_version,
                yaml_content=yaml_content,
                parsed_content=parsed,
                change_summary=change_summary,
                created_by=created_by,
            )
        )
        session.expunge(new_spec)
        return new_spec


def activate_spec(spec_id: uuid.UUID) -> Spec:
    """Set *spec_id* to status='active' and archive the currently active spec.

    Only one spec per domain can be active at a time.
    """
    with get_session() as session:
        target = session.get(Spec, spec_id)
        if target is None:
            raise ValueError(f"Spec {spec_id} not found")

        session.query(Spec).filter(
            Spec.domain_name == target.domain_name,
            Spec.status == "active",
            Spec.id != spec_id,
        ).update({"status": "archived"})

        target.status = "active"  # type: ignore[assignment]
        session.flush()
        session.expunge(target)
        return target


def seed_from_yaml(yaml_path: Path) -> Spec:
    """Import *yaml_path* into the specs table with status='active'.

    The version is read from the YAML's ``domain.version`` field and validated
    as semver. If absent or invalid, falls back to '1.0.0'.

    Idempotent: if a spec for the same domain_name already exists in the DB,
    returns the existing active spec without modifying anything.
    """
    from spec.versioning import validate_version

    yaml_text = yaml_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(yaml_text)
    domain_name = parsed["domain"]["name"]

    existing = get_active_spec(domain_name)
    if existing is not None:
        logger.info(
            "seed_from_yaml: spec already exists for '%s' (v%s) — skipping",
            domain_name,
            existing.version,
        )
        return existing

    yaml_version = str(parsed.get("domain", {}).get("version", _INITIAL_VERSION))
    if not validate_version(yaml_version):
        logger.warning(
            "seed_from_yaml: version %r in %s is not valid semver — using %s",
            yaml_version,
            yaml_path.name,
            _INITIAL_VERSION,
        )
        yaml_version = _INITIAL_VERSION

    logger.info(
        "seed_from_yaml: seeding spec for domain '%s' (v%s) from %s",
        domain_name,
        yaml_version,
        yaml_path,
    )
    spec = create_spec(
        yaml_content=yaml_text,
        domain_name=domain_name,
        version=yaml_version,
        description=f"Initial seed from {yaml_path.name}",
    )
    return activate_spec(spec.id)  # type: ignore[arg-type]
