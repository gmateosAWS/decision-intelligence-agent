"""
evaluation/sinks/jsonl_sink.py
-------------------------------
JsonlSink: appends each run record to a .jsonl file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class JsonlSink:
    """Writes one JSON line per completed run to ``<log_dir>/agent_runs.jsonl``."""

    FILENAME = "agent_runs.jsonl"

    def __init__(self, log_dir: str | Path = "logs") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def finalize_run(self, record: Dict[str, Any]) -> None:
        path = self.log_dir / self.FILENAME
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("JsonlSink: failed to write run record: %s", exc)
