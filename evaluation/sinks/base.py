"""
evaluation/sinks/base.py
------------------------
RunSink Protocol — the interface every sink must implement.

Design (ObjectBus-ready, item 1.6):
  Each sink is an independent consumer of run records. The AgentObserver
  (orchestrator) accumulates a RunRecord and calls finalize_run() once per
  run. When item 1.6 (ObjectBus) lands, each sink becomes an independent
  bus subscriber — the same interface works without change.
"""

from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class RunSink(Protocol):
    """Consumer interface for completed agent run records."""

    def finalize_run(self, record: Dict[str, Any]) -> None:
        """
        Persist or forward a completed run record.

        Called once per run, after all record_* events have been accumulated.
        ``record`` is a plain-Python dict (output of dataclasses.asdict + sanitize).
        Implementations must be fail-open: log on error, never raise.
        """
        ...
