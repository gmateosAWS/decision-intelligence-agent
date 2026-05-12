"""
evaluation/observer.py
----------------------
AgentObserver: structured observability for every agent run.

Architecture decision:
  - Console output  →  standard Python logging (human-readable)
  - Persistent data →  pluggable RunSink list (JsonlSink always;
                        PostgresSink when DATABASE_URL set)
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

Custom sinks (ObjectBus-ready, item 1.6):
    observer = AgentObserver(sinks=[JsonlSink("logs"), MyCustomSink()])
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from evaluation.confidence import ConfidenceScorer
except Exception:  # noqa: BLE001
    ConfidenceScorer = None  # type: ignore[assignment,misc]

try:
    from evaluation.sinks.base import RunSink
except Exception:  # noqa: BLE001
    RunSink = object  # type: ignore[assignment,misc]

try:
    from evaluation.sinks.jsonl_sink import JsonlSink
except Exception:  # noqa: BLE001
    JsonlSink = None  # type: ignore[assignment,misc]

try:
    from evaluation.sinks.langsmith_sink import LangSmithBridge
except Exception:  # noqa: BLE001
    LangSmithBridge = None  # type: ignore[assignment,misc]

try:
    from evaluation.sinks.postgres_sink import PostgresSink
except Exception:  # noqa: BLE001
    PostgresSink = None  # type: ignore[assignment,misc]

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
    planner_model: Optional[str] = None

    # Tool
    tool_latency_ms: Optional[float] = None
    raw_result_keys: Optional[List[str]] = None
    raw_result: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None

    # Synthesizer
    synthesizer_latency_ms: Optional[float] = None
    answer_length: Optional[int] = None
    synthesizer_model: Optional[str] = None

    # Judge
    judge_latency_ms: Optional[float] = None
    judge_score: Optional[float] = None
    judge_passed: Optional[bool] = None
    judge_revised: Optional[bool] = None
    judge_feedback: Optional[str] = None
    judge_model: Optional[str] = None

    # Overall
    total_latency_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None

    # Spec traceability
    spec_id: Optional[str] = None
    spec_version: Optional[str] = None

    # Prompt Registry traceability (item 10.1)
    planner_prompt_version: Optional[str] = None
    synthesizer_prompt_version: Optional[str] = None
    judge_prompt_version: Optional[str] = None

    # Cost tracking (item 8.7.a+b)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    llm_calls_count: int = 0
    budget_exceeded: bool = False
    budget_exceeded_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Observer
# ---------------------------------------------------------------------------


class AgentObserver:
    """
    Lightweight observability wrapper for the Decision Intelligence Agent.

    Responsibilities
    ----------------
    1. Console logging  – human-readable INFO lines for interactive sessions.
    2. RunRecord accumulation – gathers per-stage fields into a single record.
    3. Sink dispatch – calls each RunSink.finalize_run() at end_run().
    4. LangSmith bridge – sets the ``run_name`` tag so every LangGraph
       invocation appears named in the LangSmith UI when tracing is enabled.

    Persistence is handled by the injected sinks (default: JsonlSink +
    PostgresSink when DATABASE_URL set + LangSmithBridge).
    """

    JSONL_FILENAME = "agent_runs.jsonl"
    LOG_FILENAME = "agent.log"

    def __init__(
        self,
        sinks: Optional[List[RunSink]] = None,
        log_dir: str = "logs",
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = uuid.uuid4().hex[:8]
        self._run: Optional[RunRecord] = None
        self._run_start: Optional[float] = None
        self._scorer = ConfidenceScorer() if ConfidenceScorer is not None else None
        self._sinks: List[RunSink] = (
            sinks if sinks is not None else self._default_sinks()
        )
        self._logger = self._build_logger()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_session_id(self, session_id: str) -> None:
        """Override the auto-generated session_id with the caller's session UUID."""
        self.session_id = session_id
        if self._run:
            self._run.session_id = session_id

    def set_spec(self, spec_id: Optional[str], spec_version: Optional[str]) -> None:
        """Record which spec version is active for the current run."""
        if self._run:
            self._run.spec_id = spec_id
            self._run.spec_version = spec_version

    def set_raw_result(self, raw_result: Dict[str, Any]) -> None:
        """Attach the tool's full output dict to the current run record."""
        if self._run:
            self._run.raw_result = raw_result

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
        model: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> None:
        """Record the planner's tool selection."""
        if self._run:
            self._run.action = action
            self._run.reasoning = reasoning
            self._run.planner_latency_ms = latency_ms
            self._run.planner_model = model
            self._run.planner_prompt_version = prompt_version
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
                if self._scorer is not None:
                    self._run.confidence_score = self._scorer.compute_from_result(
                        result
                    )

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

    def record_synthesizer(
        self,
        answer: str,
        latency_ms: float,
        model: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> None:
        """Record the synthesizer's output."""
        if self._run:
            self._run.synthesizer_latency_ms = latency_ms
            self._run.answer_length = len(answer)
            self._run.synthesizer_model = model
            self._run.synthesizer_prompt_version = prompt_version
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
        model: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> None:
        """Record online-judge evaluation and optional revision."""
        if self._run:
            self._run.judge_latency_ms = latency_ms
            self._run.judge_score = score
            self._run.judge_passed = approved
            self._run.judge_revised = revised
            self._run.judge_feedback = feedback
            self._run.judge_model = model
            self._run.judge_prompt_version = prompt_version
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

    def record_cost(
        self,
        total_input_tokens: int,
        total_output_tokens: int,
        total_cost_usd: float,
        llm_calls_count: int,
        budget_exceeded: bool = False,
        budget_exceeded_reason: Optional[str] = None,
    ) -> None:
        """Record aggregated LLM cost for the current run (item 8.7.a+b)."""
        self._logger.warning(
            "[COST_DEBUG] record_cost: input=%d output=%d cost_usd=%.6f calls=%d",
            total_input_tokens,
            total_output_tokens,
            total_cost_usd,
            llm_calls_count,
        )
        if self._run:
            self._run.total_input_tokens = total_input_tokens
            self._run.total_output_tokens = total_output_tokens
            self._run.total_cost_usd = total_cost_usd
            self._run.llm_calls_count = llm_calls_count
            self._run.budget_exceeded = budget_exceeded
            self._run.budget_exceeded_reason = budget_exceeded_reason

    def end_run(
        self,
        success: bool = True,
        error: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Close the current run, compute total latency,
        dispatch to all sinks, and return the record dict.
        """
        if not self._run:
            return None

        elapsed_ms = (time.perf_counter() - self._run_start) * 1000
        self._run.total_latency_ms = elapsed_ms
        if not success:
            self._run.success = False
            self._run.error = error

        record = self._sanitize_value(asdict(self._run))
        for sink in self._sinks:
            sink.finalize_run(record)

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
        return record  # type: ignore[no-any-return]

    def cancel_run(self, reason: str = "Cancelled") -> None:
        """Abort the current run without persisting a failed record."""
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

    def _default_sinks(self) -> List[Any]:
        sinks: List[Any] = []
        if JsonlSink is not None:
            sinks.append(JsonlSink(self.log_dir))
        if os.getenv("DATABASE_URL", "") and PostgresSink is not None:
            sinks.append(PostgresSink())
        if LangSmithBridge is not None:
            sinks.append(LangSmithBridge())
        return sinks

    def _build_logger(self) -> logging.Logger:
        name = f"dia.observer.{self.session_id}"
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(message)s",
                datefmt="%H:%M:%S",
            )
        )

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
    def _truncate(text: str, n: int) -> str:
        return text[:n] + "…" if len(text) > n else text
