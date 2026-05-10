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
from datetime import datetime, timezone
from typing import List, Optional, Tuple, TypedDict

from prompts.models import PromptRecord, PromptStatus

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
    Returns the list of PromptRecords that are now certified (seeded or pre-existing).
    """
    if not os.getenv("DATABASE_URL", ""):
        return []

    result: List[PromptRecord] = []
    for spec in _SEED_PROMPTS:
        pid = spec["prompt_id"]
        stage = spec["stage"]

        existing = get_certified_prompt(stage)
        if existing is not None:
            result.append(existing)
            continue

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
            result.append(certified)
            logger.info("Prompt seeded and certified: %s@1.0.0", pid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to seed prompt '%s': %s", pid, exc)

    return result


# ---------------------------------------------------------------------------
# Agent-facing helper
# ---------------------------------------------------------------------------


def get_prompt_template(stage: str, fallback: str) -> Tuple[str, Optional[str]]:
    """
    Return ``(template_string, version)`` for *stage*.

    Tries the registry first (certified prompt for the stage).
    Falls back to *fallback* when the registry is unavailable, empty,
    or raises an exception. In fallback mode version is None.

    This is the primary entry point for agent modules.
    """
    record = get_certified_prompt(stage)
    if record is not None:
        return record.content, record.version
    return fallback, None
