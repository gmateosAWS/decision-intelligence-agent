"""
memory/proactive_confirmation.py
─────────────────────────────────
Structural signals computing whether the planner's interpretation merits
proactive user confirmation BEFORE executing an expensive tool (item 5.13).

Design notes:
- We do NOT ask the LLM to self-report confidence (LLM self-confidence is
  biased toward high values and unreliable).
- We do NOT hardcode tool names. Tools declare their cost class in
  agents/tools_registry.py; the gate only triggers for "expensive" tools.
  This keeps the gate domain-agnostic and forward-compatible with item 4.3
  (external skills): new skills that declare themselves as "expensive" at
  registration time automatically participate in the confirmation gate.
- Cross-layer import (memory/ → agents/): intentional by spec. The
  tools_registry is a system-level classification, not a domain concept, so
  it lives in agents/ where the tool implementations are. If item 4.3
  introduces a dedicated SkillRegistry in core/, this import will migrate
  there. The current boundary lint does not block this direction.
"""

from __future__ import annotations

import os
from typing import Any


def get_active_signals() -> set[str]:
    """Read active signals from STATE_CONFIRMATION_SIGNALS env var.

    Default: both signals active. Set to empty string to disable all signals
    (e.g. in automated testing environments that should not pause for
    confirmation).
    """
    raw = os.getenv("STATE_CONFIRMATION_SIGNALS", "first_turn,thin_context")
    return {s.strip() for s in raw.split(",") if s.strip()}


def should_request_confirmation(
    tool: str,
    query: str,
    params: dict[str, Any],
    is_first_session_turn: bool,
) -> tuple[bool, list[str]]:
    """Return (should_pause, triggered_signals).

    Only triggers for tools classified as "expensive" in the tools registry.
    This avoids hardcoding tool names — when new skills are registered
    (item 4.3) they declare their cost class and the gate adapts automatically.

    ``is_first_session_turn`` must be computed from the LangGraph checkpoint
    (graph.get_state() before invoke) rather than from state["history"].
    History is never written when the graph ends early via gate → END, so
    state["history"] stays [] on subsequent turns — causing false positives.

    Signal descriptions:
    - first_turn: this is the first turn of the LangGraph thread (no prior
      checkpoint) and the tool is expensive.  The system has no conversational
      context to resolve ambiguity, so the initial interpretation is most
      likely to need correction.
    - thin_context: query is very short (< 8 words) AND no params were
      extracted by the planner. Without either a long query or explicit params,
      the planner's slot-filling has minimal evidence to work from.
    """
    # Import deferred to avoid circular import at module load time.
    from agents.tools_registry import get_tool_cost_class  # noqa: PLC0415

    if get_tool_cost_class(tool) != "expensive":
        return False, []

    active = get_active_signals()
    triggered: list[str] = []

    if "first_turn" in active and is_first_session_turn:
        triggered.append("first_turn")

    if "thin_context" in active:
        word_count = len(query.split())
        if word_count < 8 and not params:
            triggered.append("thin_context")

    return (len(triggered) > 0, triggered)
