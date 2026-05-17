"""
prompts/routing.py
──────────────────
Deterministic A/B variant routing for the Prompt Registry (item 10.2).

Routing algorithm
-----------------
1. Load active (CHAMPION + CANDIDATE) variants for the requested stage.
   Result is cached per stage; cache is cleared when operator mutations
   change rollout configuration (start_rollout, adjust_rollout,
   promote_to_champion, deprecate_variant).

2. Compute a deterministic bucket [0, 100) from sha256(session_id|stage).
   The same session always receives the same variant, enabling stable
   quality measurement across turns.

3. Walk CANDIDATEs in creation order (oldest first), assigning each a
   cumulative slice.  The CHAMPION absorbs all remaining traffic.

Example: CANDIDATE_A at 20%, CANDIDATE_B at 15%, CHAMPION at 65%
  bucket  0–19  → CANDIDATE_A
  bucket 20–34  → CANDIDATE_B
  bucket 35–99  → CHAMPION

Cache invalidation
------------------
Call ``invalidate_variant_cache()`` after any routing mutation so the next
request re-reads the DB. The prompt-content cache in registry.py is keyed
on (prompt_id, version) and never needs clearing — content is immutable.
"""

from __future__ import annotations

import hashlib
import logging
import os
from functools import lru_cache
from typing import List, Optional

from prompts.models import PromptVariant, PromptVariantStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cached DB load
# ---------------------------------------------------------------------------


@lru_cache(maxsize=8)
def _load_active_variants(stage: str) -> tuple[PromptVariant, ...]:
    """
    Load CHAMPION + CANDIDATE variants for *stage* from the DB.

    Returns an immutable tuple (required by lru_cache).
    Cache is cleared by ``invalidate_variant_cache()`` after mutations.
    Returns empty tuple when DATABASE_URL is not set or on any error.
    """
    if not os.getenv("DATABASE_URL", ""):
        return ()
    try:
        from db.engine import get_session
        from db.models import PromptVariantRow

        with get_session() as session:
            rows = (
                session.query(PromptVariantRow)
                .filter(
                    PromptVariantRow.stage == stage,
                    PromptVariantRow.status.in_(
                        [
                            PromptVariantStatus.CHAMPION.value,
                            PromptVariantStatus.CANDIDATE.value,
                        ]
                    ),
                )
                .order_by(PromptVariantRow.created_at.asc())
                .all()
            )
            return tuple(_row_to_variant(r) for r in rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("routing: failed to load variants for stage %r: %s", stage, exc)
        return ()


def invalidate_variant_cache() -> None:
    """Clear the routing cache so the next call re-reads the DB."""
    _load_active_variants.cache_clear()


# ---------------------------------------------------------------------------
# Deterministic bucket
# ---------------------------------------------------------------------------


def _bucket_for(session_id: Optional[str], stage: str) -> int:
    """Return a deterministic bucket in [0, 100) for (session_id, stage)."""
    if not session_id:
        return 0
    digest = hashlib.sha256(f"{session_id}|{stage}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 100


# ---------------------------------------------------------------------------
# Public routing API
# ---------------------------------------------------------------------------


def select_variant(stage: str, session_id: Optional[str]) -> Optional[PromptVariant]:
    """
    Return the PromptVariant to serve for *(stage, session_id)*.

    Returns None when no active variants exist for the stage — callers
    fall back to the certified-prompt path in registry.get_prompt_template().
    """
    variants: tuple[PromptVariant, ...] = _load_active_variants(stage)
    if not variants:
        return None

    bucket = _bucket_for(session_id, stage)

    # Walk candidates in order (oldest first), assign cumulative slice
    cumulative = 0
    candidates: List[PromptVariant] = [
        v for v in variants if v.status == PromptVariantStatus.CANDIDATE
    ]
    for candidate in candidates:
        cumulative += candidate.rollout_percentage
        if bucket < cumulative:
            return candidate

    # Champion absorbs the remainder
    champion = next(
        (v for v in variants if v.status == PromptVariantStatus.CHAMPION), None
    )
    return champion


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_variant(row: object) -> PromptVariant:
    """Convert a PromptVariantRow ORM row to a PromptVariant Pydantic model."""
    return PromptVariant(
        id=str(row.id),  # type: ignore[attr-defined]
        stage=str(row.stage),  # type: ignore[attr-defined]
        prompt_id=str(row.prompt_id),  # type: ignore[attr-defined]
        version=str(row.version),  # type: ignore[attr-defined]
        variant_label=str(row.variant_label),  # type: ignore[attr-defined]
        status=PromptVariantStatus(str(row.status)),  # type: ignore[attr-defined]
        rollout_percentage=int(row.rollout_percentage),  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
        changed_at=row.changed_at,  # type: ignore[attr-defined]
        owner=str(row.owner or ""),  # type: ignore[attr-defined]
        notes=str(row.notes or ""),  # type: ignore[attr-defined]
    )
