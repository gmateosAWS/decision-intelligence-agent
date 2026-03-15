"""
evaluation/
-----------
Observability and evaluation layer for the Decision Intelligence Agent.

Modules:
  observer   – AgentObserver: structured logging + per-run JSONL records
  metrics    – load_runs / compute_metrics helpers
  dashboard  – CLI report + self-contained HTML dashboard generator
"""

from .metrics import compute_metrics, load_runs
from .observer import AgentObserver

__all__ = ["AgentObserver", "load_runs", "compute_metrics"]
