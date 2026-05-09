"""
tests/spec/test_autonomy.py
----------------------------
Unit tests for spec/autonomy.py.  No database, no LLM required.
"""

from __future__ import annotations

from spec.autonomy import AutonomyLevel, AutonomyPolicy, ToolAutonomyPolicy


def test_autonomy_level_enum_values() -> None:
    assert AutonomyLevel.AUTO.value == "auto"
    assert AutonomyLevel.HUMAN_CONFIRMS.value == "human_confirms"
    assert AutonomyLevel.HUMAN_APPROVES.value == "human_approves"


def test_policy_default_is_auto() -> None:
    policy = AutonomyPolicy()
    assert policy.default_level == AutonomyLevel.AUTO
    assert policy.tools == []


def test_policy_get_level_known_tool() -> None:
    policy = AutonomyPolicy(
        tools=[
            ToolAutonomyPolicy(tool="optimization", level=AutonomyLevel.HUMAN_CONFIRMS)
        ]
    )
    assert policy.get_level("optimization") == AutonomyLevel.HUMAN_CONFIRMS


def test_policy_get_level_unknown_tool_falls_back_to_default() -> None:
    policy = AutonomyPolicy(
        tools=[
            ToolAutonomyPolicy(tool="optimization", level=AutonomyLevel.HUMAN_CONFIRMS)
        ]
    )
    assert policy.get_level("knowledge") == AutonomyLevel.AUTO


def test_policy_get_level_custom_default() -> None:
    policy = AutonomyPolicy(default_level=AutonomyLevel.HUMAN_APPROVES)
    assert policy.get_level("unknown_tool") == AutonomyLevel.HUMAN_APPROVES


def test_policy_get_level_human_approves() -> None:
    policy = AutonomyPolicy(
        tools=[
            ToolAutonomyPolicy(tool="simulation", level=AutonomyLevel.HUMAN_APPROVES)
        ]
    )
    assert policy.get_level("simulation") == AutonomyLevel.HUMAN_APPROVES


def test_tool_policy_defaults() -> None:
    tp = ToolAutonomyPolicy(tool="optimization")
    assert tp.level == AutonomyLevel.AUTO
    assert tp.conditions == []
    assert tp.reason == ""


def test_policy_model_validate_from_dict() -> None:
    raw = {
        "default_level": "human_confirms",
        "tools": [{"tool": "optimization", "level": "auto", "reason": "safe"}],
    }
    policy = AutonomyPolicy.model_validate(raw)
    assert policy.default_level == AutonomyLevel.HUMAN_CONFIRMS
    assert policy.get_level("optimization") == AutonomyLevel.AUTO
    assert policy.get_level("simulation") == AutonomyLevel.HUMAN_CONFIRMS
