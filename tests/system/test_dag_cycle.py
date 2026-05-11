"""Unit tests for DAG cycle detection (item 3.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pytest

from system.system_graph import assert_dag_acyclic


@dataclass
class _Rel:
    from_vars: List[str]
    to_var: str


def test_valid_dag_passes() -> None:
    rels = [
        _Rel(["A"], "B"),
        _Rel(["B"], "C"),
        _Rel(["A"], "C"),
    ]
    assert_dag_acyclic(rels)  # must not raise


def test_cycle_detected_raises() -> None:
    rels = [
        _Rel(["A"], "B"),
        _Rel(["B"], "C"),
        _Rel(["C"], "A"),
    ]
    with pytest.raises(ValueError, match="cycle"):
        assert_dag_acyclic(rels)


def test_self_loop_detected() -> None:
    rels = [_Rel(["A"], "A")]
    with pytest.raises(ValueError, match="cycle"):
        assert_dag_acyclic(rels)


def test_error_message_includes_cycle_path() -> None:
    rels = [
        _Rel(["X"], "Y"),
        _Rel(["Y"], "X"),
    ]
    with pytest.raises(ValueError) as exc_info:
        assert_dag_acyclic(rels)
    msg = str(exc_info.value)
    assert "X" in msg or "Y" in msg


def test_empty_graph_passes() -> None:
    assert_dag_acyclic([])


def test_build_graph_does_not_raise_for_current_spec() -> None:
    """Regression: the shipped YAML spec must form an acyclic DAG."""
    from system.system_graph import build_graph

    G = build_graph()
    assert G.number_of_nodes() > 0
