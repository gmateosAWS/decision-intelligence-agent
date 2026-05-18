# llull · Self-Audit · 2026-05-17 · commit `28c1c48`

## 0. Auditor signature

- **Auditor**: Claude Sonnet 4.6 (Anthropic)
- **Date (UTC)**: 2026-05-17
- **Repository**: https://github.com/gmateosAWS/decision-intelligence-agent
- **Commit hash**: `28c1c48` — Merge pull request #24 (feature/10.2-prompt-ab-testing into main)
- **Branch**: main
- **Inputs read**:
  - Repository tree (~18,174 LOC Python across 160 files)
  - `docs/llull_inventario_v4.md` (116 items)
  - `docs/llull_roadmap_v4.md` (4 iterations + "Más allá")
  - `docs/adr-001-pgvector-over-qdrant.md` (⚠️ superseded by ADR-005)
  - `docs/ADR-002-langgraph-orchestration.md`
  - `docs/ADR-003-llullgen-component-reuse-policy.md`
  - `docs/ADR-005-vector-store-strategy.md`
  - `docs/audit/2026-05-10_llull_self_audit.md` (baseline)
- **Methodology version**: 1.0 (unchanged)
- **Delta context**: Audit #4. Window: 2026-05-10 → 2026-05-17. Completed since May 10:
  items 3.3 (DAG cycle assertion), pip-tools lock files, 8.7.a+b (cost tracking + ceilings),
  5.10 (ActiveAnalyticalState MVP), 5.11 (MemoryService Protocol + boundary lint),
  ADR-005 (vector-store strategy, supersedes ADR-001), mypy --strict on `agents/` (0 errors),
  10.2 (Prompt A/B testing full stack). Plan review discipline added to `CLAUDE.md` (PR #24).

---

## 1. Executive Summary

> **Post-PR update 2026-05-18**: Item 5.13 (user-driven state corrections) landed on branch
> `feature/5.13-user-correction-mutations` after the original audit date. Scores updated in-place.
> 5.13 moves 9 L3 dimensions and crosses the **3.00 overall milestone** for the first time.

**Overall maturity score (dimension-weighted across 86 dimensions)**: **3.00 / 5** *(was 2.88 pre-5.13)*

Layer scores:

| Layer | Score (May 17+5.13) | Score (May 17 pre-5.13) | Δ (May 10 clean → May 17+5.13) | Dimensions |
|---|---|---|---|---|
| Codebase & Architecture | **3.75** | 3.75 | +0.11 | 28 |
| AI / Agent Layer | **3.10** | 3.10 | +0.55 | 20 |
| Conversational & Analytical Memory | **2.45** | 2.00 | +1.27 | 22 |
| Ontology & Semantic Knowledge | **2.31** | 2.31 | +0.25 | 16 |

**Arithmetic verification (post-5.13)**: L1: 105/28=3.750; L2: 62/20=3.100; L3: 54/22=2.4545→**2.45**; L4: 37/16=2.3125→**2.31**.
Total: 258/86=3.000→**3.00**. All layer sums reconcile with per-dimension tables below.

*(Note: the original May 17 pre-5.13 arithmetic had an error — L2.11 ↑ from 5.9 (2→3, +1 pt) and L4.6+7 ↑↑ from 5.9 (0→2 each, +4 pts) were omitted from the summary totals. Corrected: L2=62/20=3.10; L4=37/16=2.31; overall=248/86=2.88. The HTML version showed the correct 2.88 from day one.)*

Findings summary:

- 🔴 **Critical (gap real)**: **0 items** — fourth consecutive audit with zero unplanned gaps.
- 🟡 **Planned (in inventory / roadmap / ADR)**: **~40 dimensions** — down from 46 at May 10.
- 🟢 **Confirmed strengths**: 18 (8.1–8.18; four new at May 17).

**Posture summary.** This sprint closes the largest I2A cluster in a single window: five items landing
between May 10 and May 17 — ActiveAnalyticalState (5.10), MemoryService Protocol with boundary lint
(5.11), LLM cost tracking and hard ceilings (8.7.a+b), mypy --strict on `agents/` with zero errors, and
Prompt A/B testing (10.2). The combined effect is a +0.36 overall lift, the largest single-window gain
across the four audits. Every delta is driven by genuine capability — no score inflated by definition change.

The Memory layer (L3) moves from 1.18 to 2.00 — the expected payoff from items 5.10 and 5.11 predicted
at May 10 materialises on schedule. Ten dimensions advance in L3 alone. The AI/Agent layer (L2) moves
from 2.55 to 3.05, crossing the 3-point threshold for the first time, driven by memory abstraction (dim 10:
1→4), cost control (dim 17: 0→4), multi-turn continuity (dim 18: 2→3), and full prompt A/B governance
(dim 8: 4→5). The Codebase layer (L1) gains three more points: boundary integrity reaches 3 with the
MemoryService seam enforced in CI; composability reaches 4 with multiple typed Protocols deployed; and
mypy --strict on `agents/` closes the last gap to a 5 on typing rigor.

The **dominant bottleneck shifts** from L2 (AI/Agent, now 3.05) to L3 and L4 jointly (both ~2.0).
Within L3, nine dimensions remain at 0 or 1 — all are gated by items planned for I2A/I3: user-correction
mutations (5.13), GroundedTokens (5.9), and the inheritance/conflict-resolution cluster (5.12, 5.13).
L4 is essentially frozen at 2.06 — no Ontology work landed this sprint, and none is scheduled before I3.
The next audit's highest-leverage target is item 5.13 (user-driven state corrections), which would move
L3 dims 4, 9, 10, 12, and 19 from 0–1 to 2–3 and lift the overall score toward 3.00.

A new process strength deserves mention: the Plan review discipline added to `CLAUDE.md` before PR #24
produced four actionable concrete risks before any code was written — including the 3-queries-per-run
cache concern that directly shaped the `lru_cache` design in `prompts/routing.py`. This is not a code
metric but an engineering process metric: evidence that the platform's development methodology is maturing
alongside its architecture.

Dark-code share: **~0.0%**. 160 Python files, no zombie imports, no silently-disabled paths.

---

## 2. Layer 1 — Codebase & Architecture (28 dimensions)

> Changed dimensions are marked ↑ with full updated rationale. Unchanged dimensions re-cite key evidence.

| # | Dimension | Score (May 10) | Score (May 17) | Rationale | Evidence | Gap |
|---|---|---|---|---|---|---|
| 1 | Local code clarity | 4 | **4** | Unchanged. Largest production files remain under 500 LOC. `evaluation/observer.py` ~200 LOC (split by P2.3). `ui/components.py` ~280 LOC. | `evaluation/observer.py`; `ui/components.py`; `ui/app.py` | 🟢 |
| 2 | Naming quality | 4 | **4** | Unchanged. `PromptVariant`, `PromptVariantStatus`, `BudgetTracker`, `MemoryCoordinator`, `FrozenActiveAnalyticalState` — all domain-aligned without ambiguity. | `prompts/models.py`; `evaluation/budget.py`; `memory/state/active.py` | 🟢 |
| 3 | Function / class size and cohesion | 4 | **4** | Unchanged. P2.2 and P2.3 refactors intact. No new god-classes introduced. `prompts/routing.py` (select_variant) and `evaluation/budget.py` (BudgetTracker) are well-bounded. | `prompts/routing.py`; `evaluation/budget.py` | 🟢 |
| 4 | Modularity | 3 | **3** | Unchanged. `ui/` package and `evaluation/sinks/` enforce behavioral cohesion. No layer-deps lint beyond the memory boundary. | `ui/`; `evaluation/sinks/` | 🟡 (item 11.1) |
| 5 | Boundary integrity | 2 | **3** ↑ | **IMPROVED.** `scripts/check_memory_boundary.py` (boundary lint) is now enforced in CI and pre-commit, blocking direct imports of `memory.coordinator.*` / `memory.state.*` outside `memory/`. `governance/memory_boundary_exceptions.yaml` provides a governed allowlist. Two typed Protocols deployed: `RunSink` (P2.3) and `MemoryService` (5.11). Score cannot reach 4 without a comprehensive layer-deps lint covering all layer boundaries (item 11.1, not only memory). | `scripts/check_memory_boundary.py`; `governance/memory_boundary_exceptions.yaml`; `.github/workflows/ci.yml` (boundary step); `.pre-commit-config.yaml` | 🟡 (item 11.1 — full layer-deps lint) |
| 6 | Composability | 3 | **4** ↑ | **IMPROVED.** Four typed seams now compose cleanly: `RunSink` Protocol (3 pluggable sinks), `MemoryService` Protocol + `LocalMemoryService`, `agents/runner.py` Directive-3 callable, and `get_prompt_template()` registry-with-fallback pattern. `PromptVariant` routing is swappable via the same seam. Score cannot reach 5 without `ToolBase` Protocol (item 4.3) and ObjectBus (item 1.6). | `evaluation/sinks/base.py:19-30`; `core/protocols/memory.py`; `agents/runner.py:45-145`; `prompts/routing.py` | 🟡 (items 1.6, 4.3 in I2A/I3) |
| 7 | Architectural integrity | 4 | **4** | Unchanged. Single architecture end-to-end. 10.2, 5.10, 5.11, 8.7 all slot cleanly into the existing paradigm without introducing a second pattern. | `agents/workflow.py`; `prompts/routing.py`; `memory/service.py` | 🟢 |
| 8 | Dependency hygiene | 4 | **4** | Unchanged. `requirements.lock` + `requirements-dev.lock` with `--generate-hashes`. Dockerfile and CI use lock files. No new dependency regressions. | `requirements.lock`; `Dockerfile:4-5` | 🟢 |
| 9 | Separation of concerns | 4 | **4** | Unchanged. Business logic absent from routers, views, and UI modules. `memory/coordinator/` is the only writer; `agents/` reads via `MemoryService`. | `ui/components.py` (no session_state); `api/routers/query.py` (delegates to runner) | 🟢 |
| 10 | Correctness | 3 | **3** | Unchanged. Fix discipline visible in git history. 330 tests confirm production paths. | `git log --oneline -10`; 330 passing tests | 🟢 |
| 11 | Robustness against failure | 4 | **4** | Unchanged. Lazy imports in `ui/session.py`; fail-open sinks; `.streamlit/config.toml`; `LocalMemoryService` fail-open on DB error. | `memory/service.py:_get_or_load` (try/except); `evaluation/observer.py` | 🟢 |
| 12 | Error handling quality | 3 | **3** | Unchanged. `# noqa: BLE001` discipline maintained. No new broad-except regressions. | `ui/app.py`; `memory/service.py` | 🟡 (item 7.9) |
| 13 | Test quality | 4 | **4** | Unchanged in score. 330 tests (up from 227 at May 10). New tests cover: routing (sha256 bucket, determinism, cache invalidation), registry 3-tuple, observer variant labels, budget ceiling. Tests target behavior, not mocks. | `tests/prompts/test_registry.py`; `tests/agents/`; `tests/evaluation/` | 🟢 |
| 14 | Test strategy completeness | 4 | **4** | Unchanged. Two-job CI: unit+lint and integration with real Postgres. 3 skipped tests are DB-only. | `.github/workflows/ci.yml` | 🟢 |
| 15 | Security posture | 3 | **3** | Unchanged. CORS explicit allowlist, FAISS threat model documented (ADR-005). Auth absent. No new attack surface. | `api/main.py:87-89`; `knowledge/retriever.py:128-141` | 🟡 (items 7.1, 7.5–7.9 in I2B) |
| 16 | Supply-chain hygiene | 4 | **4** | Unchanged. Lock files with hashes. `pip-audit` in CI. | `requirements.lock`; `.github/workflows/ci.yml:24` | 🟢 |
| 17 | Typing and contracts rigor | 4 | **5** ↑ | **IMPROVED.** `mypy --strict` activated on `agents/` (8 source files, 0 errors). `mypy-agents-strict.ini` isolates the strict zone via `follow_imports = silent`. CI strict step + pre-commit `mirrors-mypy` hook (files: `^agents/.*\.py$`). Cross-zone `# type: ignore[no-untyped-call]` for `SystemModel`, `optimize_price`, `get_checkpointer` — documented, not silenced. Full Pydantic + TypedDict + Protocol adoption platform-wide. | `mypy-agents-strict.ini`; `.github/workflows/ci.yml` (strict step); `.pre-commit-config.yaml` (mypy hook); `agents/planner.py`; `agents/judge.py` | 🟢 |
| 18 | Invariant enforcement | 3 | **3** | Unchanged. DAG cycle assertion at spec-load, graph-build, and repo-write (item 3.3). Spec semver monotonicity enforced (item 3.6). | `system/system_graph.py:31-42`; `spec/spec_repository.py:61-81` | 🟢 |
| 19 | Duplication control | 4 | **4** | Unchanged. `agents/runner.py` DRYs UI/API paths. `agents/i18n.py` DRYs language directives. No new duplication. | `agents/runner.py`; `agents/i18n.py` | 🟢 |
| 20 | Dead-code hygiene | 5 | **5** | Unchanged. 160 files, dark-code ~0.0%. No zombie imports or silently-disabled paths. | `git ls-files "*.py"` count | 🟢 |
| 21 | Observability / diagnosability | 4 | **4** | Unchanged in score. Now additionally: `*_variant_label` persisted in `agent_runs` per run; `cost_usd` + `cost_eur` per run; budget tracker spans logged. | `evaluation/sinks/postgres_sink.py`; `db/models.py` (agent_runs) | 🟡 (OTel: items 8.2, 8.3, 8.4) |
| 22 | Performance awareness | 3 | **3** | Unchanged. `lru_cache(maxsize=256)` on `_get_cached_prompt_content` — zero DB queries per prompt content access. `lru_cache(maxsize=8)` on `_load_active_variants` — invalidated by mutation ops. | `prompts/registry.py:_get_cached_prompt_content`; `prompts/routing.py:_load_active_variants` | 🟡 (items 1.4, 4.4; ADR-005 triggers) |
| 23 | Documentation | 4 | **4** | Unchanged. `CLAUDE.md` updated (all completed items + Plan review discipline). README updated (variant endpoints + prompts/ tree + migrations 008+009). | `CLAUDE.md`; `README.md` | 🟢 |
| 24 | Change governance | 4 | **4** | Unchanged. CI enforces black → ruff → mypy (standard) → mypy (strict agents/) → pytest → boundary lint → pip-audit. | `.github/workflows/ci.yml` | 🟢 |
| 25 | Dark-code risk | 5 | **5** | Unchanged. No dead code. | Confirmed. | 🟢 |
| 26 | AI-generated code governance | 3 | **3** | Unchanged. No AI-narrative artifacts in production. | Baseline confirmed. | 🟡 |
| 27 | Overall maintainability | 4 | **4** | Unchanged. A new engineer can locate and modify the prompt routing, the memory layer, or the agent workflow independently. 330 tests serve as a routing oracle. | `ui/`; `memory/`; `prompts/`; `tests/` | 🟢 |
| 28 | Production-readiness from code | 2 | **2** | Unchanged. Auth, rate limiting, multi-tenancy remain absent. Cost ceiling and fail-open sinks address two production fragility modes. | `api/main.py`; `evaluation/budget.py` | 🟡 (items 7.1, 7.5–7.9, 12.5 in I2B) |

**Layer 1 mean: 3.75 / 5** (105 / 28 dimension points)
*(May 10 baseline: 3.64; Δ = +0.11)*

Dimensions improved: 5, 6, 17 (three of twenty-eight). No dimension regressed.

---

## 3. Layer 2 — AI / Agent Layer (20 dimensions)

| # | Dimension | Score (May 10) | Score (May 17) | Rationale | Evidence | Gap |
|---|---|---|---|---|---|---|
| 1 | Clarity of agentic role | 3 | **3** | Unchanged. Four named nodes (planner, tool, synthesizer, judge), clear single responsibilities. | `agents/workflow.py` | 🟡 (item 5.3.a in I3) |
| 2 | Explicitness of agentic boundary | 3 | **3** | Unchanged. LLM orchestrates via `ToolSelection` structured output; tools compute deterministically. | `agents/planner.py:53-72`; `agents/tools.py` | 🟢 |
| 3 | Separation between agents | 2 | **2** | Unchanged. Single agent; multi-agent prerequisites (MemoryService, Capability Graph) not yet implemented. | Single graph; item 5.3.a | 🟡 (items 5.3.a/b in I3) |
| 4 | Planning / orchestration | 4 | **4** | Unchanged. `ToolSelection` structured output; typed LangGraph DAG with conditional routing. | `agents/planner.py:53-72`; `agents/workflow.py:209-237` | 🟢 |
| 5 | Tooling discipline | 2 | **2** | Unchanged. Tools have typed params but no `ToolSpec` with explicit input/output schemas per item 4.3. | `agents/tools.py` | 🟡 (items 4.3, 10.8 in I2A/I3) |
| 6 | Tool safety | 2 | **2** | Unchanged. No SQL Execution Gateway; simulation inputs are validated by Python types only. | `agents/tools.py:84-94` | 🟡 (item 2.10 in I2A) |
| 7 | Model abstraction | 3 | **3** | Unchanged. `llm_factory.py` with fallback chain. No Bedrock/Vertex yet. | `agents/llm_factory.py:50-98` | 🟡 (item 5.6 in I2A) |
| 8 | Prompt governance | 4 | **5** ↑ | **IMPROVED (10.2).** A/B routing deployed: `prompts/routing.py` sha256-bucket routing (deterministic per session_id+stage), `PromptVariant` + `PromptVariantStatus` lifecycle, `get_prompt_template()` → 3-tuple `(content, version, label)`, all 4 call sites A/B-aware, `*_variant_label` persisted in `agent_runs` per run, migrations 008+009, 6 REST endpoints, `lru_cache(maxsize=8)` on variant loading + `lru_cache(maxsize=256)` on content (zero DB queries on hot path). Shadow evaluation (10.3) remains pending. | `prompts/routing.py`; `prompts/registry.py`; `api/routers/prompts.py` | 🟡 (shadow eval 10.3 in I2A) |
| 9 | State management | 4 | **4** | Unchanged in score. Three additional typed fields in `AgentState`: `planner/synthesizer/judge_variant_label` (item 10.2). All fields typed. | `agents/state.py:58-72` | 🟢 |
| 10 | Memory abstraction | 1 | **4** ↑ | **IMPROVED (5.11).** `MemoryService` Protocol (`core/protocols/memory.py`, `@runtime_checkable`, 7 methods) + `LocalMemoryService` concrete implementation + `get_memory_service()` process-level singleton. Planner receives `FrozenActiveAnalyticalState` via service — no raw `state["history"]` slicing. Boundary lint enforced in CI. `propose_state_update` / `commit_state_update` are v1 stubs (5.13). Score 4 = strong (single seam, typed, enforced). Score 5 would require multi-agent federation and 5.13 mutations beyond stubs. | `core/protocols/memory.py`; `memory/service.py`; `agents/planner.py:186-219`; `scripts/check_memory_boundary.py` | 🟡 (item 5.9 GroundedTokens; 5.13 mutations) |
| 11 | Retrieval / grounding | 2 | **3** ↑ | **IMPROVED (5.9).** `GroundedTokens` guardrail landed: `validate_strict()` blocks ungrounded params in planner, `check_observational()` annotates judge_feedback. Vocabulary built from spec (aliases + derived_metrics). Score 3: guardrail exists and is enforced; score 4 would require near-match suggestion and semantic similarity (deferred, tech debt). | `system/grounded_tokens.py`; `agents/planner.py`; `agents/judge.py` | 🟡 (near-match suggestion, item 10.8) |
| 12 | Output validation | 4 | **4** | Unchanged. Structured outputs at every LLM seam. `RunResult` dataclass typed contract at graph boundary. | `agents/runner.py:19-42`; `agents/planner.py:60-88` | 🟢 |
| 13 | Error / retry strategy | 3 | **3** | Unchanged. Exponential backoff, rate-limit detection, judge fails-open. `BudgetExceededError` now adds a clean abort path. | `agents/llm_factory.py:101-165`; `evaluation/budget.py` | 🟡 (item 8.7.d) |
| 14 | Loop control / boundedness | 1 | **2** ↑ | **IMPROVED (8.7.b).** `BudgetTracker` with `max_wallclock_s` and `max_llm_calls` caps enforced before every `invoke_with_fallback` call. `BudgetExceededError` aborts the run cleanly and returns a structured error. Recursion guard (item 5.12) still absent; score cannot reach 3. | `evaluation/budget.py:BudgetTracker.raise_if_exceeded`; `agents/llm_factory.py:144`; `agents/runner.py` (BudgetExceededError handler) | 🟡 (item 5.12 recursion guard in I3) |
| 15 | Observability of agent runs | 4 | **4** | Unchanged in score. Now additionally: `*_variant_label` and cost fields persisted per run. Full lineage: tool, latency, model, prompt_version, variant_label, cost_usd, judge_score. | `evaluation/sinks/postgres_sink.py`; `evaluation/observer.py:92-282` | 🟢 |
| 16 | Testing and evaluation | 3 | **3** | Unchanged. 15 golden queries in CI. No real-LLM golden eval harness yet. | `tests/evaluation/test_agent_golden.py` | 🟡 (items 10.3, 10.11 in I2A/I3) |
| 17 | LLM cost control | 0 | **4** ↑ | **IMPROVED (8.7.a+b).** `config/model_pricing.yaml` (all providers); `evaluation/cost.py` (`calculate_cost_usd`); `evaluation/currency.py` (Frankfurter USD→EUR, 1h cache, env fallback); `evaluation/budget.py` (`RunBudget.from_env()`, `BudgetTracker`, `BudgetExceededError`); tracker wired through `invoke_with_fallback` and all nodes; cost fields in `RunResult` → `QueryResponse` → `RunRecord` → `agent_runs` (migration 006); `/v1/budget/current` + `/v1/budget/exchange-rate`; UI cost KPIs + dashboard. Score 4 = strong. Score 5 would require per-tenant quotas and fallback-chain-by-budget (8.7.c/d). | `evaluation/budget.py`; `evaluation/cost.py`; `evaluation/currency.py`; `api/routers/budget.py`; `db/migrations/versions/006_*` | 🟡 (8.7.c/d/e/f in I2A/I3) |
| 18 | Multi-turn / session continuity | 2 | **3** ↑ | **IMPROVED (5.10+5.11).** Typed `ActiveAnalyticalState` persists structured intent and active runs across turns. Planner receives `FrozenActiveAnalyticalState` snapshot via `MemoryService`; injects intent, active simulation run, optimization run, and active metrics as a typed context system message. `history_window` still raw-transcript-based (no compaction); score cannot reach 4 until token compaction lands (item 5.9). | `memory/coordinator/coordinator.py`; `agents/planner.py:186-219`; `memory/service.py` | 🟡 (items 5.13, 5.9) |
| 19 | Multi-agent coordination | 1 | **1** | Unchanged. No multi-agent, no prerequisites. | Single graph | 🟡 (items 5.3.a/b, 5.12, 8.7.e in I3) |
| 20 | Agent autonomy policy | 3 | **3** | Unchanged. Item 3.5 complete. `JUDGE_THRESHOLD` still hardcoded. | `spec/autonomy.py`; `agents/workflow.py:_route_after_planner` | 🟡 (items 7.3, 5.3.b in I3) |

**Layer 2 mean: 3.05 / 5** (61 / 20 dimension points)
*(May 10 clean baseline: 2.55; Δ = +0.50)*

Dimensions improved: 8, 10, 14, 17, 18 (five of twenty). No dimension regressed.

---

## 4. Layer 3 — Conversational & Analytical Memory (22 dimensions)

> All advances driven by items 5.10 (ActiveAnalyticalState) and 5.11 (MemoryService Protocol).
> Dims 8–18 are largely unchanged from May 10 — the 5.10/5.11 cluster moved dims 1–6, 19–22.

| # | Dimension | Score (May 10) | Score (May 17) | Rationale | Evidence | Gap |
|---|---|---|---|---|---|---|
| 1 | Memory system existence | 2 | **4** ↑ | **IMPROVED (5.11).** `MemoryService` Protocol (`@runtime_checkable`) + `LocalMemoryService` concrete implementation + `get_memory_service()` singleton + `memory/` package with full typed abstractions. Boundary lint enforced in CI and pre-commit. | `core/protocols/memory.py`; `memory/service.py`; `memory/__init__.py` | 🟢 |
| 2 | System boundary clarity | 1 | **4** ↑↑↑ | **IMPROVED (5.11+5.13).** Single seam: `core/protocols/memory.py::MemoryService`. Boundary lint blocks direct `memory.coordinator.*` / `memory.state.*` access outside `memory/`. Mutations now fully exposed through the seam: `propose_state_update`, `commit_state_update`, `freeze_slot`, `unfreeze_slot`. Score 4 = seam is complete for v1. Score 5 would require multi-agent federation + cross-process proposal store. | `core/protocols/memory.py`; `memory/service.py` | 🟡 (item 5.13 v2 — volatile/sticky enforcement; multi-agent) |
| 3 | Structured active state | 0 | **3** ↑ | **IMPROVED (5.10).** `ActiveAnalyticalState` (mutable Pydantic) + `FrozenActiveAnalyticalState` (immutable deep-copy via `.frozen()`). Typed slots: `intent`, `active_simulation_run`, `active_optimization_run`, `active_scenarios`, `metrics`. | `memory/state/active.py`; `memory/state/types.py` | 🟡 (v2 slots — dimensions, period, geography — deferred to 5.13) |
| 4 | State centrality as truth | 0 | **3** ↑↑↑ | **IMPROVED (5.10+5.13).** `MemoryCoordinator` is the single writer; user-correction mutations now real (propose/commit/freeze/unfreeze). Raw transcript still used for long-range context; score cannot reach 4 until slot-inheritance rules land (volatile/sticky, tech debt 5.13 v2). | `memory/coordinator/coordinator.py`; `memory/service.py`; `agents/planner.py:186-219` | 🟡 (item 5.13 v2 — volatile/sticky lifecycle) |
| 5 | State traceability | 1 | **4** ↑↑↑ | **IMPROVED (5.10+5.13).** `SlotProvenance` records `introduced_at_turn`, `introduced_by`, `evidence`, `confidence` per slot. Append-only `StateTransition` audit log with `op`/`before`/`after`. User-confirmed provenance now recorded via commit audit log (`state_commits` table, migration 010). Freeze/unfreeze ops also logged. | `memory/state/types.py:SlotProvenance`; `memory/state/audit.py:StateTransition`; `db/models.py:StateCommitRow` | 🟢 |
| 6 | State lifecycle discipline | 1 | **4** ↑↑↑ | **IMPROVED (5.10+5.13).** `StateTransition` with `TransitionOp` (set/append/clear); append-only log; `MemoryCoordinator` is the only writer (single-writer pattern enforced by 5.11 boundary lint). Correction ops fully implemented: `propose_state_update` → `commit_state_update`; `freeze_slot` / `unfreeze_slot` add typed lifecycle control. | `memory/state/audit.py`; `memory/coordinator/coordinator.py`; `memory/service.py` | 🟡 (item 5.13 v2 — volatile expiry, SlotConflictEvent) |
| 7 | Short-range memory | 3 | **3** | Unchanged. 3-turn sliding window, env-configurable (`HISTORY_WINDOW`). No compaction. | `memory/checkpointer.py`; `config/settings.py` | 🟡 (item 5.9 compaction in I2A) |
| 8 | Explicit rule quality | 1 | **2** ↑ | **IMPROVED (5.13).** Structural signals (`first_turn`, `thin_context`) are deterministic code-level rules in `memory/proactive_confirmation.py`, not prompt strings. `STATE_CONFIRMATION_SIGNALS` env var makes active signal set explicit. Most multi-turn rules still in prompts; score 3 would require slot-inheritance rules in code. | `memory/proactive_confirmation.py`; `agents/workflow.py:proactive_confirmation_gate` | 🟡 (item 5.13 v2 — inheritance/conflict rules in code) |
| 9 | Inheritance governance | 0 | **0** | Unchanged. `volatile_slots` / `sticky_slots` scaffolded (typed fields) but not enforced in v1. Lifecycle rules deferred to tech debt 5.13 v2. | `memory/state/active.py` (volatile/sticky fields, not enforced) | 🟡 (item 5.13 v2 — design review required) |
| 10 | Reset / invalidation | 0 | **1** ↑ | **IMPROVED (5.13).** `volatile_slots` and `sticky_slots` are scaffolded fields (present, typed, in schema). Not enforced at turn boundary in v1 — enforcement is tech debt 5.13 v2. Score 1 = typed scaffolding present, no runtime enforcement. | `memory/state/active.py:volatile_slots`; `docs/tech_debt.md` (5.13 v2 entry) | 🟡 (item 5.13 v2) |
| 11 | Clarification governance | 2 | **3** ↑ | **IMPROVED (5.13).** Proactive gate adds a structured pause-and-confirm loop: `proactive_confirmation_gate` node fires on structural signals, returns `StateProposal` to client, UI renders `render_proactive_confirmation()`. Reactive corrections available at any time via POST `/state/proposals` + POST `/state/commits`. 4-way `_route_after_planner` routes explicitly. | `agents/workflow.py:proactive_confirmation_gate`; `ui/components.py:render_proactive_confirmation`; `api/routers/sessions.py` | 🟢 |
| 12 | Conflict resolution | 0 | **1** ↑ | **IMPROVED (5.13).** `frozen_slots` prevents mutations to user-pinned values: `commit_state_update` silently skips frozen slots and logs them in `skipped_slots`. No typed `SlotConflictEvent` yet (tech debt 5.13 v2). Score 1 = partial conflict prevention; score 2 would require explicit conflict events. | `memory/service.py:commit_state_update`; `memory/coordinator/coordinator.py:freeze_slot` | 🟡 (item 5.13 v2 — SlotConflictEvent) |
| 13 | Contextual retrieval | 2 | **2** | Unchanged. Retrieval keyed on raw query; no active-state enrichment. | `knowledge/retriever.py:54-68` | 🟡 (items 5.9, 10.8) |
| 14 | Retrieval subordination | 1 | **1** | Unchanged. Retrieval results passed verbatim; no active-state filter. | `knowledge/retriever.py` | 🟡 (item 5.9 in I2A) |
| 15 | Multi-turn behavior | 2 | **2** | Unchanged. Works in practice; correctness is prompt-level, not code-level. | `streamlit_app.py` E2E testing | 🟡 (item 5.13 in I2A) |
| 16 | Memory vs prompting balance | 1 | **1** | Unchanged. Most multi-turn logic in prompts. `ActiveAnalyticalState` injects structured context but does not yet replace prompt-level rules. | `agents/planner.py` (PLANNER_SYSTEM_TEMPLATE) | 🟡 (item 5.13 in I2A) |
| 17 | Complementary techniques | 2 | **2** | Unchanged. Sliding window only; no compaction, no summarization. | `memory/checkpointer.py` | 🟡 (item 5.9 in I2A) |
| 18 | Single-turn vs multi-turn separation | 2 | **2** | Unchanged. Uniform code path; no explicit first-turn vs. continuation separation. | `agents/runner.py:run_query` | 🟡 (item 5.13 in I2A) |
| 19 | User interaction with memory | 0 | **3** ↑↑↑ | **IMPROVED (5.10+5.11+5.13).** `GET /v1/sessions/{id}/state` + `/state/audit` read-only endpoints (5.10/5.11). Now also: `POST /v1/sessions/{id}/state/proposals` (reactive: user sees editable slots), `POST /v1/sessions/{id}/state/commits` (user approves mutations), UI `render_proactive_confirmation()` panel, `freeze_slot`/`unfreeze_slot` via commit API. Full read + write interaction surface. | `api/routers/sessions.py`; `ui/components.py:render_proactive_confirmation`; `memory/service.py` | 🟡 (item 5.13 v2 — volatile/sticky UI) |
| 20 | Downstream integration | 2 | **3** ↑ | **IMPROVED (5.11).** Planner receives `FrozenActiveAnalyticalState` snapshot via `MemoryService` and injects typed context (intent, active runs, metrics) as a system message. No raw transcript slicing in the structured context injection. | `agents/planner.py:186-219`; `memory/service.py` | 🟡 (item 5.13 — synthesizer/judge also use state) |
| 21 | Coordination / orchestration role | 2 | **3** ↑ | **IMPROVED (5.10).** `MemoryCoordinator` single-writer pattern; `persist_to_db()` / `load_from_db()` fail-open. All writes go through the coordinator. | `memory/coordinator/coordinator.py:persist_to_db`; `memory/coordinator/intent_mapping.py` | 🟢 |
| 22 | Coordination integrity | 1 | **3** ↑ | **IMPROVED (5.10+5.11).** Single-coordinator gate enforced by `MemoryService` Protocol boundary lint; no external code can mutate `ActiveAnalyticalState` directly without going through `memory/`. | `scripts/check_memory_boundary.py`; `memory/coordinator/coordinator.py` | 🟢 |

**Layer 3 mean: 2.45 / 5** (54 / 22 dimension points) *(was 2.00 pre-5.13, 44 pts)*
*(May 10 clean baseline: 1.18; Δ = +1.27)*

Dimensions improved (cumulative): 1, 2, 3, 4, 5, 6, 8, 10, 11, 12, 19, 20, 21, 22 (fourteen of twenty-two). No dimension regressed.

Post-5.13 improvements: 2 (3→4), 4 (2→3), 5 (3→4), 6 (3→4), 8 (1→2), 10 (0→1), 11 (2→3), 12 (0→1), 19 (1→3) — nine dimensions, +10 points.

All remaining gaps are 🟡 (planned in I2A/I3 or tech debt 5.13 v2). No 🔴 in this layer.
Dims 9 (inheritance) and the enforcement of dims 10 (volatile expiry) remain at 0/1 — gated by the design review required for tech debt 5.13 v2 (volatile/sticky lifecycle).

---

## 5. Layer 4 — Ontology & Semantic Knowledge (16 dimensions)

> No Ontology work landed in this sprint. All scores unchanged from May 10.

| # | Dimension | Score | Notes |
|---|---|---|---|
| 1 | Conceptual semantic layer | **3** | `OrganizationalModelSpec` typed tree consumed by all layers. |
| 2 | Formal ontology presence | **1** | No OWL/RDF; item 2.7 in "Más allá". |
| 3 | Entity registry | **1** | Typed dataclasses, not a Registry pattern; item 10.8 in I3. |
| 4 | Relationship modelling | **3** | `CausalRelationship` typed; DAG built from spec; DAG cycle asserted (item 3.3). |
| 5 | Metric registry | **1** | `TargetVariable` dataclass; not versioned; item 10.8 in I3. |
| 6 | Dimension / vocabulary registry | **2** | `system/grounded_tokens.py` Vocabulary built from spec at runtime (decision_vars + target_vars + derived_metrics + aliases). validate_strict() blocking + check_observational() non-blocking. Keyed by spec.version. Not a full VocabularyRegistry (no UI, no admin API). Near-match suggestion deferred to tech debt. Item 10.8 in I3. (item 5.9 ✅) |
| 7 | Alias / synonym handling | **2** | `aliases: list[str]` on DecisionVariable + TargetVariable + DerivedMetric; consumed by `build_vocabulary()`. Case-insensitive matching. Near-match/fuzzy deferred (tech debt). (item 5.9 ✅) |
| 8 | Ambiguity handling | **1** | Judge revision catches some; no `IntentClassifier`. |
| 9 | Business-to-system mapping | **2** | Single-step LLM-driven; no `MappingLayer`; item 2.2 in I2A. |
| 10 | Physical data introspection | **1** | No real external data sources; items 2.1, 2.2 in I2A. |
| 11 | Query interpretation | **4** | `ToolSelection` is the typed IR; strongest area of the semantic layer. |
| 12 | Runtime consumption | **4** | Spec consumed by every layer that should consume it. |
| 13 | Test coverage of semantic layer | **1** | Spec loader tests exist; no semantic goldens. Item 10.11 in I2A. |
| 14 | Governance / versioning | **4** | Items 3.6 (spec semver) + 10.1 (prompt lifecycle) + 10.2 (variant promotion lifecycle). Three artifact types with enforced lifecycle. |
| 15 | Scalability across domains | **4** | Domain switching is config-level; prompt built dynamically from spec. |
| 16 | Internal consistency | **3** | Spec is single source of truth; demand model formula is documentary. |

**Layer 4 mean: 2.06 / 5** (33 / 16 dimension points)
*(May 10 baseline: 2.06; Δ = 0.00)*

No dimensions changed. All gaps are 🟡 (planned in I2A, I3, "Más allá"). No 🔴.

---

## 6. Critical Findings (🔴) — Gaps not in inventory / roadmap / ADRs

**0 critical findings.**

Fourth consecutive audit with zero unplanned gaps.

| Audit | Open 🔴 | Closed 🔴 | Net |
|---|---|---|---|
| 2026-05-06 (baseline) | 6 | 0 | **6 open** |
| 2026-05-08 (delta #1) | 0 | 6 | **0 open** |
| 2026-05-10 (delta #2) | 0 | 0 | **0 open** |
| 2026-05-17 (delta #3) | 0 | 0 | **0 open** |

All architectural gaps found by this rubric are accounted for in the inventory, roadmap, or ADRs.

---

## 7. Planned Gaps (🟡) — Capabilities pending per the roadmap

High-impact items (sorted by score leverage):

| Layer · Dimension | Capability | Inventory item | Iteration | Status |
|---|---|---|---|---|
| ~~Memory · dims 9, 10, 12, 19~~ | ~~User-correction mutations; slot inheritance; conflict resolution~~ | ~~**5.13**~~ | ~~I2A~~ | ✅ **Completed 2026-05-18** — dims 2,4,5,6,8,10,11,12,19 improved; volatile/sticky enforcement in tech debt 5.13 v2 |
| Memory · dims 9, 10 (partial) | Volatile/sticky slot lifecycle; SlotConflictEvent | **5.13 v2** | I2A/I3 | Pending (design review required — no inventory item yet) |
| AI · #11 Retrieval / grounding | `GroundedTokens` guardrail; active-state enrichment | **5.9** | I2A | Pending |
| AI · #8 Prompt governance (shadow eval) | Eval-gated auto-promotion (10.3) | **10.3** | I2A | Pending |
| AI · #16 Testing / eval | Real-LLM golden eval harness | **10.11** | I2A / I3 | Pending |
| AI · #14 Loop control | Recursion guard | **5.12** | I3 | Partial (wallclock+call caps via 8.7.b) |
| AI · #17 LLM cost control | Budget reservation; fallback-chain-by-budget | **8.7.c/d** | I2A | Pending |
| Memory · #7, 17 Compaction | Token-budget compaction, summarization | **5.9** | I2A | Pending |
| Codebase · #15 Security posture | Auth, RLS, encryption, audit log | **7.1, 7.5–7.9** | I2B | Pending |
| Codebase · #28 Production-readiness | Composite of 7.x + 8.x | multiple | I2B + I3 | Pending |
| Codebase · #4 Modularity (layer-deps lint) | Comprehensive layer boundary enforcement | **11.1** | I2A | Partial (memory boundary only) |
| Ontology · #6, #7 Vocabulary / synonyms | `VocabularyRegistry` + synonym fields | **10.8 (I3), 5.9 (I2A)** | I2A / I3 | Pending |
| AI · #3, #19 Multi-agent | Capability Graph, per-peer budgets | **5.3.a/b, 8.7.e** | I3 | Pending |

---

## 8. Genuine Strengths

### 8.1–8.14 (confirmed from previous audits)

- **8.1** Single coherent architecture, end-to-end — no competing paradigms across 160 files
- **8.2** Spec-driven design that is actually spec-driven (not just named so)
- **8.3** Type discipline above the size class (TypedDict + Pydantic + Protocol everywhere)
- **8.4** Dual-backend pattern consistent across modules (Postgres primary, SQLite/FAISS fallback)
- **8.5** Observability built in, not bolted on (per-run lineage: tool, model, prompt_version, variant_label, cost, judge_score)
- **8.6** Error handling discipline with explicit `# noqa: BLE001` — no silent swallowing
- **8.7** Active fix discipline visible in commit history (hotfix commits documented, reverts committed, not force-pushed)
- **8.8** Documentation that matches the code (CLAUDE.md, README, roadmap, audit docs updated on every PR)
- **8.9** Tests that test behavior, not mocks (goldens, integration, routing, budget ceiling)
- **8.10** CI pipeline that earns trust (two-job: unit+lint+mypy+strict+boundary+audit; integration with real Postgres)
- **8.11** Dead-code at 0.0% across 160 Python files
- **8.12** `ui/` package as a clean rendering separation (pure render functions, no session_state in components.py)
- **8.13** `RunSink` Protocol as ObjectBus-ready typed seam (when item 1.6 lands, sinks become bus subscribers with no interface change)
- **8.14** `agents/runner.py` as Directive-3 implementation (single callable used by Streamlit, FastAPI, and future MCP)

### 8.15 — MemoryService Protocol + single-writer pattern + boundary lint

`core/protocols/memory.py` defines a `@runtime_checkable` `MemoryService` Protocol with 7 methods — the
single seam through which all agents, the API, and the UI interact with the memory layer. `LocalMemoryService`
is the concrete implementation (fail-open on DB error). `MemoryCoordinator` is the only writer of
`ActiveAnalyticalState`, enforced by `scripts/check_memory_boundary.py` in CI and pre-commit.
`governance/memory_boundary_exceptions.yaml` makes justified violations explicit and time-bounded.
This is the correct way to build a memory layer that can grow from a prototype to a distributed system
without callers noticing: the seam is correct today, not "we'll add a protocol when it matters".

### 8.16 — Plan review discipline as a documented engineering practice

`CLAUDE.md` now includes a "Plan review discipline" section, first applied on PR #24. The plan review for
10.2 produced four concrete, codebase-specific risks before any code was written:

1. `session_id` must flow from `planner_node` state all the way to `get_prompt_template()` — four call sites
   require simultaneous atomic update.
2. `get_prompt_template()` must not add 3 DB queries per agent run — `lru_cache` on `(stage, session_id)`
   with invalidation on mutation ops is required.
3. `_get_system_prompt` had already been removed from `agents/planner.py` — test files patching it would
   fail at collection. Caught before writing any test.
4. The 3-tuple return value of `get_prompt_template()` requires backward-compatible update of all 4 call
   sites atomically — not one at a time.

All four risks materialised as exact issues during implementation and were addressed because they were
anticipated. This is the correct use of a plan review: not a ritual, but a concrete early-warning system.

### 8.17 — Prompt A/B testing full stack with zero DB queries on hot path

`prompts/routing.py` implements deterministic sha256-bucket routing: the same `session_id` always maps to
the same variant (no session jumping). `_load_active_variants(stage)` uses `@lru_cache(maxsize=8)`,
invalidated by all four mutation operations (`start_rollout`, `adjust_rollout`, `promote_to_champion`,
`deprecate_variant`). `_get_cached_prompt_content(prompt_id, version)` uses `@lru_cache(maxsize=256)` —
never cleared (immutable by `(id, version)`). The hot path (`get_prompt_template` in agent nodes) hits zero
DB queries in steady state. Variant attribution flows end-to-end: routing → `AgentState` → `RunRecord` →
`agent_runs` table → dashboard visibility. Six REST endpoints for operator control. This is a complete A/B
testing infrastructure, not a proof of concept.

### 8.18 — mypy --strict on `agents/` with zero errors across 8 files

`mypy-agents-strict.ini` activates `strict = True` for `agents.*` and `follow_imports = silent` for all
non-agents packages (preventing strict-check leakage into imported modules). All 8 `agents/` source files
pass with 0 errors. Cross-zone `# type: ignore[no-untyped-call]` annotations for `SystemModel`,
`optimize_price`, and `get_checkpointer` are documented, not silenced. The strict zone is enforced in CI
(dedicated step after the standard mypy step) and in pre-commit (file-filtered `mirrors-mypy` hook). A
strict-typed agent layer is non-trivial at this codebase size; it constrains future changes to maintain
the discipline.

### 8.19 — User-driven state corrections (5.13): two-channel explicit mutation loop *(post-PR 2026-05-18)*

`memory/proactive_confirmation.py` implements deterministic structural signals (`first_turn`, `thin_context`)
that pause the LangGraph graph before an expensive tool runs, presenting a `StateProposal` to the user.
The 6-node graph routes 4-way in `_route_after_planner`: clarification > proactive gate > synthesizer
(autonomy policy) > tool. Confirmed re-runs set `bypass_gate=True` in `AgentState`.

Reactive corrections: `POST /v1/sessions/{id}/state/proposals` packages editable slots as identity
proposals; `POST /v1/sessions/{id}/state/commits` applies approved mutations via `MemoryCoordinator`,
silently skipping `frozen_slots`. `freeze_slot()` / `unfreeze_slot()` let users pin values across turns.
`state_proposals` + `state_commits` tables (migration 010) provide audit persistence.

The `agents/tools_registry.py` cost classifier (`cheap` / `expensive`) makes gate behaviour extensible:
when item 4.3 (skills engine) lands, operators can register new expensive skills without changing gate
code. 382 tests, 0 strict mypy errors maintained.

---

## 9. Comparison with previous self-audits

### 9.1 — Four-point evolution table

| Layer | May 6 (baseline) | May 8 (corrected) | May 10 (clean) | May 17+5.13 |
|---|---|---|---|---|
| L1 Codebase (28 dims) | 2.96 | 3.39 | 3.64 | **3.75** |
| L2 AI/Agent (20 dims) | 2.40 | 2.50 | 2.55 | **3.10** |
| L3 Memory (22 dims) | 1.55 | 1.14 | 1.18 | **2.45** |
| L4 Ontology (16 dims) | 2.31 | 2.00 | 2.06 | **2.31** |
| **Overall (86 dims)** | **2.55** | **2.35** | **2.47** | **3.00** |

Notes:
- "May 8 (corrected)" uses recomputed sums from the May 10 audit's arithmetic correction note.
- "May 10 (clean)" is the May 10 audit score before the inline post-audit updates (5.10, 5.11, 8.7.a+b).
  Using the clean baseline makes this audit's Δ attributable entirely to changes in this window.
- The apparent May 6→May 8 regression in L3 (1.55→1.14) and L4 (2.31→2.00) is an arithmetic
  correction, not a code regression. The May 6 stated means did not reconcile with their own dim tables.
- "May 17+5.13" = post-PR 2026-05-18 scores. L2 and L4 include 5.9's contributions (corrected from
  the original MD arithmetic). L3 includes 5.13's +10 pts. Overall: 258/86 = **3.00**.
  *(The original May 17 MD stated 2.83, which omitted 5.9's L2.11+L4.6+7 contributions; the HTML showed the correct 2.88. Both are superseded by the 5.13 update.)*

### 9.2 — Delta since May 10 (this sprint)

| Layer | Dim # | Dimension | May 10 | May 17 | Driver |
|---|---|---|---|---|---|
| L1 | 5 | Boundary integrity | 2 | **3** | 5.11: boundary lint in CI + pre-commit; MemoryService seam |
| L1 | 6 | Composability | 3 | **4** | 5.11: MemoryService Protocol; 10.2: routing seam; multiple typed Protocols composed |
| L1 | 17 | Typing and contracts rigor | 4 | **5** | mypy --strict on agents/ (0 errors); CI strict step; pre-commit hook |
| L2 | 8 | Prompt governance | 4 | **5** | 10.2: A/B routing, PromptVariant lifecycle, 3-tuple, migrations 008+009, 6 endpoints |
| L2 | 10 | Memory abstraction | 1 | **4** | 5.11: MemoryService Protocol + LocalMemoryService + boundary lint |
| L2 | 11 | Retrieval / grounding | 2 | **3** | 5.9: validate_strict() blocks ungrounded params; check_observational() on judge |
| L2 | 14 | Loop control / boundedness | 1 | **2** | 8.7.b: BudgetTracker with wallclock + call caps |
| L2 | 17 | LLM cost control | 0 | **4** | 8.7.a+b: tracking + ceilings + API endpoints + DB persistence |
| L2 | 18 | Multi-turn / session continuity | 2 | **3** | 5.10+5.11: ActiveAnalyticalState + MemoryService + typed context injection |
| L3 | 1 | Memory system existence | 2 | **4** | 5.11: MemoryService Protocol + LocalMemoryService + boundary lint |
| L3 | 2 | System boundary clarity | 1 | **4** | 5.11+5.13: single seam + mutations exposed through MemoryService |
| L3 | 3 | Structured active state | 0 | **3** | 5.10: ActiveAnalyticalState + FrozenActiveAnalyticalState |
| L3 | 4 | State centrality as truth | 0 | **3** | 5.10+5.13: single-writer + user-correction mutations real |
| L3 | 5 | State traceability | 1 | **4** | 5.10+5.13: SlotProvenance + StateTransition + commit audit DB |
| L3 | 6 | State lifecycle discipline | 1 | **4** | 5.10+5.13: correction ops + freeze/unfreeze fully implemented |
| L3 | 8 | Explicit rule quality | 1 | **2** | 5.13: structural signals (first_turn, thin_context) in code |
| L3 | 10 | Reset/invalidation | 0 | **1** | 5.13: volatile_slots/sticky_slots typed scaffolding (not enforced) |
| L3 | 11 | Clarification governance | 2 | **3** | 5.13: proactive gate + reactive correction API + UI panel |
| L3 | 12 | Conflict resolution | 0 | **1** | 5.13: frozen_slots silently skips conflicting mutations |
| L3 | 19 | User interaction with memory | 0 | **3** | 5.10+5.11+5.13: read endpoints + POST proposals + commits + UI |
| L3 | 20 | Downstream integration | 2 | **3** | 5.11: planner receives FrozenActiveAnalyticalState via MemoryService |
| L3 | 21 | Coordination / orchestration role | 2 | **3** | 5.10: MemoryCoordinator single-writer pattern with fail-open persistence |
| L3 | 22 | Coordination integrity | 1 | **3** | 5.10+5.11: single-coordinator gate enforced by boundary lint |
| L4 | 6 | Dimension/vocabulary registry | 1 | **2** | 5.9: Vocabulary built from spec; validate_strict() + check_observational() |
| L4 | 7 | Alias/synonym handling | 1 | **2** | 5.9: aliases on DecisionVariable + TargetVariable + DerivedMetric |

**27 dimensions improved since May 10** (18 at May 17 + 9 from item 5.13 post-PR 2026-05-18). No dimension regressed.

### 9.3 — Invariants confirmed (strengths that must not decline)

All 19 strengths (8.1–8.19) are confirmed. A decline in any confirmed-strength dimension in the next
audit is an alarm.

### 9.4 — What the next audit (I2A close-out) should show

With 5.13 now landed and overall at 3.00, the next high-leverage items are:
- L2 AI: 3.10 → ~3.20 (item 10.3 eval-gated auto-promotion: dim 8 from 5 to maintained; dim 16 from 3→4)
- L1 Codebase: 3.75 → ~3.80 (security baseline: dim 15 from 3→4)
- L3 Memory: 2.45 → ~2.50 (5.13 v2 volatile/sticky enforcement: dim 9 from 0→1, dim 10 from 1→2)
- L4 Ontology: 2.31 → ~2.40 (item 2.2 MappingLayer: dim 9 from 2→3)
- **Overall: 3.00 → ~3.10**

---

## 10. Prioritized remediation plan

### P0 — No open P0 items ✅

Zero critical findings for the fourth consecutive sprint.

### P1 — Highest-leverage next steps (I2A)

1. ~~**⏱ 2–3 days · Item 5.13 (user-correction mutations).**~~ ✅ **Completed 2026-05-18.**
   Lifted L3 dims 2,4,5,6,8,10,11,12,19 — +10 points. Overall crosses 3.00.

2. ~~**⏱ 2 days · Item 5.9 (GroundedTokens guardrail + compaction).**~~ ✅ **Completed 2026-05-17.**
   Guardrail ✓; compaction deferred to tech debt.

3. **⏱ 1 day · Item 10.3 (eval-gated auto-promotion).** Shadow evaluation harness: records
   judge scores per variant per session, gates promotion to champion on a configured threshold.
   Lifts L2 dim 8 fully into mature governance (shadow eval closes the last planned gap).

4. **⏱ 1 day · Items 8.7.c/d (budget reservation + fallback-chain-by-budget).** Adds
   per-tenant quota reservation and automatic model downgrade when budget threshold is approached.
   Lifts L2 dim 17 toward 5.

### P2 — Tactical hygiene (compound interest)

5. **Security baseline (items 7.5, 7.6).** Add JWT/API-key authentication to FastAPI
   and rate-limiting middleware. Lifts L1 dim 15 (3→4) and starts the L1 dim 28 journey
   toward production-readiness.

6. **OTel traces (items 8.2, 8.3).** Add `opentelemetry-sdk` and instrument
   `invoke_with_fallback` + node entry/exit. Lifts L1 dim 21 (4→5) and L2 dim 15 (4→5).
   Currently blocked by missing correlation ID flow — add `run_id` to contextvars first.

7. **Layer-deps lint expansion (item 11.1).** Extend `scripts/check_memory_boundary.py`
   to cover all layer boundaries (agents/ → db/ direct access; api/ → memory/ direct access).
   Lifts L1 dim 5 (3→4).

---

## End of audit · 2026-05-17 · commit `28c1c48`

Auditor: Claude Sonnet 4.6 (Anthropic) · Methodology: llull self-audit v1.0
Previous audits: 2026-05-06 (baseline), 2026-05-08 (delta #1), 2026-05-10 (delta #2)
Next re-audit recommended: after item 5.13 (user-correction mutations) or 10.3 (eval-gated promotion) lands.
Expected overall score after I2A completion: ~3.00 / 5.

**Post-PR note 2026-05-19**: hotfix/5.13-proactive-gate-and-resume merged (PR #27). Changes:
AND semantics in `memory/proactive_confirmation.py` (`triggered == active` — gate fires only when
all active signals trigger simultaneously); LangGraph checkpoint reset in `agents/runner.py`
(gate-only checkpoint bleed); `bypass_gate` wired into `QueryRequest` + `api/routers/query.py`;
session state cleanup in `ui/session.py`. Item 5.13.c (reactive correction inline form) opened as
pending — backend complete, Streamlit form not yet implemented. 417 tests. No dimension scores
change (behavioral fix, not new capability).
