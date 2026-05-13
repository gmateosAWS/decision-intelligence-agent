"""Map planner ToolSelection.tool values to Intent enum."""

from memory.state.types import Intent

_TOOL_TO_INTENT: dict[str, Intent] = {
    "optimization": Intent.OPTIMIZE,
    "simulation": Intent.SIMULATE,
    "knowledge": Intent.EXPLAIN,
}


def map_tool_to_intent(tool: str) -> Intent:
    """Return the Intent that corresponds to a planner tool name.

    Falls back to EXPLORE for unknown tools so the coordinator never
    propagates None when the planner returns an unexpected tool value.
    """
    return _TOOL_TO_INTENT.get(tool, Intent.EXPLORE)
