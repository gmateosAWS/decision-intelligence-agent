"""
memory/__init__.py
------------------
Public API for the conversational memory layer.

Exports
-------
  get_checkpointer   – returns the singleton SqliteSaver instance
  SessionManager     – CRUD + listing of conversation sessions
  register_turn      – convenience wrapper for SessionManager.register_turn
"""

from .checkpointer import get_checkpointer, register_turn
from .session_manager import SessionManager

__all__ = [
    "get_checkpointer",
    "register_turn",
    "SessionManager",
]
