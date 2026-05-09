"""
evaluation/
-----------
Observability and evaluation layer for the Decision Intelligence Agent.

Modules:
  observer    – AgentObserver: orchestrates run recording via pluggable RunSinks
  confidence  – ConfidenceScorer: derives 0-1 confidence from tool output
  sinks/      – RunSink Protocol + JsonlSink + PostgresSink + LangSmithBridge
  metrics     – load_runs / compute_metrics helpers
  dashboard   – CLI report + self-contained HTML dashboard generator
"""

from .metrics import compute_metrics, load_runs
from .observer import AgentObserver

__all__ = [
    "AgentObserver",
    "load_runs",
    "compute_metrics",
]
