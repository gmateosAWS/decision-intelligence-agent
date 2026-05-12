"""Per-run budget enforcement for LLM calls (item 8.7.b).

RunBudget  — immutable limits read from env vars.
BudgetTracker — mutable accumulator; check() returns None or a reason string.
BudgetExceededError — raised by invoke_with_fallback when a limit is hit.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class RunBudget:
    max_llm_calls: int = 0  # 0 = no limit
    max_wallclock_s: float = 0.0  # 0 = no limit
    max_cost_usd: float = 0.0  # 0 = no limit
    max_tokens: int = 0  # 0 = no limit

    @classmethod
    def from_env(cls) -> "RunBudget":
        def _int(key: str) -> int:
            v = os.environ.get(key, "0")
            try:
                return max(0, int(v))
            except ValueError:
                return 0

        def _float(key: str) -> float:
            v = os.environ.get(key, "0")
            try:
                return max(0.0, float(v))
            except ValueError:
                return 0.0

        return cls(
            max_llm_calls=_int("RUN_MAX_LLM_CALLS"),
            max_wallclock_s=_float("RUN_MAX_WALLCLOCK_S"),
            max_cost_usd=_float("RUN_MAX_COST_USD"),
            max_tokens=_int("RUN_MAX_TOKENS"),
        )


class BudgetExceededError(RuntimeError):
    def __init__(self, reason: str, tracker: "BudgetTracker") -> None:
        super().__init__(reason)
        self.reason = reason
        self.tracker = tracker


@dataclass
class BudgetTracker:
    budget: RunBudget
    _start_ts: float = field(default_factory=time.monotonic, init=False)
    _llm_calls: int = field(default=0, init=False)
    _total_input_tokens: int = field(default=0, init=False)
    _total_output_tokens: int = field(default=0, init=False)
    _total_cost_usd: float = field(default=0.0, init=False)

    # ── read-only properties ────────────────────────────────────────────────

    @property
    def llm_calls(self) -> int:
        return self._llm_calls

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._total_output_tokens

    @property
    def total_tokens(self) -> int:
        return self._total_input_tokens + self._total_output_tokens

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost_usd

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self._start_ts

    # ── mutation ────────────────────────────────────────────────────────────

    def record_call(
        self,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        self._llm_calls += 1
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_cost_usd += cost_usd

    # ── enforcement ────────────────────────────────────────────────────────

    def check(self) -> Optional[str]:
        """Return an exceeded-reason string, or None if within limits."""
        b = self.budget
        if b.max_llm_calls and self._llm_calls >= b.max_llm_calls:
            return f"LLM call limit reached ({self._llm_calls}/{b.max_llm_calls})"
        if b.max_wallclock_s and self.elapsed_s >= b.max_wallclock_s:
            return (
                f"Wallclock limit reached ({self.elapsed_s:.1f}s/{b.max_wallclock_s}s)"
            )
        if b.max_cost_usd and self._total_cost_usd >= b.max_cost_usd:
            return f"Cost limit reached (${self._total_cost_usd:.4f}/${b.max_cost_usd})"
        if b.max_tokens and self.total_tokens >= b.max_tokens:
            return f"Token limit reached ({self.total_tokens}/{b.max_tokens})"
        return None

    def raise_if_exceeded(self) -> None:
        reason = self.check()
        if reason:
            raise BudgetExceededError(reason, self)
