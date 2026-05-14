"""
memory/__init__.py
------------------
Public API for the conversational and analytical memory layer.

Exports
-------
  get_checkpointer      – returns the singleton SqliteSaver instance
  SessionManager        – CRUD + listing of conversation sessions
  register_turn         – convenience wrapper for SessionManager.register_turn
  LocalMemoryService    – concrete MemoryService implementation (item 5.11)
  get_memory_service    – process-level singleton accessor for LocalMemoryService

Boundary rule (item 5.11):
  Code outside memory/ MUST import only from this module or from
  core.protocols.memory. Direct imports from memory.coordinator.* or
  memory.state.* are blocked by scripts/check_memory_boundary.py in CI.
"""

from __future__ import annotations

from .checkpointer import get_checkpointer, register_turn
from .service import LocalMemoryService
from .session_manager import SessionManager

__all__ = [
    "get_checkpointer",
    "register_turn",
    "SessionManager",
    "LocalMemoryService",
    "get_memory_service",
]

_memory_service: LocalMemoryService | None = None


def get_memory_service() -> LocalMemoryService:
    """Return the process-level MemoryService singleton.

    One LocalMemoryService instance per process; sessions are isolated
    inside it via session_id keying in the coordinator cache.
    Fail-open: if the service cannot be created, a fresh one is returned.
    """
    global _memory_service
    if _memory_service is None:
        _memory_service = LocalMemoryService()
    return _memory_service
