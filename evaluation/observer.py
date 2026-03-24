"""
evaluation/observer.py
----------------------
AgentObserver: structured observability for every agent run.

Architecture decision:
  - Console output  →  standard Python logging (human-readable)
  - Persistent data →  append-only JSONL file (one record per run)
  - LangSmith       →  automatic when LANGCHAIN_TRACING_V2=true is set in .env

Usage (in app.py):
    observer = AgentObserver()
    config   = {"configurable": {"observer": observer}}
    run_id   = observer.start_run(query)
    result   = graph.invoke({"query": query}, config=config)
    observer.end_run()

Usage (in workflow nodes):
    def planner_node(state: AgentState, config=None):
        obs = (config or {}).get("configurable", {}).get("observer")
        t0  = time.time()
        ...
        if obs:
            obs.record_planner(action, reasoning, (time.time()-t0)*1000)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RunRecord:
    """One complete agent run captured as a structured record."""

    run_id: str
    session_id: str
    timestamp: str  # ISO-8601 UTC
    query: str

    # Planner
    action: Optional[str] = None
    reasoning: Optional[str] = None
    planner_latency_ms: Optional[float] = None

    # Tool
    tool_latency_ms: Optional[float] = None
    raw_result_keys: Optional[List[str]] = None
    confidence_score: Optional[float] = None  # derived from tool output

    # Synthesizer
    synthesizer_latency_ms: Optional[float] = None
    answer_length: Optional[int] = None

    # Judge
    judge_latency_ms: Optional[float] = None
    judge_score: Optional[float] = None
    judge_passed: Optional[bool] = None
    judge_revised: Optional[bool] = None
    judge_feedback: Optional[str] = None

    # Overall
    total_latency_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Observer
# ---------------------------------------------------------------------------


class AgentObserver:
    """
    Lightweight observability wrapper for the Decision Intelligence Agent.

    Responsibilities
    ----------------
    1. Console logging  – human-readable INFO lines for interactive sessions.
    2. JSONL persistence – one JSON record per run appended to
       ``logs/agent_runs.jsonl``.  Compatible with any log-analysis tool.
    3. Confidence scoring – derives a simple 0-1 score from tool output
       (Monte Carlo downside risk or optimization margin).
    4. LangSmith bridge – sets the ``run_name`` tag so every LangGraph
       invocation appears named in the LangSmith UI when tracing is enabled.
    """

    JSONL_FILENAME = "agent_runs.jsonl"
    LOG_FILENAME = "agent.log"

    def __init__(self, log_dir: str = "logs") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = uuid.uuid4().hex[:8]
        self._run: Optional[RunRecord] = None
        self._run_start: Optional[float] = None
        self._logger = self._build_logger()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_run(self, query: str) -> str:
        """Open a new run.  Returns the run_id for correlation."""
        run_id = uuid.uuid4().hex[:12]
        self._run_start = time.perf_counter()
        self._run = RunRecord(
            run_id=run_id,
            session_id=self.session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            query=query,
        )
        self._logger.info(
            "▶ RUN START  run_id=%-12s  query=%s",
            run_id,
            self._truncate(query, 70),
        )
        return run_id

    def record_planner(
        self,
        action: str,
        reasoning: str,
        latency_ms: float,
    ) -> None:
        """Record the planner's tool selection."""
        if self._run:
            self._run.action = action
            self._run.reasoning = reasoning
            self._run.planner_latency_ms = latency_ms
        self._logger.info(
            "  PLANNER     action=%-14s  latency=%6.0f ms  reason=%s",
            action,
            latency_ms,
            self._truncate(reasoning, 80),
        )

    def record_tool(
        self,
        tool_name: str,
        result: Any,
        latency_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Record tool execution result and derive a confidence score."""
        if self._run:
            self._run.tool_latency_ms = latency_ms
            if error:
                self._run.success = False
                self._run.error = error
            elif isinstance(result, dict):
                self._run.raw_result_keys = list(result.keys())
                self._run.confidence_score = self._derive_confidence(result)

        status = "ERROR" if error else "OK"
        conf = (
            f"  confidence={self._run.confidence_score:.2f}"
            if (self._run and self._run.confidence_score is not None)
            else ""
        )
        self._logger.info(
            "  TOOL %-14s  status=%-5s  latency=%6.0f ms%s",
            tool_name,
            status,
            latency_ms,
            conf,
        )
        if error:
            self._logger.error("  TOOL ERROR: %s", error)

    def record_synthesizer(self, answer: str, latency_ms: float) -> None:
        """Record the synthesizer's output."""
        if self._run:
            self._run.synthesizer_latency_ms = latency_ms
            self._run.answer_length = len(answer)
        self._logger.info(
            "  SYNTHESIZER                       latency=%6.0f ms  answer_chars=%d",
            latency_ms,
            len(answer),
        )

    def record_judge(
        self,
        score: Optional[float],
        approved: bool,
        feedback: str,
        latency_ms: float,
        revised: bool,
        final_answer: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record online-judge evaluation and optional revision."""
        if self._run:
            self._run.judge_latency_ms = latency_ms
            self._run.judge_score = score
            self._run.judge_passed = approved
            self._run.judge_revised = revised
            self._run.judge_feedback = feedback
            if final_answer is not None:
                self._run.answer_length = len(final_answer)
            if error and self._run.error is None:
                self._run.error = f"Judge error: {error}"

        score_text = f"{score:.2f}" if score is not None else "n/a"
        self._logger.info(
            "  JUDGE       approved=%-5s  revised=%-5s  latency=%6.0f ms  score=%s",
            approved,
            revised,
            latency_ms,
            score_text,
        )
        if feedback:
            self._logger.info("  JUDGE NOTE  %s", self._truncate(feedback, 100))

    def end_run(
        self,
        success: bool = True,
        error: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Close the current run, compute total latency,
        persist the record to JSONL, and return the record dict.
        """
        if not self._run:
            return None

        elapsed_ms = (time.perf_counter() - self._run_start) * 1000
        self._run.total_latency_ms = elapsed_ms
        if not success:
            self._run.success = False
            self._run.error = error

        record = self._sanitize_value(asdict(self._run))
        self._append_jsonl(record)

        icon = "✓" if self._run.success else "✗"
        self._logger.info(
            "◀ RUN END %s  run_id=%-12s  total=%7.0f ms  success=%s",
            icon,
            self._run.run_id,
            elapsed_ms,
            self._run.success,
        )
        self._run = None
        self._run_start = None
        return record

    def cancel_run(self, reason: str = "Cancelled") -> None:
        """Abort the current run without persisting a failed JSONL record."""
        if not self._run:
            return

        elapsed_ms = None
        if self._run_start is not None:
            elapsed_ms = (time.perf_counter() - self._run_start) * 1000

        self._logger.warning(
            "◀ RUN CANCELLED  run_id=%-12s  total=%7s  reason=%s",
            self._run.run_id,
            f"{elapsed_ms:.0f} ms" if elapsed_ms is not None else "n/a",
            reason,
        )
        self._run = None
        self._run_start = None

    # ------------------------------------------------------------------
    # LangSmith helpers
    # ------------------------------------------------------------------

    def langsmith_config(self, extra_tags: Optional[List[str]] = None) -> Dict:
        """
        Build the LangGraph ``config`` dict that enables LangSmith tracing
        with a meaningful run name and tags.

        Usage:
            config = observer.langsmith_config()
            config["configurable"]["observer"] = observer
            graph.invoke({"query": q}, config=config)
        """
        tags = ["decision-intelligence-agent", f"session:{self.session_id}"]
        if extra_tags:
            tags.extend(extra_tags)
        return {
            "run_name": "decision-intelligence-agent",
            "tags": tags,
            "metadata": {"session_id": self.session_id},
            "configurable": {},
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_logger(self) -> logging.Logger:
        name = f"dia.observer.{self.session_id}"
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        # Console – concise, human-readable
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(message)s",
                datefmt="%H:%M:%S",
            )
        )

        # File – verbose, for post-mortem debugging
        fh = logging.FileHandler(
            self.log_dir / self.LOG_FILENAME, mode="a", encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

        logger.addHandler(ch)
        logger.addHandler(fh)
        return logger

    def _append_jsonl(self, record: Dict) -> None:
        path = self.log_dir / self.JSONL_FILENAME
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(self._sanitize_value(record), ensure_ascii=False) + "\n")

    @staticmethod
    def _sanitize_value(value: Any) -> Any:
        """Convert NumPy scalars/arrays and other exotic objects to plain Python."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {
                str(key): AgentObserver._sanitize_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [AgentObserver._sanitize_value(item) for item in value]

        item_method = getattr(value, "item", None)
        if callable(item_method):
            try:
                return AgentObserver._sanitize_value(item_method())
            except Exception:  # noqa: BLE001
                pass

        tolist_method = getattr(value, "tolist", None)
        if callable(tolist_method):
            try:
                return AgentObserver._sanitize_value(tolist_method())
            except Exception:  # noqa: BLE001
                pass

        return str(value)

    @staticmethod
    def _derive_confidence(result: Dict) -> Optional[float]:
        """
        Heuristic confidence score [0, 1] derived from tool output.

        - Simulation/optimization: 1 - downside_risk_pct / 100
        - Knowledge: fixed 0.9 (RAG match assumed relevant)
        - Unknown: None
        """
        if "downside_risk_pct" in result:
            risk = float(result["downside_risk_pct"])
            return round(max(0.0, 1.0 - risk / 100.0), 3)
        if "expected_profit" in result:
            # Optimization result – confidence based on profit being positive
            profit = float(result.get("expected_profit", 0))
            return 1.0 if profit > 0 else 0.3
        if "answer" in result or "documents" in result:
            return 0.9
        return None

    @staticmethod
    def _truncate(text: str, n: int) -> str:
        return text[:n] + "…" if len(text) > n else text
