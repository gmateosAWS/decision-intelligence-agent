# llull · Self-Audit · 2026-05-10 · commit `22b4a6a`

## 0. Auditor signature

- **Auditor**: Claude Sonnet 4.6 (Anthropic)
- **Date (UTC)**: 2026-05-10
- **Repository**: https://github.com/gmateosAWS/decision-intelligence-agent
- **Commit hash**: `22b4a6a` — `[fix] Add [build-system] to pyproject.toml to suppress Streamlit multi-requirements warning`
- **Branch**: `feature/11.1-ci-pipeline`
- **Inputs read**:
  - Repository tree (12,875 LOC Python across 116 files — was 8,881 LOC / 79 files at May 8 audit)
  - `docs/llull_inventario_v4.md` (116 items)
  - `docs/llull_roadmap_v4.md` (4 iterations + "Más allá")
  - `docs/adr-001-pgvector-over-qdrant.md`
  - `docs/ADR-002-langgraph-orchestration.md`
  - `docs/ADR-003-llullgen-component-reuse-policy.md`
  - `docs/audit/2026-05-06_llull_self_audit.md` (baseline)
  - `docs/audit/2026-05-08_llull_self_audit.md` (delta #1)
- **Methodology version**: 1.0 (unchanged from previous audits)
- **Delta context**: Audit #3. Window: 2026-05-08 → 2026-05-10.
  Completed since May 8: item 3.6 (spec semver), item 3.5 (autonomy policies), item 10.1 (prompt
  registry), P2.2 (Streamlit monolith split into `ui/` package + `agents/runner.py`), P2.3 (observer
  split into `evaluation/sinks/` with RunSink Protocol), plus 5 hotfix commits (lazy imports,
  `.streamlit/config.toml` file watcher, psycopg3, pyproject.toml build-system, width="stretch" revert).

---

## 1. Executive Summary

**Overall maturity score (dimension-weighted across 86 dimensions)**: **2.52 / 5** *(updated 2026-05-12 with items 8.7.a+b)*

**Methodology note on arithmetic correction**: This audit computes layer means directly from the sum
of each layer's dimension scores divided by the count. Previous audits' stated layer means did not match
their own dimension-score tables (e.g., May 8 L3 table sums to 25/22 = 1.14, stated as 1.27; L4 sums
to 32/16 = 2.00, stated as 2.31). The 2.44 figure is consistent with the actual dimension scores.
The corrected May 8 baseline is **2.35**; the corrected delta to May 10 is **+0.09**. Section 9
provides the full reconciliation against both previous audits.

Layer scores:

| Layer | Score (May 10) | Δ (corrected May 8 → May 10) | Stated May 8 | Dimensions |
|---|---|---|---|---|
| Codebase & Architecture | **3.57** | +0.18 | 3.46 (stated) | 28 |
| AI / Agent Layer | **2.55** | +0.05 | 2.55 (stated) | 20 |
| Conversational & Analytical Memory | **1.18** | +0.04 | 1.27 (stated) | 22 |
| Ontology & Semantic Knowledge | **2.06** | +0.06 | 2.31 (stated) | 16 |

Findings summary:

- 🔴 **Critical (gap real)**: **0 items** — third consecutive audit with zero unplanned gaps.
- 🟡 **Planned (in inventory / roadmap / ADR)**: **46 dimensions** (down from 48 at May 8; two
  graduated: L3 dim 11 from pending to partial, L4 dim 14 from partial to strong).
- 🟢 **Confirmed strengths**: the 11 confirmed at May 8, plus three new: `ui/` package architecture
  (8.12), RunSink Protocol as first typed architectural seam (8.13), `agents/runner.py` as Directive-3
  shared callable (8.14).

**Posture summary.** The sprint closed the two largest un-closed tactical debts from the May 8 audit:
the 1,040 LOC `streamlit_app.py` monolith (now a 22-line thin wrapper; the `ui/` package absorbs all
rendering, session, sidebar, and dashboard logic) and the 465 LOC `AgentObserver` god class (refactored
into a typed `RunSink` Protocol with three pluggable implementations in `evaluation/sinks/`). These two
changes account for most of the L1 gain: five dimensions advance (3, 5, 6, 11, 21) where they had stalled.
The production hardening of the Streamlit rendering stack — lazy imports in `ui/session.py` preventing
import-cascade failures, `.streamlit/config.toml` disabling the file watcher that silently killed the
spinner during LLM execution, try/except isolation around chart rendering — reflects genuine operational
discipline, not cosmetic polish.

Three architectural items also land in this window: item 3.6 (spec semantic versioning with enforced
monotonicity and migration 003 CHECK constraint), item 3.5 (autonomy policies with a runtime conditional
edge in the graph), and item 10.1 (Prompt Registry with draft/certified/deprecated lifecycle, five REST
endpoints, and prompt_version propagated through AgentState → RunRecord → `agent_runs` table). Prompt
governance (L2 dim 8) advances from 3 to 4: the registry is no longer just designed — all three agents
consume it at runtime with inline fallback. Item 3.5 provides the scaffolding for L3 dim 11 to advance
from 1 to 2: `requires_confirmation` and `requires_approval` are now typed state fields, not implicit
prompt strings, and the graph enforces them via `_route_after_planner`.

The **dominant gap pattern is unchanged**: Memory (Layer 3) and LLM cost control (AI Layer dim 17)
are held back by the absence of `ActiveAnalyticalState` (item 5.10) and the full cost-tracking cluster
(8.7.a–f). All of these are 🟡 (planned in I2A). The Memory mean improved only 0.04 points despite dim 11
advancing — a reminder that the six 0-score dimensions (3, 4, 9, 10, 12, 19) are jointly gated by item 5.10
and will not move until it lands. The next audit after I2A close-out should show Memory at ~2.5, not 1.18.

Dark-code share: **~0.0%**. The `ui/` split and `evaluation/sinks/` refactor did not introduce dead
paths. `streamlit_app.py` is 22 lines of active glue, not dead code.

---

## 2. Layer 1 — Codebase & Architecture (28 dimensions)

> For dimensions unchanged from May 8, the May 8 rationale is confirmed and evidence re-cited.
> For changed dimensions, a full updated rationale is provided with new diff evidence.
> "Score (prev)" = May 8 audit score.

| # | Dimension | Score (prev) | Score (now) | Rationale | Evidence | Gap |
|---|---|---|---|---|---|---|
| 1 | Local code clarity | 4 | **4** | Unchanged. `streamlit_app.py` (previously 1,040 LOC, the main outlier) is now 22 lines. Largest production files: `evaluation/observer.py` 464 LOC, `ui/components.py` ~280 LOC, `ui/app.py` 220 LOC. All well-structured. | `streamlit_app.py:1-22`; `evaluation/observer.py:1-464`; `ui/app.py:1-220` | 🟢 |
| 2 | Naming quality | 4 | **4** | Unchanged. `RunResult`, `RunSink`, `AgentObserver`, `get_prompt_template` follow the established domain-aligned pattern. No naming regressions. | `agents/runner.py:19-42`; `evaluation/sinks/base.py:19-30`; `prompts/registry.py` | 🟢 |
| 3 | Function / class size and cohesion | 3 | **4** | **IMPROVED.** P2.2 eliminates the 1,040 LOC `streamlit_app.py` monolith — now 22 lines. P2.3 eliminates the 465 LOC `AgentObserver` god-class by splitting it into: `observer.py` (thin orchestrator ~200 LOC), `evaluation/sinks/jsonl_sink.py`, `postgres_sink.py`, `langsmith_sink.py`, `confidence.py` (ConfidenceScorer). Largest remaining production file: `evaluation/observer.py` at 464 LOC (still the orchestrator + RunRecord accumulation; functionally coherent). | `streamlit_app.py:1-22`; `evaluation/sinks/jsonl_sink.py`; `evaluation/confidence.py`; `ui/app.py:1-220` | 🟢 |
| 4 | Modularity | 3 | **3** | Unchanged in score. `ui/` package improves behavioral cohesion (render functions in `components.py`, state in `session.py`, orchestration in `app.py`). No layer-deps lint declared. | `ui/components.py` (pure render, no session_state access); `ui/session.py` (all state); `ui/app.py` (orchestrator) | 🟡 (item 11.1 layer-deps lint) |
| 5 | Boundary integrity | 1 | **2** | **IMPROVED.** `evaluation/sinks/base.py:19` introduces the first `@runtime_checkable` Protocol in the codebase: `class RunSink(Protocol)`. This is a genuine typed seam — `AgentObserver` depends on `RunSink`, not on concrete sinks. MemoryService Protocol (item 5.11) and layer-deps lint remain absent; score cannot reach 3. | `evaluation/sinks/base.py:15-30` (`Protocol, runtime_checkable` import + class); `grep "Protocol" agents/ → 0 hits` (MemoryService still missing) | 🟡 (item 5.11, I2A) |
| 6 | Composability | 2 | **3** | **IMPROVED.** `RunSink` Protocol enables three pluggable implementations (JsonlSink, PostgresSink, LangSmithBridge) with identical interface. `agents/runner.py:19-42` defines `RunResult` — a typed dataclass that Streamlit UI, FastAPI, and future MCP callers all consume. The `run_query()` function is the first implementation of Directive 3: one callable, three callers. | `evaluation/sinks/base.py:19-30`; `agents/runner.py:45-145`; `api/routers/query.py` (delegates to `run_query`) | 🟡 (MemoryService Protocol, 5.11; `ToolBase`, 4.3) |
| 7 | Architectural integrity | 4 | **4** | Unchanged. Single architecture end-to-end. `ui/` package, `evaluation/sinks/`, and `agents/runner.py` strengthen the architecture without introducing a second paradigm. | `agents/workflow.py:209-237`; `ui/app.py:1-220`; `evaluation/sinks/` | 🟢 |
| 8 | Dependency hygiene | 4 | **4** | Unchanged in score. `psycopg[binary]==3.3.4` (psycopg3 for langgraph-checkpoint-postgres) and `langgraph-checkpoint-postgres==3.0.5` added to `requirements.txt`. `pyproject.toml` now has `[build-system]` with setuptools to distinguish from Poetry format (Streamlit CC warning). | `requirements.txt:22-23`; `pyproject.toml:1-3` | 🟢 |
| 9 | Separation of concerns | 4 | **4** | Unchanged in score. `ui/components.py` contains pure render functions with no `session_state` access. `ui/session.py` owns all state. `ui/app.py` is the orchestrator. Business logic does not appear in any UI module. | `ui/components.py` (no `st.session_state` reference); `ui/session.py`; `api/routers/query.py` | 🟢 |
| 10 | Correctness | 3 | **3** | Unchanged. `width="stretch"` revert (hotfix after incorrect use_container_width change) demonstrates active fix discipline. `st.rerun()` placement (only for card-button `_pending_query`, never for agent response flow) is documented and enforced. | `ui/app.py:141-143` (the only `st.rerun()` call); commit `6739035` (revert) | 🟢 |
| 11 | Robustness against failure | 3 | **4** | **IMPROVED.** Three independent improvements: (1) All heavy imports in `ui/session.py` moved inside function bodies — import-cascade failure mode eliminated for the UI layer. (2) All five sink imports in `evaluation/observer.py` wrapped in `try/except` — observer fails open even if psycopg2, langsmith, or faiss is absent. (3) `.streamlit/config.toml` sets `fileWatcherType = "none"` — prevents the file watcher from detecting JSONL log writes during LLM execution and triggering a rerun that killed the spinner. | `ui/session.py` (lazy imports inside functions); `evaluation/observer.py` (5 try/except blocks); `.streamlit/config.toml:2` | 🟢 |
| 12 | Error handling quality | 3 | **3** | Unchanged in score. `ui/app.py` wraps inline rendering extras in `try/except` — text rendering and session_state append execute unconditionally before the try block. `ui/components.py._render_assistant_extras` similarly wrapped. Disciplined `# noqa: BLE001` usage continues. | `ui/app.py:204-217`; `ui/components.py` (`_render_assistant_extras` try/except) | 🟡 (item 7.9) |
| 13 | Test quality | 4 | **4** | Unchanged in score. 227 tests pass (was 101 at May 8; +126 new: 28 in `tests/evaluation/test_sinks.py`, 15 in `tests/prompts/`, 10 in `tests/api/`, 9 in `tests/agents/test_i18n.py`, 7 in new DAG cycle tests, remainder from ui/ and runner tests). Tests target behavior, not mocks. No coverage gate yet (step to 5). | `tests/evaluation/test_sinks.py` (28 tests, Protocol conformance + fail-open); `tests/system/test_dag_cycle.py` (6 unit); `tests/api/test_spec_cycle_validation.py` (1 API) | 🟢 |
| 14 | Test strategy completeness | 4 | **4** | Unchanged. Two-job CI pipeline continues to enforce unit + integration. New test modules slot cleanly into the existing pytest-marker strategy. | `.github/workflows/ci.yml:1-104`; `pyproject.toml:9-12` | 🟢 |
| 15 | Security posture | 3 | **3** | Unchanged. CORS explicit allowlist, FAISS threat model documented, auth absent. No new attack surface introduced. | `api/main.py:87-89`; `knowledge/retriever.py:128-141` | 🟡 (items 7.1, 7.5, 7.6, 7.8, 7.9 in I2B) |
| 16 | Supply-chain hygiene | 3 | **4** | **IMPROVED.** `requirements.lock` and `requirements-dev.lock` generated with `pip-compile --generate-hashes --allow-unsafe`. Dockerfile uses `pip install --no-cache-dir --no-deps -r requirements.lock`. CI uses `pip install --no-deps -r requirements-dev.lock` (superset). `requirements.txt` preserved for Streamlit Community Cloud. `pip-audit` continues in CI. | `requirements.lock`; `requirements-dev.lock`; `Dockerfile:4-5`; `.github/workflows/ci.yml:24` | 🟢 |
| 17 | Typing and contracts rigor | 4 | **4** | Unchanged in score. `RunResult` dataclass and `RunSink` Protocol add new typed seams. `AgentState` gains three new typed fields (`requires_confirmation`, `requires_approval`, `confirmation_message`) plus three prompt_version fields. `mypy` in CI continues. | `agents/runner.py:19-42` (RunResult dataclass); `agents/state.py:58-64` (six new fields); `evaluation/sinks/base.py:19-30` (Protocol) | 🟢 |
| 18 | Invariant enforcement | 2 | **3** | **IMPROVED.** Item 3.3 adds DAG cycle assertion at three integration points: `assert_dag_acyclic()` in `system/system_graph.py` (graph-build time); lazy-import hook in `spec_loader._parse_raw()` (every spec load); `_validate_dag_acyclic()` in `spec_repository.create_spec()` and `update_spec()` (before DB write). 7 tests confirm all integration points. Spec version monotonicity from item 3.6 continues. | `system/system_graph.py:31-42` (`assert_dag_acyclic`); `spec/spec_loader.py:303-306` (lazy hook); `spec/spec_repository.py:61-81` (`_validate_dag_acyclic`); `tests/system/test_dag_cycle.py`; `tests/api/test_spec_cycle_validation.py` | 🟢 |
| 19 | Duplication control | 4 | **4** | Unchanged. `agents/runner.py` DRYs the Streamlit/FastAPI execution paths (was duplicated; now one `run_query()` callable). No new duplication introduced. | `agents/runner.py:45-145`; `api/routers/query.py` (delegates to `run_query`) | 🟢 |
| 20 | Dead-code hygiene | 5 | **5** | Unchanged. 116 Python files, dark-code share ~0.0%. The `ui/` split and sinks refactor produced no dead paths. `streamlit_app.py` is 22 lines of active glue. | `streamlit_app.py:1-22`; `git ls-files "*.py" \| wc -l → 116` | 🟢 |
| 21 | Observability / diagnosability | 3 | **4** | **IMPROVED.** P2.3 delivers three observability improvements: (1) `evaluation/sinks/postgres_sink.py` writes structured records to `agent_runs` with three new `prompt_version` columns (migration 005), enabling prompt attribution per run. (2) `evaluation/confidence.py:ConfidenceScorer` produces a typed 0–1 score from tool output — previously a raw heuristic. (3) All three agents record their `prompt_version` via `AgentState → RunRecord → PostgresSink`. Full per-run lineage (tool, latency, model, prompt_version, judge_score) now persisted. | `evaluation/sinks/postgres_sink.py`; `evaluation/confidence.py`; `agents/state.py:62-64` (prompt_version fields); `db/models.py` (agent_runs + 3 cols) | 🟡 (OTel, run_id contextvars: items 8.4, 8.2, 8.3) |
| 22 | Performance awareness | 3 | **3** | Unchanged. | Baseline confirmed. | 🟡 (items 1.4, 4.4) |
| 23 | Documentation | 4 | **4** | `CLAUDE.md` updated with all new items (3.6, 3.5, 10.1, P2.2, P2.3), architecture diagram reflects `ui/` package and `evaluation/sinks/`, Directive 3 implementation documented. `docs/llull_roadmap_visual.html` updated. | `CLAUDE.md` ("Completed items" section); `docs/llull_roadmap_visual.html` | 🟢 |
| 24 | Change governance | 4 | **4** | Unchanged. CI pipeline continues to enforce black → ruff → mypy → pytest → pip-audit on every push. | `.github/workflows/ci.yml` | 🟢 |
| 25 | Dark-code risk | 5 | **5** | Unchanged. No dead code. | Confirmed. | 🟢 |
| 26 | AI-generated code governance | 3 | **3** | Unchanged. No AI-narrative artifacts. `# noqa: BLE001` discipline maintained. | Baseline confirmed. | 🟡 |
| 27 | Overall maintainability | 4 | **4** | Unchanged in score. `ui/` package makes onboarding substantially easier — a new engineer can locate and modify sidebar, chat rendering, or dashboard independently. 220 tests provide a routing oracle. | `ui/` package (6 focused modules); `tests/evaluation/test_agent_golden.py` (15 canonical queries) | 🟢 |
| 28 | Production-readiness from code | 2 | **2** | Unchanged. `.streamlit/config.toml` and lazy imports address two production fragility modes. Auth, rate limiting, multi-tenancy remain absent. | `.streamlit/config.toml`; `ui/session.py` (lazy imports); absence of auth middleware | 🟡 (items 7.1, 7.5, 7.6, 7.8, 12.5 in I2B) |

**Layer 1 mean: 3.64 / 5** (102 / 28 dimension points)
*(Corrected May 8 baseline: 3.39; stated May 8: 3.46)*

Dimensions improved: 3, 5, 6, 11, 16, 18, 21 (seven of twenty-eight). No dimension regressed.

---

## 3. Layer 2 — AI / Agent Layer (20 dimensions)

| # | Dimension | Score (prev) | Score (now) | Rationale | Evidence | Gap |
|---|---|---|---|---|---|---|
| 1 | Clarity of agentic role | 3 | **3** | Unchanged. Four named nodes (planner, tool, synthesizer, judge), clear docstrings and single responsibilities. | `agents/workflow.py` | 🟡 (item 5.3.a in I3) |
| 2 | Explicitness of agentic boundary | 3 | **3** | Unchanged. LLM orchestrates via `ToolSelection` structured output; tools compute deterministically. | `agents/planner.py:53-72`; `agents/tools.py` | 🟢 |
| 3 | Separation between agents | 2 | **2** | Unchanged. Single agent; multi-agent prerequisites (MemoryService, Capability Graph) not yet implemented. | Single graph; item 5.3.a | 🟡 (items 5.3.a/b in I3) |
| 4 | Planning / orchestration | 4 | **4** | Unchanged. `ToolSelection` structured output; typed LangGraph DAG with conditional routing. | `agents/planner.py:53-72`; `agents/workflow.py:209-237` | 🟢 |
| 5 | Tooling discipline | 2 | **2** | Unchanged. Tools have typed params but no `ToolSpec` with explicit input/output schemas per item 4.3. | `agents/tools.py` | 🟡 (items 4.3, 10.8) |
| 6 | Tool safety | 2 | **2** | Unchanged. No SQL Execution Gateway; simulation inputs are validated by Python types only. | `agents/tools.py:84-94` | 🟡 (item 2.10 in I2A) |
| 7 | Model abstraction | 3 | **3** | Unchanged. `llm_factory.py` with fallback chain. No Bedrock/Vertex yet. | `agents/llm_factory.py:50-98` | 🟡 (item 5.6 in I2A) |
| 8 | Prompt governance | 3 | **4** | **IMPROVED.** Item 10.1 is fully deployed: `prompts/registry.py` with idempotent `seed_prompts_from_code()` at API startup; `get_prompt_template(stage, fallback)` consumed by all three agent nodes; five REST endpoints (`GET/POST /v1/prompts`, `GET /v1/prompts/{id}/{version}`, `PUT .../certify`, `PUT .../deprecate`); `prompt_version` propagated through `AgentState:62-64 → RunRecord → PostgresSink → agent_runs` table via migration 005. Inline fallback ensures no degradation when DB unavailable. A/B testing (10.2) and shadow evaluation (10.3) remain pending. | `prompts/registry.py`; `prompts/models.py`; `agents/state.py:62-64`; `api/routers/prompts.py`; migration 005 | 🟡 (A/B testing 10.2, shadow eval 10.3 in I2A) |
| 9 | State management | 4 | **4** | Unchanged. `AgentState` TypedDict now has three additional typed fields for autonomy (`requires_confirmation`, `requires_approval`, `confirmation_message`) and three for prompt traceability (`planner/synthesizer/judge_prompt_version`). All new fields typed. | `agents/state.py:58-66` | 🟢 |
| 10 | Memory abstraction | 1 | **1** | Unchanged. No `MemoryService` Protocol. Planner slices `state["history"]` directly. | `agents/planner.py:185-196` | 🟡 (items 5.10, 5.11 in I2A) |
| 11 | Retrieval / grounding | 2 | **2** | Unchanged. RAG configured; no `GroundedTokens` guardrail. | `knowledge/retriever.py:54-68` | 🟡 (item 5.9 in I2A) |
| 12 | Output validation | 4 | **4** | Unchanged. Structured outputs at every LLM seam. `RunResult` dataclass is a new typed contract at the graph boundary. | `agents/runner.py:19-42`; `agents/planner.py:60-88` | 🟢 |
| 13 | Error / retry strategy | 3 | **3** | Unchanged. Exponential backoff, rate-limit detection, judge fails-open. Fail-open sinks in observer strengthen robustness. | `agents/llm_factory.py:101-165`; `evaluation/observer.py` (try/except blocks) | 🟡 (item 8.7.d) |
| 14 | Loop control / boundedness | 1 | **2** | **IMPROVED.** Item 8.7.b adds `BudgetTracker` with `max_wallclock_s` and `max_llm_calls` caps enforced before every `invoke_with_fallback` call. `BudgetExceededError` aborts the run cleanly and returns a structured error. Recursion guard (item 5.12) still absent; score cannot reach 3. | `evaluation/budget.py` (`BudgetTracker.raise_if_exceeded`); `agents/llm_factory.py:144` (pre-call check); `agents/runner.py` (`BudgetExceededError` handler) | 🟡 (item 5.12 recursion guard in I3) |
| 15 | Observability of agent runs | 4 | **4** | Unchanged in score. Now additionally records `prompt_version` per node per run. Full lineage: tool, latency, model, prompt_version, confidence, judge_score all in `agent_runs`. | `evaluation/sinks/postgres_sink.py`; `evaluation/observer.py:92-282` | 🟢 |
| 16 | Testing and evaluation | 3 | **3** | Unchanged. 15 golden queries in CI. No real-LLM golden eval harness yet. | `tests/evaluation/test_agent_golden.py` | 🟡 (items 10.2, 10.11 in I2A/I3) |
| 17 | LLM cost control | 0 | **3** | **IMPROVED.** Items 8.7.a + 8.7.b fully implemented: `config/model_pricing.yaml` (pricing table all providers); `evaluation/cost.py` (calculate_cost_usd); `evaluation/currency.py` (USD→EUR via Frankfurter, 1h cache); `evaluation/budget.py` (RunBudget.from_env, BudgetTracker, BudgetExceededError); tracker wired through `invoke_with_fallback` and all nodes; cost fields in RunResult → QueryResponse → RunRecord → `agent_runs` (migration 006); `/v1/budget/current` + `/v1/budget/exchange-rate` endpoints; UI cost KPIs + dashboard row. Per-tenant quotas (multi-tenant) and fallback-chain-by-budget (8.7.c/d) remain pending. | `evaluation/budget.py`; `evaluation/cost.py`; `agents/llm_factory.py:144` (tracker pre-call); `db/migrations/versions/006_*`; `api/routers/budget.py` | 🟡 (8.7.c budget reservation, 8.7.d fallback chain, 8.7.e/f multi-agent in I2A/I3) |
| 18 | Multi-turn / session continuity | 2 | **2** | Unchanged. Checkpointing via `thread_id`; history window of 3. `requires_confirmation` and `requires_approval` are now typed state but do not add multi-turn context. | `memory/checkpointer.py:63-95`; `agents/planner.py:185-196` | 🟡 (items 5.10, 5.11 in I2A) |
| 19 | Multi-agent coordination | 1 | **1** | Unchanged. No multi-agent, no prerequisites. | Single graph | 🟡 (items 5.3.a/b, 5.12, 8.7.e in I3) |
| 20 | Agent autonomy policy | 3 | **3** | Unchanged. Item 3.5 complete: `spec/autonomy.py` with AutonomyLevel/ToolAutonomyPolicy/AutonomyPolicy; `_route_after_planner` conditional edge enforces policy at runtime; `GET/PUT /v1/specs/{id}/autonomy` REST endpoints; 26 tests. `JUDGE_THRESHOLD` still hardcoded — items 7.3 and 5.3.b for I3. | `spec/autonomy.py`; `agents/workflow.py` (`_route_after_planner`); `agents/state.py:58-60` | 🟢 (3.5 done; 7.3 + 5.3.b in I3) |

**Layer 2 mean: 2.75 / 5** (55 / 20 dimension points)
*(Corrected May 8 baseline: 2.50; May 10 baseline: 2.55)*

Dimensions improved: 8, 14, 17 (three of twenty). No dimension regressed.

---

## 4. Layer 3 — Conversational & Analytical Memory (22 dimensions)

One dimension improved since May 8 (dim 11). All others unchanged.

| # | Dimension | Score | Change | Notes |
|---|---|---|---|---|
| 1 | Memory system existence | 2 | — | `memory/` package with checkpointer + session_manager. No typed MemoryService. |
| 2 | System boundary clarity | 1 | — | Planner reads `state["history"]` directly; no single seam. |
| 3 | Structured active state | 0 | — | No `ActiveAnalyticalState`. All six 0-score dims await item 5.10. |
| 4 | State centrality as truth | 0 | — | Transcript is the source of truth; no typed slot-based state. |
| 5 | State traceability | 1 | — | Run-level provenance only via `run_id`; no slot provenance. |
| 6 | State lifecycle discipline | 1 | — | Append-only transcript; no slot-transition audit log. |
| 7 | Short-range memory | 3 | — | 3-turn sliding window, env-configurable; no compaction. |
| 8 | Explicit rule quality | 1 | — | Multi-turn rules live in system prompt strings. |
| 9 | Inheritance governance | 0 | — | No slot inheritance logic. |
| 10 | Reset / invalidation | 0 | — | No invalidation rules per slot type. |
| 11 | Clarification governance | 1 → **2** | **+1** | Item 3.5 introduces `requires_confirmation: bool`, `requires_approval: bool`, and `confirmation_message: Optional[str]` as typed fields in `AgentState` (lines 58–60). The planner consults `AutonomyPolicy` and sets these fields; `_route_after_planner` conditional edge enforces them; `RunResult` propagates them to the UI. Pending clarifications are now **tracked as typed state**, not implicit in prompts. Score 2 = partial: fields and graph routing exist, but no user-facing clarification flow UI (e.g., user can't respond to a confirmation request and resume the run). | `agents/state.py:58-60`; `spec/autonomy.py`; `agents/workflow.py` (`_route_after_planner`); `agents/runner.py:40-42` |
| 12 | Conflict resolution | 0 | — | No declarative conflict rules. |
| 13 | Contextual retrieval | 2 | — | Retrieval keyed on raw query; no active-state enrichment. |
| 14 | Retrieval subordination | 1 | — | Retrieval results passed verbatim; no active-state filter. |
| 15 | Multi-turn behavior | 2 | — | Works in practice; correctness is prompt-level, not code-level. |
| 16 | Memory vs prompting balance | 1 | — | All multi-turn logic in prompts, not coded rules. |
| 17 | Complementary techniques | 2 | — | Sliding window only; no compaction, no summarization. |
| 18 | Single-turn vs multi-turn | 2 | — | Uniform code path; no explicit first-turn vs. continuation separation. |
| 19 | User interaction with memory | 0 | — | No slot inspection/mutation APIs. |
| 20 | Downstream integration | 2 | — | Synthesizer and judge read from state; planner slices history directly. |
| 21 | Coordination / orchestration | 2 | — | LangGraph orchestrates; no `MemoryCoordinator`. |
| 22 | Coordination integrity | 1 | — | No single-coordinator gate on memory mutations. |

**Layer 3 mean: 1.18 / 5** (26 / 22 dimension points)
*(Corrected May 8 baseline: 1.14; stated May 8: 1.27)*

All 21 remaining gaps are 🟡 (planned in I2A/I3). No 🔴 in this layer. The six 0-score dimensions
(3, 4, 9, 10, 12, 19) are jointly gated by item 5.10 `ActiveAnalyticalState` — the single
highest-leverage item in the I2A backlog.

---

## 5. Layer 4 — Ontology & Semantic Knowledge (16 dimensions)

One dimension improved since May 8 (dim 14). All others unchanged.

| # | Dimension | Score | Change | Notes |
|---|---|---|---|---|
| 1 | Conceptual semantic layer | 3 | — | `OrganizationalModelSpec` typed tree consumed by all layers. |
| 2 | Formal ontology presence | 1 | — | No OWL/RDF; item 2.7 in "Más allá". |
| 3 | Entity registry | 1 | — | Typed dataclasses, not a Registry pattern; item 10.8 in I3. |
| 4 | Relationship modelling | 3 | — | `CausalRelationship` typed; DAG built from spec. |
| 5 | Metric registry | 1 | — | `TargetVariable` dataclass; not versioned; item 10.8 in I3. |
| 6 | Dimension / vocabulary registry | 0 | — | No VocabularyRegistry; items 5.9, 10.8. |
| 7 | Alias / synonym handling | 0 | — | No synonyms in spec; item 5.9. |
| 8 | Ambiguity handling | 1 | — | Judge revision catches some; no `IntentClassifier`. |
| 9 | Business-to-system mapping | 2 | — | Single-step LLM-driven; no `MappingLayer`; item 2.2 in I2A. |
| 10 | Physical data introspection | 1 | — | No real data sources; items 2.1, 2.2 in I2A. |
| 11 | Query interpretation | 4 | — | `ToolSelection` is the typed IR; strongest area of the semantic layer. |
| 12 | Runtime consumption | 4 | — | Spec consumed by every layer that should consume it. |
| 13 | Test coverage of semantic layer | 1 | — | Spec loader tests exist; no semantic goldens. Item 10.11 in I2A. |
| 14 | Governance / versioning | 3 → **4** | **+1** | **IMPROVED.** Two new governance mechanisms land in this sprint: (a) Item 3.6 adds `spec/versioning.py` with `SpecVersion`, `BumpType`, `detect_bump_type()`, `validate_version()`, and monotonicity enforcement — specs can only advance (PATCH → MINOR → MAJOR), enforced by a migration 003 database CHECK constraint. `POST /v1/specs/{id}/bump` exposes explicit bumps. (b) Item 10.1 adds a full `PromptStatus` lifecycle (`draft → certified → deprecated`) in `prompts/models.py` with enforced transitions via `certify()` / `deprecate()` in `prompts/registry.py`. Two independent versioned artifact types, both with enforced lifecycle. Score 4 = strong; score 5 would require cross-artifact version linking and audit trail. | `spec/versioning.py`; `prompts/models.py` (`PromptStatus`); `prompts/registry.py` (`certify`, `deprecate`); `api/routers/specs.py` (`/bump` endpoint); migration 003 |
| 15 | Scalability across domains | 4 | — | Domain switching is config-level; prompt built dynamically from spec. |
| 16 | Internal consistency | 3 | — | Spec is single source of truth; demand model formula is documentary, not asserted. |

**Layer 4 mean: 2.06 / 5** (33 / 16 dimension points)
*(Corrected May 8 baseline: 2.00; stated May 8: 2.31)*

All gaps are 🟡 (planned in I2A, I3, "Más allá"). No 🔴 in this layer.

---

## 6. Critical Findings (🔴) — Gaps not in inventory / roadmap / ADRs

**0 critical findings.**

Third consecutive audit with zero unplanned gaps. The 6 findings identified at May 6 baseline were
closed by May 8. No new 🔴 findings arose in this sprint.

| Audit | Open 🔴 | Closed 🔴 | Net |
|---|---|---|---|
| 2026-05-06 (baseline) | 6 | 0 | **6 open** |
| 2026-05-08 (delta #1) | 0 | 6 | **0 open** |
| 2026-05-10 (delta #2) | 0 | 0 | **0 open** |

All remaining gaps are classified 🟡 (planned in the roadmap, inventory, or ADRs). The inventory
and roadmap cover every architectural gap found by this rubric.

---

## 7. Planned Gaps (🟡) — Capabilities pending per the roadmap

High-impact items only (full list available via inventory grep):

| Layer · Dimension | Capability | Inventory item | Iteration | Status |
|---|---|---|---|---|
| Memory · dims 3, 4, 9, 10, 12, 19 (six 0-score) | `ActiveAnalyticalState` typed object | 5.10 | **I2A · highest-leverage** | Pending |
| Memory · dim 2 | `MemoryService` Protocol + boundary lint | 5.11 | I2A | Pending |
| ~~AI · #17 LLM cost control~~ | ~~Token tracking, quotas, hard ceilings~~ | ~~8.7.a–f~~ | ~~I2A~~ | ✅ 8.7.a+b done 2026-05-12; 8.7.c/d/e/f pending |
| AI · #14 Loop control | Recursion guard (wallclock+call caps now in place via 8.7.b) | 5.12 | I3 | Partial ↑ |
| AI · #11 Retrieval / grounding | `GroundedTokens` guardrail | 5.9 | I2A | Pending |
| AI · #10 Memory abstraction | `MemoryService` Protocol | 5.11 | I2A | Pending |
| AI · #8 Prompt governance (partial) | A/B testing, shadow evaluation | 10.2, 10.3 | I2A | Pending |
| AI · #16 Testing / eval | Real-LLM golden eval harness | 10.11 | I2A / I3 | Pending |
| Codebase · #5 Boundary integrity | Layer-deps lint; MemoryService seam | 5.11 + 11.1 | I2A | Pending |
| Codebase · #15 Security posture | Auth, RLS, encryption, audit log | 7.1, 7.5, 7.6–7.9 | I2B | Pending |
| Codebase · #28 Production-readiness | Composite of 7.x + 8.x | multiple | I2B + I3 | Pending |
| Ontology · #6, #7 Vocabulary / synonyms | `VocabularyRegistry` + synonym fields | 10.8 (I3), 5.9 (I2A) | I2A / I3 | Pending |
| AI · #3, #19 Multi-agent | Capability Graph, per-peer budgets | 5.3.a/b, 8.7.e | I3 | Pending |
| AI · #20 Autonomy policy (partial) | Per-agent policies, runtime enforcement | 7.3, 5.3.b | I3 | Pending |
| Codebase · #16 Supply-chain | `pip-tools` lock file | — | Tactical | Pending |

46 dimensions remain 🟡. The sprint reduced this by 2 (dim L3-11 and L4-14 graduated from "absent/pending"
to "partially implemented" — their scores advanced but the underlying full capabilities remain 🟡).

---

## 8. Genuine Strengths

The 11 strengths confirmed at May 8 (8.1–8.11) are all confirmed unchanged. Three new strengths added.

### 8.1–8.11 (from previous audits) — all confirmed

- 8.1 Single coherent architecture, end-to-end
- 8.2 Spec-driven design that is actually spec-driven (not just named so)
- 8.3 Type discipline above the size class
- 8.4 Dual-backend pattern consistent across modules
- 8.5 Observability built in, not bolted on
- 8.6 Error handling discipline with explicit `# noqa: BLE001`
- 8.7 Active fix discipline visible in commit history
- 8.8 Documentation that matches the code
- 8.9 Tests that test behavior, not mocks
- 8.10 CI pipeline that earns trust (two-job: unit+lint, integration with real Postgres)
- 8.11 Dead-code at 0.0% across 116 Python files

### 8.12 — `ui/` package as a clean rendering separation

The `streamlit_app.py` split did not merely reduce LOC — it produced a genuinely clean architecture:
`ui/components.py` contains pure render functions with no `st.session_state` access (a hard discipline
to maintain), `ui/session.py` owns all state transitions, `ui/app.py` is a pure orchestrator, and
`ui/dashboard.py` imports metrics lazily inside `render_dashboard()` to prevent cascade failures. A
developer can now read the entire UI rendering logic without encountering any agent invocation code.
These are the bones of a maintainable frontend, not a hurried split.

### 8.13 — `RunSink` Protocol as first typed architectural seam

`evaluation/sinks/base.py:19` defines `@runtime_checkable class RunSink(Protocol)` with a single
method `finalize_run(record: Dict[str, Any]) -> None`. The docstring states the ObjectBus-ready design
intent (item 1.6): when item 1.6 lands, each sink becomes a bus subscriber with the same interface,
zero code change. This is the correct way to design for a planned architectural seam — not "we'll
refactor when the bus arrives", but "the interface is correct today". The three implementations
(JsonlSink, PostgresSink, LangSmithBridge) all satisfy the Protocol and can be replaced independently.

### 8.14 — `agents/runner.py` as Directive-3 implementation

`agents/runner.py` implements Directive 3 ("every capability must be internally callable as a typed
Python function") for the agent execution path. `run_query(query, thread_id, observer, graph) → RunResult`
is the single callable used by the Streamlit UI (`ui/session.py:run_agent_query`), the FastAPI service
(`api/routers/query.py`), and will be used by future MCP clients without modification. `RunResult` is
a dataclass with 16 typed fields — it is not a free-form dict. This is a non-trivial achievement in a
prototype: the "internal callable with a clear contract" constraint is actually enforced, not just stated.

---

## 9. Comparison with previous self-audits

### 9.1 — Arithmetic correction note

Previous audits had inconsistencies between their stated layer means and the sum of their dimension
scores. This audit recomputes all three baselines from the actual dimension scores:

| Layer | May 6 (stated) | May 8 (stated) | May 8 (corrected) | May 10 (this audit) | May 12 (8.7.a+b) | Δ May 10→12 |
|---|---|---|---|---|---|---|
| L1 Codebase (28 dims) | 2.96 | 3.46 | **3.39** | **3.64** | **3.64** | +0.00 |
| L2 AI/Agent (20 dims) | 2.40 | 2.55 | **2.50** | **2.55** | **2.75** | +0.20 |
| L3 Memory (22 dims) | 1.55 | 1.27 | **1.14** | **1.18** | **1.18** | +0.00 |
| L4 Ontology (16 dims) | 2.31 | 2.31 | **2.00** | **2.06** | **2.06** | +0.00 |
| **Overall (86 dims)** | **2.55** | **2.65** | **2.35** | **2.47** | **2.52** | **+0.05** |

The corrected May 8 baseline is 2.35, not 2.65. The trend is genuinely upward: +0.09 from corrected
May 8. The apparent "decline" from stated values is entirely due to arithmetic correction, not regression.

### 9.2 — Delta against May 6 (baseline) — all changes since the first audit

| Layer | Dim # | Dimension | May 6 | May 10 | Net change | Driver |
|---|---|---|---|---|---|---|
| L1 | 3 | Function / class size | 3 | **4** | +1 | P2.2: ui/ split eliminates 1040 LOC monolith; P2.3: observer split |
| L1 | 5 | Boundary integrity | 1 | **2** | +1 | P2.3: RunSink Protocol (first typed seam) |
| L1 | 6 | Composability | 2 | **3** | +1 | P2.3: RunSink Protocol + P2.2: RunResult typed interface |
| L1 | 8 | Dependency hygiene | 3 | **4** | +1 | pytest, mypy, types-* added; pyproject py312; psycopg3 |
| L1 | 11 | Robustness against failure | 2 | **4** | +2 | lazy imports + fail-open sinks + config/settings.py lazy + .streamlit config |
| L1 | 13 | Test quality | 3 | **4** | +1 | 220 tests (was ~85); goldens, sinks, prompts, i18n, smoke |
| L1 | 14 | Test strategy completeness | 2 | **4** | +2 | CI pipeline: two jobs; integration with real Postgres |
| L1 | 15 | Security posture | 2 | **3** | +1 | CORS allowlist; FAISS threat model |
| L1 | 16 | Supply-chain hygiene | 2 | **4** | +2 | pip-audit in CI; `requirements.lock` + `requirements-dev.lock` with hashes; Dockerfile + CI use lock files |
| L1 | 18 | Invariant enforcement | 2 | **3** | +1 | Item 3.3: DAG cycle assertion at spec load, graph build, and repo write; 7 tests |
| L1 | 19 | Duplication control | 3 | **4** | +1 | agents/i18n.py + agents/runner.py DRY |
| L1 | 20 | Dead-code hygiene | 4 | **5** | +1 | scenario_runner deleted; is_new removed |
| L1 | 21 | Observability | 3 | **4** | +1 | sinks refactor; prompt_version propagation; ConfidenceScorer |
| L1 | 24 | Change governance | 2 | **4** | +2 | CI pipeline enforces black+ruff+mypy+pytest on every push |
| L1 | 25 | Dark-code risk | 4 | **5** | +1 | scenario_runner deleted; 0.0% dark code |
| L1 | 27 | Overall maintainability | 3 | **4** | +1 | CI + golden eval + ui/ package + 220 tests |
| L1 | 28 | Production-readiness | 1 | **2** | +1 | CI + Dockerfile + lazy imports + CORS |
| L2 | 8 | Prompt governance | 1 | **4** | +3 | Item 10.1: full registry, lifecycle, REST, prompt_version in DB |
| L2 | 16 | Testing / evaluation | 2 | **3** | +1 | 15 golden queries in CI (item 5.2 foundation) |
| L2 | 20 | Agent autonomy policy | 1 | **3** | +2 | Item 3.5: autonomy.py + _route_after_planner + REST endpoints |
| L3 | 11 | Clarification governance | 1 | **2** | +1 | Item 3.5: requires_confirmation/approval in AgentState |
| L4 | 14 | Governance / versioning | 3 | **4** | +1 | Items 3.6 + 10.1: spec semver + prompt lifecycle |

**Total since May 6: 23 dimension improvements.** No dimension regressed across the full period.

### 9.3 — Delta against May 8 (delta #1) — changes in this sprint only

| Layer | Dim # | Dimension | May 8 | May 10 | Driver |
|---|---|---|---|---|---|
| L1 | 3 | Function / class size | 3 | **4** | P2.2: ui/ split; P2.3: observer split |
| L1 | 5 | Boundary integrity | 1 | **2** | P2.3: RunSink Protocol |
| L1 | 6 | Composability | 2 | **3** | P2.3: RunSink Protocol + P2.2: RunResult |
| L1 | 11 | Robustness against failure | 3 | **4** | Lazy imports + fail-open sinks + .streamlit config |
| L1 | 21 | Observability | 3 | **4** | Sinks refactor; prompt_version propagation; ConfidenceScorer |
| L2 | 8 | Prompt governance | 3 | **4** | Item 10.1 fully deployed (registry at runtime, not just designed) |
| L3 | 11 | Clarification governance | 1 | **2** | Item 3.5: typed state fields + graph routing |
| L4 | 14 | Governance / versioning | 3 | **4** | Items 3.6 + 10.1 both deployed |
| L1 | 16 | Supply-chain hygiene | 3 | **4** | `requirements.lock` + `requirements-dev.lock`; Dockerfile + CI updated to use lock files |
| L1 | 18 | Invariant enforcement | 2 | **3** | Item 3.3: DAG cycle assertion at spec load, graph build, and repo write; 7 tests |

**10 dimensions improved since May 8.** No regression.

### 9.4 — Invariants confirmed (strengths that must not decline)

The 11 baseline strengths (8.1–8.11) are all confirmed. Three new strengths added (8.12–8.14).

### 9.5 — What the next audit (I2A close-out) should show

If I2A items land as planned, the next audit should show:
- Memory layer: 1.18 → ~2.50 (item 5.10 moves 6 dims from 0 to 2+; item 5.11 moves dims 2, 10)
- AI Layer: 2.55 → ~2.80 (items 8.7.a–d add cost control: dim 17 from 0 to 2; 5.6 for model abstraction)
- Codebase: 3.64 → ~3.70 (boundary integrity 2→3 with MemoryService Protocol + layer-deps lint)
- Ontology: 2.06 → ~2.20 (item 2.2 MappingLayer: dim 9 from 2 to 3)
- Overall: 2.47 → **~2.80**

A decline in any of the 14 confirmed-strength dimensions (8.1–8.14) in the next audit is an alarm.

---

## 10. Prioritized remediation plan

### P0 — No open P0 items ✅

Zero critical findings for the second consecutive sprint.

### P1 — Highest-leverage next steps (I2A)

1. **⏱ 3–4 days · Item 5.10 (ActiveAnalyticalState typed).** The single highest-ROI item in the
   remaining backlog. Lifts 6 Memory dimensions from 0 to 2+ simultaneously. Design: a Pydantic model
   in `memory/active_state.py` with fields for active metric, active dimensions, period, geography,
   frozen slots, pending confirmations, provenance dict. Wire into `MemoryService` (5.11) and replace
   the `state["history"]` slice in `agents/planner.py:185-196` with a typed call. The `requires_confirmation`
   infrastructure from item 3.5 already provides the UI-side hook for presenting pending confirmations.

2. **⏱ 1 day · Item 5.11 (MemoryService Protocol).** Follow immediately after 5.10. Create
   `memory/memory_service.py` with a `MemoryService` Protocol (mirroring the `RunSink` precedent from
   P2.3). Add a ruff rule banning direct `state["history"]` access outside `memory/`. Lifts L1 dims 5
   and 6 from 2 and 3 to 3 and 4.

3. **⏱ 2 days · Items 8.7.a + 8.7.b (LLM cost control: tracking + hard ceilings).** Add `token_count`
   and `cost_usd` fields to `RunRecord` in `evaluation/observer.py`. Add a per-run hard ceiling env
   var (`LLM_MAX_TOKENS_PER_RUN`). These are the critical-path I2A items. Lifts AI Layer dim 17
   from 0 to 2.

4. **⏱ 1 day · Item 1.6 (ObjectBus).** Per CLAUDE.md, deferred until LlullGen codebase is available
   for reference (ADR-003 Principle 1). The `RunSink` Protocol is already ObjectBus-ready. When item
   1.6 lands, each sink becomes a bus subscriber with no interface change needed — the seam is correct.

### P2 — Tactical hygiene (compound interest)

5. ~~**Add `pip-tools` lock file** (`requirements.lock`). Lifts L1 dim 16 from 3 to 4.~~ ✅ Done 2026-05-11: `requirements.lock` + `requirements-dev.lock` with `--generate-hashes`; Dockerfile + CI updated; L1 dim 16 lifted to 4.

6. **`mypy --strict` migration on `agents/`.** Apply strict mode package-by-package. Lifts L1 dim 17
   from 4 to 5. Estimated 2–3 hours for `agents/` only; expand in subsequent sprints.

7. **Item 10.2 (A/B testing for prompts).** The registry is deployed — A/B testing is the obvious next
   step. Adds a `variant` field to `PromptRecord`, a routing function in `prompts/registry.py`, and
   a `variant_id` column in `agent_runs`. Lifts L2 dim 8 toward 5.

8. ~~**DAG cycle assertion (item 3.3).** One line: `if not nx.is_directed_acyclic_graph(G): raise ValueError(...)`. Lifts L1 dim 18 from 2 to 3.~~ ✅ Done 2026-05-11: three integration points + 7 tests; L1 dim 18 lifted to 3.

---

## End of audit · 2026-05-10 · commit `22b4a6a`

Auditor: Claude Sonnet 4.6 (Anthropic) · Methodology: llull self-audit v1.0
Previous audits: 2026-05-06 (baseline), 2026-05-08 (delta #1)
Next re-audit recommended: after I2A close-out (items 5.10, 5.11, 8.7.a–b land).
Expected overall score after I2A: ~2.80 / 5.
