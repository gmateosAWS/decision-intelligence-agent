"""
evaluation/sinks/langsmith_sink.py
------------------------------------
LangSmithBridge: forwards run records to LangSmith as feedback entries.

TODO(product): Full implementation requires langsmith SDK ≥ 0.1.
  When item 10.5 (lineage) or 10.10 (eval framework) lands, replace this
  stub with real client.create_feedback() calls keyed on the LangSmith
  run_id stored in record["langsmith_run_id"] (to be added by orchestrator).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


class LangSmithBridge:
    """Stub sink — active only when LANGCHAIN_TRACING_V2=true."""

    def finalize_run(self, record: Dict[str, Any]) -> None:
        if os.getenv("LANGCHAIN_TRACING_V2", "").lower() != "true":
            return
        # TODO(product): call langsmith client to attach structured feedback
        # to the run identified by record.get("langsmith_run_id").
        logger.debug(
            "LangSmithBridge: tracing enabled but feedback upload not yet implemented "
            "(run_id=%s)",
            record.get("run_id"),
        )
