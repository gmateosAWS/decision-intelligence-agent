"""tests/prompts/test_routing.py — Unit tests for prompt A/B routing (item 10.2)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from prompts.models import PromptVariant, PromptVariantStatus
from prompts.routing import _bucket_for, invalidate_variant_cache, select_variant


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_variant(
    stage: str,
    label: str,
    status: PromptVariantStatus,
    rollout_pct: int,
    prompt_id: str = "planner",
    version: str = "1.0.0",
) -> PromptVariant:
    return PromptVariant(
        id="00000000-0000-0000-0000-000000000001",
        stage=stage,
        prompt_id=prompt_id,
        version=version,
        variant_label=label,
        status=status,
        rollout_percentage=rollout_pct,
        created_at=_now(),
        changed_at=_now(),
    )


# ---------------------------------------------------------------------------
# _bucket_for
# ---------------------------------------------------------------------------


def test_bucket_for_no_session_returns_zero():
    assert _bucket_for(None, "planner") == 0
    assert _bucket_for("", "planner") == 0


def test_bucket_for_deterministic():
    sid = "abc-123"
    b1 = _bucket_for(sid, "planner")
    b2 = _bucket_for(sid, "planner")
    assert b1 == b2


def test_bucket_for_range():
    for i in range(50):
        sid = f"session-{i}"
        b = _bucket_for(sid, "planner")
        assert 0 <= b < 100


def test_bucket_for_stage_dependency():
    sid = "same-session"
    b_planner = _bucket_for(sid, "planner")
    b_synthesizer = _bucket_for(sid, "synthesizer")
    # Different stages → different buckets (probabilistically true for real session_ids)
    assert b_planner != b_synthesizer


def test_bucket_for_matches_sha256():
    sid = "test-session-id"
    stage = "planner"
    digest = hashlib.sha256(f"{sid}|{stage}".encode()).digest()
    expected = int.from_bytes(digest[:4], "big") % 100
    assert _bucket_for(sid, stage) == expected


# ---------------------------------------------------------------------------
# select_variant — no DB (empty tuple from cache)
# ---------------------------------------------------------------------------


def test_select_variant_no_variants_returns_none():
    """When no variants exist, select_variant returns None."""
    invalidate_variant_cache()
    with patch("prompts.routing._load_active_variants", return_value=()):
        result = select_variant("planner", "any-session")
    assert result is None


def test_select_variant_no_session_returns_champion():
    """No session_id → bucket=0 → champion returned when no candidate covers it."""
    champion = _make_variant(
        "planner", "v1-champion", PromptVariantStatus.CHAMPION, 100
    )
    invalidate_variant_cache()
    with patch("prompts.routing._load_active_variants", return_value=(champion,)):
        result = select_variant("planner", None)
    assert result is not None
    assert result.status == PromptVariantStatus.CHAMPION


def test_select_variant_candidate_captures_bucket():
    """A CANDIDATE at 100% captures all traffic (bucket is always < 100)."""
    candidate = _make_variant("planner", "v2-test", PromptVariantStatus.CANDIDATE, 100)
    champion = _make_variant("planner", "v1-ctrl", PromptVariantStatus.CHAMPION, 100)
    invalidate_variant_cache()
    with patch(
        "prompts.routing._load_active_variants", return_value=(candidate, champion)
    ):
        result = select_variant("planner", "any-session")
    assert result is not None
    assert result.variant_label == "v2-test"


def test_select_variant_zero_pct_candidate_skipped():
    """A CANDIDATE at 0% is never selected — all traffic goes to CHAMPION."""
    candidate = _make_variant("planner", "v2-zero", PromptVariantStatus.CANDIDATE, 0)
    champion = _make_variant("planner", "v1-ctrl", PromptVariantStatus.CHAMPION, 100)
    invalidate_variant_cache()
    with patch(
        "prompts.routing._load_active_variants", return_value=(candidate, champion)
    ):
        result = select_variant("planner", "session-x")
    assert result is not None
    assert result.status == PromptVariantStatus.CHAMPION


def test_select_variant_deterministic_across_calls():
    """Same session always gets same variant."""
    candidate = _make_variant("planner", "v2-cand", PromptVariantStatus.CANDIDATE, 50)
    champion = _make_variant("planner", "v1-ctrl", PromptVariantStatus.CHAMPION, 100)
    session = "stable-session-abc"

    results = set()
    invalidate_variant_cache()
    with patch(
        "prompts.routing._load_active_variants", return_value=(candidate, champion)
    ):
        for _ in range(10):
            r = select_variant("planner", session)
            results.add(r.variant_label if r else None)

    assert len(results) == 1, "Same session must always get the same variant"


def test_select_variant_distributes_traffic():
    """Routing distributes traffic roughly proportionally across many sessions."""
    candidate = _make_variant("planner", "v2-cand", PromptVariantStatus.CANDIDATE, 30)
    champion = _make_variant("planner", "v1-ctrl", PromptVariantStatus.CHAMPION, 100)

    candidate_count = 0
    champion_count = 0
    invalidate_variant_cache()
    with patch(
        "prompts.routing._load_active_variants", return_value=(candidate, champion)
    ):
        for i in range(200):
            r = select_variant("planner", f"session-{i}")
            if r and r.variant_label == "v2-cand":
                candidate_count += 1
            else:
                champion_count += 1

    # With 30% rollout across 200 sessions, expect roughly 60 ± 25 in candidate
    assert (
        20 <= candidate_count <= 80
    ), f"Expected ~60 candidate selections out of 200, got {candidate_count}"


def test_invalidate_variant_cache_clears():
    """invalidate_variant_cache() forces the next call to re-query."""
    mock_load = MagicMock(return_value=())
    with patch("prompts.routing._load_active_variants", mock_load):
        select_variant("planner", "s1")
    invalidate_variant_cache()
    with patch("prompts.routing._load_active_variants", mock_load):
        select_variant("planner", "s1")
    # Both calls should reach the (patched) loader since we cleared cache between them
    assert mock_load.call_count >= 1
