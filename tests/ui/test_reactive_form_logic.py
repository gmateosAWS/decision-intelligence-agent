"""
tests/ui/test_reactive_form_logic.py
--------------------------------------
Unit tests for the pure helper functions in ui/components.py that back
the reactive correction form (item 5.13.c).

All tests are offline — no DB, no LLM, no Streamlit runtime.
The helpers under test (_parse_reactive_form_inputs, _compute_freeze_decisions,
_normalize_metrics_list, _assemble_metrics_from_rows, _assemble_scenarios_from_rows)
contain zero st.* calls so they can be imported and called directly.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from ui.components import (
    _assemble_metrics_from_rows,
    _assemble_scenarios_from_rows,
    _compute_freeze_decisions,
    _normalize_metrics_list,
    _parse_reactive_form_inputs,
)

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


# ── freeze → unfreeze round-trip ──────────────────────────────────────────────


def test_freeze_then_unfreeze_round_trip() -> None:
    freeze, unfreeze = _compute_freeze_decisions(
        "metrics", was_frozen=False, is_now_checked=True
    )
    assert freeze == ["metrics"]
    assert unfreeze == []
    # Now unfreeze it
    freeze2, unfreeze2 = _compute_freeze_decisions(
        "metrics", was_frozen=True, is_now_checked=False
    )
    assert freeze2 == []
    assert unfreeze2 == ["metrics"]


# ── _normalize_metrics_list ───────────────────────────────────────────────────


def test_normalize_metrics_empty() -> None:
    assert _normalize_metrics_list(None) == []
    assert _normalize_metrics_list([]) == []


def test_normalize_metrics_plain_dicts() -> None:
    inp = [{"id": "profit", "name": "Profit", "source_turn": 1, "confidence": 0.9}]
    out = _normalize_metrics_list(inp)
    assert len(out) == 1
    assert out[0]["id"] == "profit"
    assert out[0]["confidence"] == 0.9


def test_normalize_metrics_pydantic_model() -> None:
    mock_model = MagicMock()
    mock_model.model_dump.return_value = {
        "id": "revenue",
        "name": "Revenue",
        "source_turn": 2,
        "confidence": 1.0,
    }
    out = _normalize_metrics_list([mock_model])
    assert len(out) == 1
    assert out[0]["id"] == "revenue"
    mock_model.model_dump.assert_called_once()


def test_normalize_metrics_scalar_fallback() -> None:
    out = _normalize_metrics_list(["some_metric_string"])
    assert len(out) == 1
    assert out[0]["id"] == "some_metric_string"
    assert out[0]["name"] == "some_metric_string"


def test_normalize_metrics_multiple_mixed() -> None:
    pydantic_mock = MagicMock()
    pydantic_mock.model_dump.return_value = {
        "id": "a",
        "name": "A",
        "source_turn": 0,
        "confidence": 1.0,
    }
    inp: Any = [
        pydantic_mock,
        {"id": "b", "name": "B", "source_turn": 1, "confidence": 0.8},
    ]
    out = _normalize_metrics_list(inp)
    assert len(out) == 2
    assert out[0]["id"] == "a"
    assert out[1]["id"] == "b"


# ── _assemble_metrics_from_rows ───────────────────────────────────────────────


def test_assemble_metrics_filters_empty_id() -> None:
    rows = [
        {"id": "", "name": "Empty", "confidence": 1.0, "source_turn": 0},
        {"id": "revenue", "name": "Revenue", "confidence": 0.9, "source_turn": 1},
    ]
    out = _assemble_metrics_from_rows(rows)
    assert len(out) == 1
    assert out[0]["id"] == "revenue"


def test_assemble_metrics_clamps_confidence() -> None:
    rows = [{"id": "x", "name": "X", "confidence": 1.5, "source_turn": 0}]
    out = _assemble_metrics_from_rows(rows)
    assert out[0]["confidence"] == 1.0

    rows2 = [{"id": "y", "name": "Y", "confidence": -0.1, "source_turn": 0}]
    out2 = _assemble_metrics_from_rows(rows2)
    assert out2[0]["confidence"] == 0.0


def test_assemble_metrics_name_falls_back_to_id() -> None:
    rows = [{"id": "profit", "name": "", "confidence": 1.0, "source_turn": 0}]
    out = _assemble_metrics_from_rows(rows)
    assert out[0]["name"] == "profit"


def test_assemble_metrics_empty_input() -> None:
    assert _assemble_metrics_from_rows([]) == []


# ── _assemble_scenarios_from_rows ─────────────────────────────────────────────


def test_assemble_scenarios_filters_blanks() -> None:
    rows = ["scenario A", "  ", "", "scenario B"]
    out = _assemble_scenarios_from_rows(rows)
    assert out == ["scenario A", "scenario B"]


def test_assemble_scenarios_strips_whitespace() -> None:
    rows = ["  padded  ", "clean"]
    out = _assemble_scenarios_from_rows(rows)
    assert out == ["padded", "clean"]


def test_assemble_scenarios_empty() -> None:
    assert _assemble_scenarios_from_rows([]) == []
    assert _assemble_scenarios_from_rows(["", "  "]) == []
