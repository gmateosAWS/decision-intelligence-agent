"""
prompts/registry.py
───────────────────
CRUD + lifecycle operations for versioned prompt artifacts.

All write operations target the ``prompts`` PostgreSQL table.
Falls back gracefully when DATABASE_URL is not set (unit tests, SQLite mode):
  - get_certified_prompt() returns None → callers use the inline fallback
  - create_prompt() / certify_prompt() raise RuntimeError

The public helper ``get_prompt_template(stage, fallback)`` is what agents
call: it returns (template_string, version_or_None) and is fully fail-safe.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import List, Optional, Tuple, TypedDict

from prompts.models import (
    PromptRecord,
    PromptStatus,
    PromptVariant,
    PromptVariantStatus,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_record(row) -> PromptRecord:
    """Convert a SQLAlchemy ORM Prompt row to a PromptRecord."""
    import json

    variables = row.variables
    if isinstance(variables, str):
        variables = json.loads(variables)

    return PromptRecord(
        id=str(row.id),
        version=str(row.version),
        status=PromptStatus(str(row.status)),
        stage=str(row.stage),
        content=str(row.content),
        variables=list(variables or []),
        owner=str(row.owner or ""),
        description=str(row.description or ""),
        created_at=row.created_at,
        changed_at=row.changed_at,
        sunset_date=row.sunset_date,
        replacement_id=str(row.replacement_id) if row.replacement_id else None,
        adr=str(row.adr) if row.adr else None,
    )


def _get_session_and_model():
    """Return (get_session, Prompt) or raise RuntimeError when DB unavailable."""
    from db.engine import get_session
    from db.models import Prompt

    return get_session, Prompt


def _get_variant_model():
    """Return (get_session, PromptVariantRow) or raise when DB unavailable."""
    from db.engine import get_session
    from db.models import PromptVariantRow

    return get_session, PromptVariantRow


def _row_to_variant(row) -> PromptVariant:
    """Convert a PromptVariantRow ORM row to a PromptVariant Pydantic model."""
    return PromptVariant(
        id=str(row.id),
        stage=str(row.stage),
        prompt_id=str(row.prompt_id),
        version=str(row.version),
        variant_label=str(row.variant_label),
        status=PromptVariantStatus(str(row.status)),
        rollout_percentage=int(row.rollout_percentage),
        created_at=row.created_at,
        changed_at=row.changed_at,
        owner=str(row.owner or ""),
        notes=str(row.notes or ""),
    )


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def get_certified_prompt(stage: str) -> Optional[PromptRecord]:
    """
    Return the latest certified prompt for a stage, or None.

    "Latest" = highest semver among all certified rows for this stage,
    determined lexicographically (semver ordering works lexicographically
    for equal-width version strings; we use DB ordering for simplicity).
    """
    if not os.getenv("DATABASE_URL", ""):
        return None
    try:
        get_session, Prompt = _get_session_and_model()
        with get_session() as session:
            row = (
                session.query(Prompt)
                .filter_by(stage=stage, status=PromptStatus.CERTIFIED.value)
                .order_by(Prompt.changed_at.desc())
                .first()
            )
            # _row_to_record must be called inside the session context so that
            # lazy-loaded ORM attributes (e.g. variables) can still be accessed.
            return _row_to_record(row) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("prompt registry read failed (%s): %s", stage, exc)
        return None


def get_prompt(prompt_id: str, version: str) -> Optional[PromptRecord]:
    """Return a specific (id, version) prompt, or None if not found."""
    if not os.getenv("DATABASE_URL", ""):
        return None
    try:
        get_session, Prompt = _get_session_and_model()
        with get_session() as session:
            row = session.query(Prompt).filter_by(id=prompt_id, version=version).first()
            return _row_to_record(row) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "prompt registry get failed (%s@%s): %s", prompt_id, version, exc
        )
        return None


def list_prompts(
    stage: Optional[str] = None,
    status: Optional[PromptStatus] = None,
) -> List[PromptRecord]:
    """List prompts with optional filters. Returns [] when DB unavailable."""
    if not os.getenv("DATABASE_URL", ""):
        return []
    try:
        get_session, Prompt = _get_session_and_model()
        with get_session() as session:
            q = session.query(Prompt)
            if stage is not None:
                q = q.filter_by(stage=stage)
            if status is not None:
                q = q.filter_by(status=status.value)
            rows = q.order_by(Prompt.changed_at.desc()).all()
            return [_row_to_record(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("prompt registry list failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


def create_prompt(
    prompt_id: str,
    stage: str,
    content: str,
    version: str = "1.0.0",
    variables: Optional[List[str]] = None,
    owner: str = "",
    description: str = "",
    adr: Optional[str] = None,
) -> PromptRecord:
    """
    Create a new prompt as DRAFT.

    Raises RuntimeError when DATABASE_URL is not set.
    Raises ValueError when (id, version) already exists.
    """
    get_session, Prompt = _get_session_and_model()
    now = _now()
    with get_session() as session:
        existing = (
            session.query(Prompt).filter_by(id=prompt_id, version=version).first()
        )
        if existing:
            raise ValueError(
                f"Prompt '{prompt_id}@{version}' already exists"
                f" (status={existing.status})."
                " Bump the version to create a new variant."
            )
        row = Prompt(
            id=prompt_id,
            version=version,
            status=PromptStatus.DRAFT.value,
            stage=stage,
            content=content,
            variables=variables or [],
            owner=owner,
            description=description,
            created_at=now,
            changed_at=now,
            adr=adr,
        )
        session.add(row)
    return get_prompt(prompt_id, version)  # type: ignore[return-value]


def certify_prompt(prompt_id: str, version: str) -> PromptRecord:
    """
    Promote a DRAFT prompt to CERTIFIED.

    Exactly one certified prompt per stage at a time: the previously
    certified prompt for the same stage becomes DEPRECATED automatically.
    """
    get_session, Prompt = _get_session_and_model()
    with get_session() as session:
        target = session.query(Prompt).filter_by(id=prompt_id, version=version).first()
        if target is None:
            raise ValueError(f"Prompt '{prompt_id}@{version}' not found.")
        if target.status == PromptStatus.CERTIFIED.value:
            raise ValueError(f"Prompt '{prompt_id}@{version}' is already certified.")

        # Deprecate existing certified prompt for the same stage
        prev_certified = (
            session.query(Prompt)
            .filter_by(stage=str(target.stage), status=PromptStatus.CERTIFIED.value)
            .first()
        )
        if prev_certified is not None:
            prev_certified.status = PromptStatus.DEPRECATED.value
            prev_certified.changed_at = _now()

        target.status = PromptStatus.CERTIFIED.value
        target.changed_at = _now()
    return get_prompt(prompt_id, version)  # type: ignore[return-value]


def deprecate_prompt(
    prompt_id: str,
    version: str,
    replacement_id: Optional[str] = None,
) -> PromptRecord:
    """Mark a prompt as DEPRECATED, optionally noting a replacement."""
    get_session, Prompt = _get_session_and_model()
    with get_session() as session:
        row = session.query(Prompt).filter_by(id=prompt_id, version=version).first()
        if row is None:
            raise ValueError(f"Prompt '{prompt_id}@{version}' not found.")
        row.status = PromptStatus.DEPRECATED.value
        row.changed_at = _now()
        if replacement_id:
            row.replacement_id = replacement_id
    return get_prompt(prompt_id, version)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Variant CRUD (item 10.2)
# ---------------------------------------------------------------------------


def list_variants(stage: Optional[str] = None) -> List[PromptVariant]:
    """List all variant rows, optionally filtered by stage. Returns [] on error."""
    if not os.getenv("DATABASE_URL", ""):
        return []
    try:
        get_session, PromptVariantRow = _get_variant_model()
        with get_session() as session:
            q = session.query(PromptVariantRow)
            if stage is not None:
                q = q.filter_by(stage=stage)
            rows = q.order_by(PromptVariantRow.created_at.asc()).all()
            return [_row_to_variant(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_variants failed: %s", exc)
        return []


def get_variant(variant_label: str, stage: str) -> Optional[PromptVariant]:
    """Return a specific variant by (stage, variant_label), or None."""
    if not os.getenv("DATABASE_URL", ""):
        return None
    try:
        get_session, PromptVariantRow = _get_variant_model()
        with get_session() as session:
            row = (
                session.query(PromptVariantRow)
                .filter_by(stage=stage, variant_label=variant_label)
                .first()
            )
            return _row_to_variant(row) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_variant failed (%s/%s): %s", stage, variant_label, exc)
        return None


def start_rollout(
    stage: str,
    prompt_id: str,
    version: str,
    variant_label: str,
    rollout_percentage: int,
    owner: str = "",
    notes: str = "",
) -> PromptVariant:
    """
    Register a new CANDIDATE variant in traffic.

    Raises ValueError when:
      - (stage, variant_label) already exists
      - rollout_percentage is out of [1, 99]
      - the referenced (prompt_id, version) is not CERTIFIED
      - adding this candidate would exceed 100% total candidate traffic
    """
    if not 1 <= rollout_percentage <= 99:
        raise ValueError(
            f"rollout_percentage must be 1–99 for a CANDIDATE;"
            f" got {rollout_percentage}."
        )
    prompt_record = get_prompt(prompt_id, version)
    if prompt_record is None:
        raise ValueError(f"Prompt '{prompt_id}@{version}' not found.")
    if prompt_record.status != PromptStatus.CERTIFIED:
        raise ValueError(
            f"Only CERTIFIED prompts can be registered as variants;"
            f" '{prompt_id}@{version}' is {prompt_record.status.value}."
        )

    get_session, PromptVariantRow = _get_variant_model()
    now = _now()
    with get_session() as session:
        existing = (
            session.query(PromptVariantRow)
            .filter_by(stage=stage, variant_label=variant_label)
            .first()
        )
        if existing is not None:
            raise ValueError(
                f"Variant '{variant_label}' already exists for stage '{stage}'."
            )

        # Validate total candidate traffic doesn't exceed 100%
        current_candidates = (
            session.query(PromptVariantRow)
            .filter_by(stage=stage, status=PromptVariantStatus.CANDIDATE.value)
            .all()
        )
        total_pct = sum(int(r.rollout_percentage) for r in current_candidates)
        if total_pct + rollout_percentage > 100:
            raise ValueError(
                f"Total candidate rollout for stage '{stage}' would exceed 100%:"
                f" current={total_pct}%, new={rollout_percentage}%."
            )

        row = PromptVariantRow(
            id=uuid.uuid4(),
            stage=stage,
            prompt_id=prompt_id,
            version=version,
            variant_label=variant_label,
            status=PromptVariantStatus.CANDIDATE.value,
            rollout_percentage=rollout_percentage,
            created_at=now,
            changed_at=now,
            owner=owner,
            notes=notes,
        )
        session.add(row)

    from prompts.routing import invalidate_variant_cache

    invalidate_variant_cache()
    result = get_variant(variant_label, stage)
    if result is None:
        raise RuntimeError("start_rollout: failed to retrieve newly created variant.")
    return result


def adjust_rollout(
    stage: str, variant_label: str, rollout_percentage: int
) -> PromptVariant:
    """
    Adjust the traffic percentage of an existing CANDIDATE variant.

    Raises ValueError when:
      - variant not found or not in CANDIDATE status
      - new total candidate traffic would exceed 100%
    """
    if not 0 <= rollout_percentage <= 99:
        raise ValueError(
            f"rollout_percentage must be 0–99 for a CANDIDATE;"
            f" got {rollout_percentage}."
        )
    get_session, PromptVariantRow = _get_variant_model()
    with get_session() as session:
        row = (
            session.query(PromptVariantRow)
            .filter_by(stage=stage, variant_label=variant_label)
            .first()
        )
        if row is None:
            raise ValueError(
                f"Variant '{variant_label}' not found for stage '{stage}'."
            )
        if str(row.status) != PromptVariantStatus.CANDIDATE.value:
            raise ValueError(
                f"Can only adjust CANDIDATE variants;"
                f" '{variant_label}' is {row.status}."
            )

        other_candidates = (
            session.query(PromptVariantRow)
            .filter(
                PromptVariantRow.stage == stage,
                PromptVariantRow.status == PromptVariantStatus.CANDIDATE.value,
                PromptVariantRow.variant_label != variant_label,
            )
            .all()
        )
        total_other = sum(int(r.rollout_percentage) for r in other_candidates)
        if total_other + rollout_percentage > 100:
            raise ValueError(
                f"Adjusting '{variant_label}' to {rollout_percentage}% would exceed"
                f" 100% total candidate traffic (others={total_other}%)."
            )

        row.rollout_percentage = rollout_percentage
        row.changed_at = _now()

    from prompts.routing import invalidate_variant_cache

    invalidate_variant_cache()
    result = get_variant(variant_label, stage)
    if result is None:
        raise RuntimeError("adjust_rollout: failed to retrieve updated variant.")
    return result


def promote_to_champion(stage: str, variant_label: str) -> PromptVariant:
    """
    Promote a CANDIDATE to CHAMPION.

    The previous CHAMPION is DEPRECATED. The promoted variant is set to
    rollout_percentage=100. All other CANDIDATE variants are left unchanged
    (operators should deprecate them separately if the test is over).

    Raises ValueError when variant not found or not in CANDIDATE status.
    """
    get_session, PromptVariantRow = _get_variant_model()
    with get_session() as session:
        target = (
            session.query(PromptVariantRow)
            .filter_by(stage=stage, variant_label=variant_label)
            .first()
        )
        if target is None:
            raise ValueError(
                f"Variant '{variant_label}' not found for stage '{stage}'."
            )
        if str(target.status) != PromptVariantStatus.CANDIDATE.value:
            raise ValueError(
                f"Only CANDIDATE variants can be promoted to CHAMPION;"
                f" '{variant_label}' is {target.status}."
            )

        # Deprecate existing champion
        old_champion = (
            session.query(PromptVariantRow)
            .filter_by(stage=stage, status=PromptVariantStatus.CHAMPION.value)
            .first()
        )
        if old_champion is not None:
            old_champion.status = PromptVariantStatus.DEPRECATED.value
            old_champion.changed_at = _now()

        target.status = PromptVariantStatus.CHAMPION.value
        target.rollout_percentage = 100
        target.changed_at = _now()

    from prompts.routing import invalidate_variant_cache

    invalidate_variant_cache()
    result = get_variant(variant_label, stage)
    if result is None:
        raise RuntimeError("promote_to_champion: failed to retrieve updated variant.")
    return result


def deprecate_variant(stage: str, variant_label: str) -> PromptVariant:
    """
    Deprecate a CANDIDATE or CHAMPION variant (sets rollout to 0).

    If the deprecated variant was the CHAMPION, callers should create a new
    CHAMPION immediately or all traffic will fall back to the certified prompt.

    Raises ValueError when variant not found.
    """
    get_session, PromptVariantRow = _get_variant_model()
    with get_session() as session:
        row = (
            session.query(PromptVariantRow)
            .filter_by(stage=stage, variant_label=variant_label)
            .first()
        )
        if row is None:
            raise ValueError(
                f"Variant '{variant_label}' not found for stage '{stage}'."
            )
        row.status = PromptVariantStatus.DEPRECATED.value
        row.rollout_percentage = 0
        row.changed_at = _now()

    from prompts.routing import invalidate_variant_cache

    invalidate_variant_cache()
    result = get_variant(variant_label, stage)
    if result is None:
        raise RuntimeError("deprecate_variant: failed to retrieve updated variant.")
    return result


# ---------------------------------------------------------------------------
# Seed from code
# ---------------------------------------------------------------------------

# These template strings are the canonical fallbacks used by the agents.
# They live here so seed_prompts_from_code() can extract them without
# importing the full agent modules (which trigger load_dotenv + LLM init).

PLANNER_SYSTEM_TEMPLATE = (
    "You are the planner of a Decision Intelligence system\n"
    "for a {domain_name} business.\n"
    "The system models how decision variables affect demand,\n"
    "revenue, cost and profit.\n\n"
    "You have three tools available:\n\n"
    "1. OPTIMIZATION\n"
    "   Use when the user asks: what is the best price? what price maximises\n"
    "   profit? what decision should I make? find the optimal...\n"
    "   The tool searches the full decision variable range and returns the\n"
    "   combination that maximises expected profit.\n\n"
    "2. SIMULATION\n"
    "   Use when the user asks: what happens if X is Y? simulate scenario...\n"
    "   what would profit be at value Z? what is the expected outcome?\n"
    "   The tool evaluates a specific scenario under uncertainty\n"
    "   using Monte Carlo simulation.\n\n"
    "3. KNOWLEDGE\n"
    "   Use when the user asks: how does the model work? what is demand\n"
    "   elasticity? explain the methodology, what does Monte Carlo mean?\n"
    "   The tool retrieves relevant explanations from the knowledge base.\n\n"
    "{examples}\n\n"
    "If the user mentions specific values for decision variables, extract\n"
    "them into the `params` dict using the exact variable name as key.\n"
    "Decision variables available:\n"
    "{vars_description}\n"
    "Leave params empty if no specific values are mentioned.\n\n"
    "Before selecting a tool, reason step by step in the `reasoning` field:\n"
    "  1. What is the user asking for?\n"
    "  2. Does the query mention concrete values for any decision variable?\n"
    "  3. Is this an exploration/optimization question or a request to understand\n"
    "     how the system works?\n"
    "  4. Which tool fits best and why?\n\n"
    "Select the single most appropriate tool for the user's query.\n\n"
    "Detect the language of the user's query and return its ISO 639-1\n"
    "code in the 'language' field (e.g. 'es' for Spanish, 'en' for\n"
    "English, 'fr' for French, 'de' for German)."
)

SYNTHESIZER_SYSTEM_TEMPLATE = (
    "You are a business intelligence assistant. {language_directive}"
)

JUDGE_SYSTEM_TEMPLATE = (
    "You are an online quality judge for a Decision Intelligence "
    "assistant.\n"
    "Evaluate the assistant answer strictly against the user"
    "'s query and the raw tool output.\n"
    "Do not reward style alone. Prefer factual grounding, "
    "quantitative consistency, and decision usefulness.\n"
    "Approve only if the answer is clearly grounded in the tool "
    "result and directly answers the user.\n"
    "Use a strict approval threshold of {threshold}."
)

JUDGE_REVISION_TEMPLATE = (
    "You revise answers for a Decision Intelligence assistant. {language_directive}"
)


# ---------------------------------------------------------------------------
# Prompt content cache (immutable by (prompt_id, version) — never invalidated)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=256)
def _get_cached_prompt_content(prompt_id: str, version: str) -> Optional[str]:
    """Return prompt content for (prompt_id, version). Content is immutable."""
    record = get_prompt(prompt_id, version)
    return record.content if record else None


class _SeedEntry(TypedDict):
    prompt_id: str
    stage: str
    content: str
    variables: List[str]
    description: str


_SEED_PROMPTS: List[_SeedEntry] = [
    {
        "prompt_id": "planner",
        "stage": "planner",
        "content": PLANNER_SYSTEM_TEMPLATE,
        "variables": ["domain_name", "examples", "vars_description"],
        "description": (
            "Planner system prompt: tool routing with CoT and dynamic spec context."
        ),
    },
    {
        "prompt_id": "synthesizer",
        "stage": "synthesizer",
        "content": SYNTHESIZER_SYSTEM_TEMPLATE,
        "variables": ["language_directive"],
        "description": "Synthesizer system prompt: business-oriented answer.",
    },
    {
        "prompt_id": "judge",
        "stage": "judge",
        "content": JUDGE_SYSTEM_TEMPLATE,
        "variables": ["threshold"],
        "description": "Judge system prompt: online quality gate evaluation.",
    },
    {
        "prompt_id": "judge.revision",
        "stage": "judge.revision",
        "content": JUDGE_REVISION_TEMPLATE,
        "variables": ["language_directive"],
        "description": "Judge revision system prompt: single-pass answer rewrite.",
    },
]


def seed_prompts_from_code() -> List[PromptRecord]:
    """
    Seed the four inline prompts as v1.0.0 certified. Idempotent.

    If a certified prompt for a stage already exists, it is left unchanged.
    Also ensures a CHAMPION variant exists for every certified prompt
    (creates one if absent). Returns the list of certified PromptRecords.
    """
    if not os.getenv("DATABASE_URL", ""):
        return []

    result: List[PromptRecord] = []
    for spec in _SEED_PROMPTS:
        pid = spec["prompt_id"]
        stage = spec["stage"]

        existing = get_certified_prompt(stage)
        if existing is not None:
            certified = existing
        else:
            try:
                create_prompt(
                    prompt_id=pid,
                    stage=stage,
                    content=spec["content"],
                    version="1.0.0",
                    variables=spec["variables"],
                    description=spec["description"],
                    owner="system",
                )
                certified = certify_prompt(pid, "1.0.0")
                logger.info("Prompt seeded and certified: %s@1.0.0", pid)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to seed prompt '%s': %s", pid, exc)
                continue

        result.append(certified)
        _ensure_champion_variant(certified)

    return result


def _ensure_champion_variant(record: PromptRecord) -> None:
    """Create a CHAMPION variant for *record* if none exists yet. Idempotent."""
    try:
        get_session, PromptVariantRow = _get_variant_model()
        with get_session() as session:
            champion = (
                session.query(PromptVariantRow)
                .filter_by(
                    stage=record.stage, status=PromptVariantStatus.CHAMPION.value
                )
                .first()
            )
            if champion is not None:
                return  # already has a champion
            label = f"{record.id}-v{record.version.replace('.', '')}-champion"
            row = PromptVariantRow(
                id=uuid.uuid4(),
                stage=record.stage,
                prompt_id=record.id,
                version=record.version,
                variant_label=label,
                status=PromptVariantStatus.CHAMPION.value,
                rollout_percentage=100,
                created_at=_now(),
                changed_at=_now(),
                owner="system",
                notes="Auto-created by seed_prompts_from_code()",
            )
            session.add(row)
        from prompts.routing import invalidate_variant_cache

        invalidate_variant_cache()
        logger.info("Champion variant seeded for stage '%s': %s", record.stage, label)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to seed champion variant for '%s': %s", record.stage, exc
        )


# ---------------------------------------------------------------------------
# Agent-facing helper
# ---------------------------------------------------------------------------


def get_prompt_template(
    stage: str,
    fallback: str,
    session_id: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Return ``(template_string, version, variant_label)`` for *stage*.

    Resolution order:
    1. If variant routing is active (prompt_variants table has entries for stage),
       select a variant deterministically from session_id and return its content.
       Both the routing decision and the prompt content are cached; the routing
       cache is cleared by variant mutations (start_rollout, adjust_rollout, etc.)
       so that operator changes take effect on the next request.
    2. If no variants exist, fall back to the latest CERTIFIED prompt.
    3. If the registry is unavailable or empty, return (fallback, None, None).

    Caching guarantees zero DB queries per call after the first for a given
    (stage, session_id) combination until a routing mutation clears the cache.
    """
    from prompts.routing import select_variant

    variant = select_variant(stage, session_id)
    if variant is not None:
        content = _get_cached_prompt_content(variant.prompt_id, variant.version)
        if content is not None:
            return content, variant.version, variant.variant_label
        # Content fetch failed — fall through to certified-prompt path

    record = get_certified_prompt(stage)
    if record is not None:
        # Cache content so repeated calls don't re-query
        _get_cached_prompt_content(record.id, record.version)
        return record.content, record.version, None
    return fallback, None, None
