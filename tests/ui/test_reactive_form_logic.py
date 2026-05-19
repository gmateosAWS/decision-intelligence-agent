"""
tests/ui/test_reactive_form_logic.py
--------------------------------------
Unit tests for the pure helper functions in ui/components.py that back
the reactive correction form (item 5.13.c).

All tests are offline — no DB, no LLM, no Streamlit runtime.
The helpers under test (_parse_reactive_form_inputs, _compute_freeze_decisions)
contain zero st.* calls so they can be imported and called directly.
"""

from __future__ import annotations

import json

from ui.components import _compute_freeze_decisions, _parse_reactive_form_inputs

# ── _parse_reactive_form_inputs ───────────────────────────────────────────────


def test_parse_intent_valid() -> None:
    parsed, err = _parse_reactive_form_inputs("intent", "optimize", None)
    assert err is None
    assert parsed == "optimize"


def test_parse_intent_invalid_returns_error() -> None:
    parsed, err = _parse_reactive_form_inputs("intent", "fly_to_moon", "optimize")
    assert err is not None
    assert "inválido" in err.lower() or "debe ser" in err.lower()
    # On failure, current_value is returned unchanged
    assert parsed == "optimize"


def test_parse_metrics_valid_json() -> None:
    raw = json.dumps(
        [{"id": "revenue", "name": "Revenue", "source_turn": 1, "confidence": 1.0}]
    )
    parsed, err = _parse_reactive_form_inputs("metrics", raw, [])
    assert err is None
    assert isinstance(parsed, list)
    assert parsed[0]["id"] == "revenue"


def test_parse_metrics_invalid_json_returns_error() -> None:
    raw = "[{broken"
    parsed, err = _parse_reactive_form_inputs("metrics", raw, [])
    assert err is not None
    assert "json" in err.lower() or "inválido" in err.lower()


def test_parse_active_simulation_run_empty_string_returns_none() -> None:
    parsed, err = _parse_reactive_form_inputs("active_simulation_run", "   ", None)
    assert err is None
    assert parsed is None


def test_parse_active_simulation_run_nonempty_passthrough() -> None:
    parsed, err = _parse_reactive_form_inputs(
        "active_simulation_run", "abc-123-def", None
    )
    assert err is None
    assert parsed == "abc-123-def"


# ── _compute_freeze_decisions ─────────────────────────────────────────────────


def test_freeze_new_slot() -> None:
    freeze, unfreeze = _compute_freeze_decisions(
        "intent", was_frozen=False, is_now_checked=True
    )
    assert freeze == ["intent"]
    assert unfreeze == []


def test_unfreeze_previously_frozen_slot() -> None:
    freeze, unfreeze = _compute_freeze_decisions(
        "active_simulation_run", was_frozen=True, is_now_checked=False
    )
    assert freeze == []
    assert unfreeze == ["active_simulation_run"]


def test_no_change_when_frozen_stays_frozen() -> None:
    freeze, unfreeze = _compute_freeze_decisions(
        "metrics", was_frozen=True, is_now_checked=True
    )
    assert freeze == []
    assert unfreeze == []


def test_no_change_when_unfrozen_stays_unfrozen() -> None:
    freeze, unfreeze = _compute_freeze_decisions(
        "active_optimization_run", was_frozen=False, is_now_checked=False
    )
    assert freeze == []
    assert unfreeze == []
