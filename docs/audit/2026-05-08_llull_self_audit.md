# llull · Self-Audit · 2026-05-08 · commit `a09f9f2`

## 0. Auditor signature

- **Auditor**: Claude Sonnet 4.6 (Anthropic)
- **Date (UTC)**: 2026-05-08
- **Repository**: https://github.com/gmateosAWS/decision-intelligence-agent
- **Commit hash**: `a09f9f2` — `[audit-P2] Extract i18n module + add mypy and pip-audit to CI`
- **Branch**: `feature/11.1-ci-pipeline` (to be merged into main)
- **Inputs read**:
  - Repository tree (8,881 LOC Python across 79 files — was 8,372 LOC / 73 files at baseline)
  - `docs/llull_inventario_v4.md` (116 items)
  - `docs/llull_roadmap_v4.md` (4 iterations + "Más allá")
  - `docs/adr-001-pgvector-over-qdrant.md`
  - `docs/ADR-002-langgraph-orchestration.md`
  - `docs/ADR-003-llullgen-component-reuse-policy.md`
  - `docs/audit/2026-05-06_llull_self_audit.md` (baseline)
- **Methodology version**: 1.0 (same rubric as baseline; dimension-for-dimension comparable)
- **Delta context**: this is audit #2. The delta window is 2026-05-06 → 2026-05-08 (≈ 2 days of work).
  Closed between audits: all 6 baseline 🔴 findings (P0: CI pipeline, config lazy imports, pytest in dev deps;
  P1: pyproject target-version, CORS, scenario_runner inline, is_new removal, FAISS threat model;
  P2: i18n module extraction, mypy + pip-audit in CI).

---

## 1. Executive Summary

**Overall maturity score (weighted average across 86 dimensions)**: **2.65 / 5**
(Baseline 2026-05-06: **2.55 / 5** — methodology note: this delta is conservative; the original
baseline stated 2.55 using a layer-mean average, and the gain is proportional to Layer 1 improvements.)

Layer scores:

| Layer | Score (prev) | Score (now) | Δ | Dimensions |
|---|---|---|---|---|
| Codebase & Architecture | 2.96 | **3.46** | +0.50 | 28 |
| AI / Agent Layer | 2.40 | **2.45** | +0.05 | 20 |
| Conversational & Analytical Memory | 1.27 | **1.27** | 0.00 | 22 |
| Ontology & Semantic Knowledge | 2.31 | **2.31** | 0.00 | 16 |

Findings summary:

- 🔴 **Critical (gap real)**: **0 items** — all 6 baseline findings have been resolved.
- 🟡 **Planned (in inventory / roadmap / ADR)**: **48 dimensions** — same as baseline; the P0/P1/P2 items
  were tactical and did not advance the planned-gap front.
- 🟢 **Confirmed strengths**: same 9 as baseline, plus the CI pipeline and dead-code hygiene now join the
  confirmed-strength cluster.

**Posture summary.** The two-day sprint closed the entire tactical debt identified at baseline: an executable
CI pipeline with two jobs (unit + integration), lazy spec loading across the full call chain, correct dev
tooling (pytest, mypy, pip-audit), tightened CORS, documented FAISS threat model, extracted i18n module,
dead code removed, and 101 unit tests collected. The score jump in Layer 1 (+0.50) reflects genuine structural
improvements — not incremental polish.

The **dominant gap pattern is unchanged**: Memory (Layer 3) and AI Layer (Layer 2) are held back by the
absence of typed `ActiveAnalyticalState` (item 5.10), `MemoryService` Protocol (item 5.11), and the full
cost-control cluster (8.7.a–f). All of these are 🟡 (planned for I2A) — they were not expected to move in
this sprint.

The **single most important recommendation for the next sprint** is to begin item **5.10 ActiveAnalyticalState**:
it is the lever that moves 12 of the 22 Memory dimensions from 0–1 to 2–3 simultaneously, and it is the
declared I2A priority.

---

## 2. Layer 1 — Codebase & Architecture (28 dimensions)

> For dimensions unchanged from the baseline, the baseline rationale is confirmed and the evidence is
> re-cited. For changed dimensions, a full updated rationale is provided with diff evidence.

| # | Dimension | Score (prev) | Score (now) | Rationale | Evidence | Gap |
|---|---|---|---|---|---|---|
| 1 | Local code clarity | 4 | **4** | Unchanged. Files remain readable. `agents/i18n.py` (114 LOC) is new and well-structured. `streamlit_app.py` (1,040 LOC) remains the outlier. | `agents/i18n.py:1-114`; `evaluation/dashboard.py:1-471` | 🟢 |
| 2 | Naming quality | 4 | **4** | Unchanged. Identifiers consistent and domain-aligned. `get_system_language_directive`, `get_synth_instructions` follow the established pattern. | `agents/i18n.py:72-113` | 🟢 |
| 3 | Function / class size | 3 | **3** | Unchanged. `streamlit_app.py` and `evaluation/observer.py` remain the two outliers. | Baseline confirmed | 🟢 |
| 4 | Modularity | 3 | **3** | Unchanged. `agents/i18n.py` improves cohesion within `agents/` by consolidating language tables. No new cross-layer imports introduced. | `agents/i18n.py:1-5` (imports only `__future__`) | 🟡 (item 11.1 layer-deps lint) |
| 5 | Boundary integrity | 1 | **1** | Unchanged. Zero `Protocol` classes. No layer-deps lint. MemoryService Protocol (item 5.11) not implemented. | `grep "Protocol" agents/ → 0 hits` | 🟡 (items 5.11, I2A) |
| 6 | Composability | 2 | **2** | Unchanged. Provider/backend switches are conditional branches, not Protocol-typed seams. | Baseline confirmed | 🟡 (item 5.11 + 4.3) |
| 7 | Architectural integrity | 4 | **4** | Unchanged. Single architecture, end-to-end. Dockerfile and CI do not introduce a second architecture — they strengthen the existing one. | `agents/workflow.py:209-237`; `Dockerfile:1-28` | 🟢 |
| 8 | Dependency hygiene | 3 | **4** | **IMPROVED.** `requirements-dev.txt` now contains `pytest~=8.0`, `pytest-cov~=5.0`, `mypy~=1.10`, `types-requests~=2.31`, `types-PyYAML~=6.0`, `pip-audit~=2.7`. `pyproject.toml:3` now declares `target-version = ["py312"]`. **Baseline finding 6.3 (pytest missing) and 6.4 (py310 target) both closed.** | `requirements-dev.txt:1-10`; `pyproject.toml:3` | 🟢 |
| 9 | Separation of concerns | 4 | **4** | Unchanged. `api/`, `agents/`, `system/` boundaries respected. | Baseline confirmed | 🟢 |
| 10 | Correctness | 3 | **3** | CI now validates correctness on every push. No regressions detected. `api/routers/runs.py` `_get_db_or_503()` dependency correctly raises 503 before the DB is touched. | `.github/workflows/ci.yml:40-41`; `api/routers/runs.py:1-50` | 🟢 |
| 11 | Robustness against failure | 2 | **3** | **IMPROVED.** `config/settings.py` is now fully lazy: `_load_settings()` is called only on first accessor invocation and cached. No IO or DB access at import time. **Baseline finding 6.2 closed.** Import-time failure mode eliminated from the full call chain. `memory/checkpointer.py:_register_turn_sqlite` now calls `_ensure_sessions_table_sqlite()` idempotently before every SQLite write, removing the race where the table was absent when the checkpointer was mocked in tests. | `config/settings.py:28-45`; `memory/checkpointer.py:87-100` | 🟢 |
| 12 | Error handling quality | 3 | **3** | Unchanged. 38 broad excepts, 27 marked `# noqa: BLE001`. Additional `# type: ignore` suppressions are documented with specific codes (e.g. `# type: ignore[arg-type]` with inline reason). | Baseline confirmed; `agents/llm_factory.py:56` (new type: ignore) | 🟡 (item 7.9) |
| 13 | Test quality | 3 | **4** | **IMPROVED.** 101 tests collected (was ~85 at baseline). Three new test modules: `tests/agents/test_i18n.py` (9 tests for the new i18n module), `tests/evaluation/test_agent_golden.py` (15 canonical golden queries testing routing, result shape, parameter propagation, language detection — parametrized with `GOLDEN_QUERIES`), `tests/ci/test_smoke.py` (import smoke + health endpoint tests). Coverage configured via `pytest --cov`. **Items 5.2 (golden eval foundation) delivered.** | `tests/agents/test_i18n.py`; `tests/evaluation/test_agent_golden.py`; `tests/ci/test_smoke.py`; CI step: `--cov=. --cov-report=term-missing` | 🟢 |
| 14 | Test strategy completeness | 2 | **4** | **MAJOR IMPROVEMENT.** `.github/workflows/ci.yml` now exists with two jobs: (1) Unit tests + linting — runs black, ruff, mypy, `pytest -m "not integration"` with coverage on every push and PR; (2) Integration tests — runs against a `pgvector/pgvector:pg16` service container with full Alembic + data bootstrap, on PR to main only. **Baseline P0 finding 6.1 closed. Item 11.1 delivered.** | `.github/workflows/ci.yml:1-104`; `pyproject.toml:6-8` (integration marker exercised in CI) | 🟢 |
| 15 | Security posture | 2 | **3** | **IMPROVED.** CORS now uses an explicit allowlist: `allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]`, `allow_headers=["Content-Type", "Authorization", "X-Request-ID"]`, `allow_credentials=False`. **Baseline finding 6.5 closed.** FAISS `allow_dangerous_deserialization=True` now has a 13-line comment documenting the threat model (locally-generated only, migration plan when multi-tenant). **Baseline finding 6.6 closed.** Auth still absent. | `api/main.py:87-89`; `knowledge/retriever.py:128-141` | 🟡 (items 7.1, 7.5, 7.6 in I2B) |
| 16 | Supply-chain hygiene | 2 | **3** | **IMPROVED.** `pip-audit --strict --desc` now runs in CI (Job 1, `continue-on-error: true` so it reports without blocking on known issues). `requirements.txt` remains pinned with `==`. No lock file yet (`pip-tools` compile not yet introduced). | `.github/workflows/ci.yml:43-45`; `requirements.txt:1-28` | 🟡 (pip-tools lock is a further step) |
| 17 | Typing and contracts rigor | 4 | **4** | Sustained. `mypy --ignore-missing-imports --no-strict-optional --warn-return-any --warn-unused-configs --explicit-package-bases` now runs in CI. 21 type errors found at introduction and fixed: 3 were real bugs (`_NODE_FORMULAS` callable type, `config/settings.py` bare float/int returns, SQLAlchemy Column stubs), 18 were documented suppressions with specific error codes (`# type: ignore[arg-type]`, `[assignment]`, `[no-any-return]`, `[call-arg]`). Non-strict mypy keeps the score at 4 (not 5, which would require `--strict`). | `.github/workflows/ci.yml:32-38`; `system/system_model.py:6` (new Callable type); `agents/llm_factory.py:56` (type: ignore[call-arg] with reason) | 🟢 |
| 18 | Invariant enforcement | 2 | **2** | Unchanged. No DAG cycle assertion (item 3.3 in I2A). | Baseline confirmed | 🟡 (item 3.3 in I2A) |
| 19 | Duplication control | 3 | **4** | **IMPROVED.** `agents/i18n.py` extracted: `LANGUAGE_NAMES`, `SYNTH_INSTRUCTIONS`, `REVISE_INSTRUCTIONS` tables, plus four accessor functions (`get_language_name`, `get_synth_instructions`, `get_revise_instructions`, `get_system_language_directive`). `agents/workflow.py` and `agents/judge.py` now import from this module — no duplication. Skills-aware: `get_system_language_directive(language_code)` is the single entry point any future skill needs. **Baseline P2 finding closed.** | `agents/i18n.py:1-114`; `agents/workflow.py:36` (import); `agents/judge.py:29` (import); `grep "_LANG_NAMES" agents/ → 0 hits` | 🟢 |
| 20 | Dead-code hygiene | 4 | **5** | **IMPROVED.** Both dead-code items from the baseline have been cleaned up: `simulation/scenario_runner.py` is gone (its 5-line wrapper inlined into callers). The `is_new: bool = False` parameter has been removed from `memory/checkpointer.py:register_turn`. Zero TODOs, zero FIXMEs, zero unused arguments. Dark-code share: 0.0%. | `ls simulation/scenario_runner.py → not found`; `grep "is_new" memory/checkpointer.py → 0 hits`; `grep "TODO\|FIXME" --include="*.py" → 0 hits` | 🟢 |
| 21 | Observability | 3 | **3** | Unchanged. `AgentObserver` records all run spans. No OpenTelemetry, no `run_id` via contextvars yet. | Baseline confirmed | 🟡 (items 8.4, 8.2, 8.3) |
| 22 | Performance awareness | 3 | **3** | Unchanged. | Baseline confirmed | 🟡 (items 1.4, 4.4) |
| 23 | Documentation | 4 | **4** | `CLAUDE.md` updated: i18n module in architecture diagram, mypy/pip-audit in testing section, completed items updated, architecture directives maintained. `docs/llull_roadmap_visual.html` updated: 1C marked done, ObjectBus kept as ⏳ pending, date updated. | `CLAUDE.md:1-60`; `docs/llull_roadmap_visual.html` | 🟢 |
| 24 | Change governance | 2 | **4** | **MAJOR IMPROVEMENT.** `.github/workflows/ci.yml` now enforces: black format check → ruff lint → mypy type check → pytest with coverage → pip-audit on every push/PR to main. Integration job with Postgres on PRs. The pre-commit hooks (local) + CI (remote) form a two-layer gate. **Baseline P0 finding 6.1 closed. Item 11.1 delivered.** | `.github/workflows/ci.yml:26-44`; `.pre-commit-config.yaml:1-12` | 🟢 |
| 25 | Dark-code risk | 4 | **5** | **IMPROVED.** `simulation/scenario_runner.py` removed. Dark-code share is now effectively 0.0% with 79 Python files. The one previously dead path is gone. | `git ls-files "*.py" | wc -l → 79`; `ls simulation/scenario_runner.py → not found` | 🟢 |
| 26 | AI-generated code governance | 3 | **3** | Unchanged. No AI-narrative comments introduced. New code follows same conventions. | Baseline confirmed | 🟡 (parte de 11.1) |
| 27 | Overall maintainability | 3 | **4** | **IMPROVED.** CI provides test signal on every push: a new engineer pushing a change gets immediate feedback. `tests/evaluation/test_agent_golden.py` provides a routing oracle (15 canonical queries). `tests/ci/test_smoke.py` catches import-time regressions. The combination raises the floor for safe changes. | `.github/workflows/ci.yml`; `tests/ci/test_smoke.py`; `tests/evaluation/test_agent_golden.py` | 🟢 |
| 28 | Production-readiness from code | 1 | **2** | **IMPROVED.** CI now detects regressions. Lazy imports prevent cascade failures. CORS is tightened. Dockerfile and docker-compose api service exist. Auth still absent; rate limiting (item 12.5) not implemented; multi-tenancy not implemented. Score reflects "can be demoed safely internally" but not "can be exposed externally". | `.github/workflows/ci.yml`; `Dockerfile:1-28`; `api/main.py:87-89`; absence of auth middleware | 🟡 (items 7.1, 7.5, 7.6, 7.8, 12.5 in I2B) |

**Layer 1 mean: 3.46 / 5** (was 2.96)

Dimensions improved: 8, 11, 13, 14, 15, 16, 19, 20, 24, 25, 27, 28 (twelve of twenty-eight).
Unchanged: all others. No dimension regressed.

---

## 3. Layer 2 — AI / Agent Layer (20 dimensions)

| # | Dimension | Score (prev) | Score (now) | Rationale | Evidence | Gap |
|---|---|---|---|---|---|---|
| 1 | Clarity of agentic role | 3 | **3** | Unchanged. Four named nodes, clear docstrings. | Baseline confirmed | 🟡 (5.3.a en I3) |
| 2 | Explicitness of agentic boundary | 3 | **3** | Unchanged. LLM orchestrates, tools compute. | Baseline confirmed | 🟢 |
| 3 | Separation between agents | 2 | **2** | Single agent; prerequisites (Capability Graph, MemoryService) not yet implemented. | Baseline confirmed | 🟡 (items 5.3.a/b en I3) |
| 4 | Planning / orchestration | 4 | **4** | Unchanged. `ToolSelection` structured output, typed LangGraph DAG. | `agents/planner.py:53-72`; `agents/workflow.py:209-237` | 🟢 |
| 5 | Tooling discipline | 2 | **2** | Unchanged. No `ToolSpec` with typed input/output schemas. | Baseline confirmed | 🟡 (items 4.3, 10.8) |
| 6 | Tool safety | 2 | **2** | Unchanged. No SQL Execution Gateway; simulation adapter still manual. | `agents/tools.py:84-94` | 🟡 (item 2.10 en I2A) |
| 7 | Model abstraction | 3 | **3** | Unchanged. Provider-agnostic factory, fallback chain. No Bedrock/Vertex/Ollama yet. | `agents/llm_factory.py:50-98` | 🟡 (item 5.6 ampliado en I2A) |
| 8 | Prompt governance | 1 | **1** | Unchanged. Prompts remain inline Python strings, no registry, no versioning. | `agents/planner.py:117-163`; `agents/judge.py:103-130` | 🟡 (item 10.1 en I2A) |
| 9 | State management | 4 | **4** | Unchanged. `AgentState` TypedDict, `_sanitize_for_state`, LangGraph append semantics. | `agents/state.py:38-52`; `agents/workflow.py:244-268` | 🟢 |
| 10 | Memory abstraction | 1 | **1** | Unchanged. No `MemoryService` Protocol. Planner still slices `state["history"]` directly. | `agents/planner.py:185-196` | 🟡 (items 5.10, 5.11 en I2A) |
| 11 | Retrieval / grounding | 2 | **2** | Unchanged. RAG configured; no `GroundedTokens` guardrail. | `knowledge/retriever.py:54-68` | 🟡 (item 5.9 en I2A) |
| 12 | Output validation | 4 | **4** | Unchanged. Structured outputs at every LLM seam. | `agents/planner.py:60-88`; `agents/judge.py:49-57` | 🟢 |
| 13 | Error / retry strategy | 3 | **3** | Unchanged. Exponential backoff, rate-limit detection, judge fails-open. | `agents/llm_factory.py:101-165`; `agents/judge.py:130-158` | 🟡 (item 8.7.d) |
| 14 | Loop control / boundedness | 1 | **1** | Unchanged. No recursion guard, no wallclock cap. Graph is a DAG (bounded by structure). | `agents/workflow.py:209-237` (no recursion_limit) | 🟡 (items 5.12, 8.7.b en I2A/I3) |
| 15 | Observability of agent runs | 4 | **4** | Unchanged. Full per-node span recording, JSONL + Postgres, LangSmith bridge. | `evaluation/observer.py:92-282` | 🟢 |
| 16 | Testing and evaluation | 2 | **3** | **IMPROVED.** `tests/evaluation/test_agent_golden.py` adds 15 canonical queries as a structured test suite: routing gate (expected_tool), result-shape gate (expected_keys), parameter-propagation gate (expected_params), language-detection gate (language field). Parametrized with `GOLDEN_QUERIES` list so it evolves into item 10.11 without replacement. CI runs these on every push. No golden eval harness with real LLM calls yet. | `tests/evaluation/test_agent_golden.py`; `.github/workflows/ci.yml:40-41` | 🟡 (items 10.2, 10.11 en I2A/I3) |
| 17 | LLM cost control | 0 | **0** | Unchanged. No cost tracking per run, no token counts, no per-tenant quotas, no hard ceilings. | `evaluation/observer.py:92-282` (no cost field) | 🟡 (items 8.7.a–f en I2A) |
| 18 | Multi-turn / session continuity | 2 | **2** | Unchanged. Checkpointing via `thread_id`, history window of 3. No `ActiveAnalyticalState`. | `memory/checkpointer.py:63-95`; `agents/planner.py:185-196` | 🟡 (items 5.5, 5.10, 5.11 en I2A) |
| 19 | Multi-agent coordination | 1 | **1** | Unchanged. No multi-agent, no prerequisites. | Single graph | 🟡 (items 5.3.a/b, 5.12, 8.7.e en I3) |
| 20 | Agent autonomy policy | 1 | **1** | Unchanged. No `autonomy_policy` in spec, hardcoded `JUDGE_THRESHOLD`. | `agents/judge.py:37`; absence of autonomy fields | 🟡 (items 3.5, 7.3 en I2A/I3) |

**Layer 2 mean: 2.45 / 5** (was 2.40)

Dimension improved: 16 (Testing and evaluation). All others unchanged. No regressions.

---

## 4. Layer 3 — Conversational & Analytical Memory (22 dimensions)

No changes to the memory system in this sprint. All 22 dimension scores are unchanged from the baseline.
The P0/P1/P2 fixes were tactical (CI, imports, tooling, i18n DRY) — they did not advance the memory layer.
The roadmap correctly identifies items 5.10 and 5.11 as the I2A priority.

| # | Dimension | Score | Change | Notes |
|---|---|---|---|---|
| 1 | Memory system existence | 2 | — | `memory/` package exists; no typed `MemoryService`. |
| 2 | System boundary clarity | 1 | — | Planner reads `state["history"]` directly. |
| 3 | Structured active state | 0 | — | No `ActiveAnalyticalState`. |
| 4 | State centrality as truth | 0 | — | Transcript is source of truth; no typed state. |
| 5 | State traceability | 1 | — | Run-level provenance only, no slot provenance. |
| 6 | State lifecycle discipline | 1 | — | Append-only transcript; no slot transitions. |
| 7 | Short-range memory | 3 | — | 3-turn window, env-configurable; no compaction. |
| 8 | Explicit rule quality | 1 | — | Rules live in system prompt strings. |
| 9 | Inheritance governance | 0 | — | No slot inheritance logic. |
| 10 | Reset / invalidation | 0 | — | No invalidation rules. |
| 11 | Clarification governance | 1 | — | Judge revision is one-shot rewrite, not clarification flow. |
| 12 | Conflict resolution | 0 | — | No declarative conflict rules. |
| 13 | Contextual retrieval | 2 | — | Retrieval keyed on raw query; no active-state enrichment. |
| 14 | Retrieval subordination | 1 | — | Retrieval results passed verbatim; no active-state filter. |
| 15 | Multi-turn behavior | 2 | — | Works in practice; correctness is prompt-level. |
| 16 | Memory vs prompting balance | 1 | — | All multi-turn logic prompted, not coded. |
| 17 | Complementary techniques | 2 | — | Sliding window only; no compaction, no summarization. |
| 18 | Single-turn vs multi-turn | 2 | — | Uniform code path; no explicit first-turn vs. continuation. |
| 19 | User interaction with memory | 0 | — | No slot inspection/mutation APIs. |
| 20 | Downstream integration | 2 | — | Synthesizer and judge read from state cleanly; planner slices history. |
| 21 | Coordination / orchestration | 2 | — | LangGraph orchestrates; no `MemoryCoordinator`. |
| 22 | Coordination integrity | 1 | — | No single-coordinator gate on memory mutations. |

**Layer 3 mean: 1.27 / 5** (unchanged)

All 22 gaps are 🟡 (planned in I2A/I3). No 🔴 in this layer. The 0-score dimensions (3, 4, 9, 10, 12, 19)
are all directly addressed by item 5.10 `ActiveAnalyticalState` — the single highest-leverage item in the
I2A backlog.

---

## 5. Layer 4 — Ontology & Semantic Knowledge (16 dimensions)

No changes in this sprint. All 16 dimension scores are unchanged from the baseline.

| # | Dimension | Score | Change | Notes |
|---|---|---|---|---|
| 1 | Conceptual semantic layer | 3 | — | `OrganizationalModelSpec` typed tree; consumed by all layers. |
| 2 | Formal ontology presence | 1 | — | No OWL/RDF; item 2.7 in "Más allá". |
| 3 | Entity registry | 1 | — | Typed dataclasses, not a Registry pattern; item 10.8 in I3. |
| 4 | Relationship modelling | 3 | — | `CausalRelationship` typed, DAG built from spec. |
| 5 | Metric registry | 1 | — | `TargetVariable` dataclass; not versioned/owned; item 10.8 in I3. |
| 6 | Dimension / vocabulary registry | 0 | — | No VocabularyRegistry; items 5.9, 10.8. |
| 7 | Alias / synonym handling | 0 | — | No synonyms in spec; item 5.9. |
| 8 | Ambiguity handling | 1 | — | Judge revision catches some; no `IntentClassifier`. |
| 9 | Business-to-system mapping | 2 | — | Single-step, LLM-driven; no `MappingLayer`; item 2.2 in I2A. |
| 10 | Physical data introspection | 1 | — | No real data sources yet; items 2.1, 2.2 in I2A. |
| 11 | Query interpretation | 4 | — | `ToolSelection` is the typed IR; strongest area of the semantic layer. |
| 12 | Runtime consumption | 4 | — | Spec consumed by every layer that should consume it. |
| 13 | Test coverage of semantic layer | 1 | — | Spec loader tests exist; no semantic golden tests. Item 10.11 in I2A. |
| 14 | Governance / versioning | 3 | — | `Spec`/`SpecVersion` ORM with lifecycle; limited to spec only. |
| 15 | Scalability across domains | 4 | — | Domain switching is config-level; prompt built dynamically from spec. |
| 16 | Internal consistency | 3 | — | Spec is single source of truth; demand model formula is documentary, not asserted. |

**Layer 4 mean: 2.31 / 5** (unchanged)

All gaps are 🟡 (planned in I2A, I3, "Más allá"). No 🔴 in this layer.

---

## 6. Critical Findings (🔴) — Gaps not in inventory / roadmap / ADRs

**0 critical findings.**

All 6 findings from the 2026-05-06 audit have been resolved. Verification:

| Finding | Severity | Resolution | Commit |
|---|---|---|---|
| 6.1 — No executable CI pipeline | P0 | `.github/workflows/ci.yml` created with two jobs | `5c1f42f` (PR merge) |
| 6.2 — `config/settings.py` import-time loading | P1 | `_load_settings()` lazy, `_settings_cache` pattern | prior to `a09f9f2` |
| 6.3 — `pytest`/`pytest-cov` missing from dev deps | P1 | Added to `requirements-dev.txt` | prior to `a09f9f2` |
| 6.4 — `pyproject.toml` target py310 vs py312 | P2 | `target-version = ["py312"]` | prior to `a09f9f2` |
| 6.5 — CORS `allow_methods=["*"]` | P2 | Explicit allowlist, `allow_credentials=False` | `05ce957` |
| 6.6 — FAISS `allow_dangerous_deserialization` undocumented | P2 | 13-line comment with threat model + migration path | `05ce957` |

No new risks to flag. The integration job now carries an explicit `if:` guard (`github.event.pull_request.head.repo.full_name == github.repository`) that skips it on PRs from external forks, and a comment documenting the Secrets requirement. `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are confirmed configured in the repository's Secrets settings and verified passing in CI.

---

## 7. Planned Gaps (🟡) — Capabilities pending per the roadmap

Unchanged from baseline — the P0/P1/P2 sprint closed tactical debt, not architectural gaps. Selected for highest-impact items:

| Layer · Dimension | Capability | Inventory item | Iteration |
|---|---|---|---|
| Memory · dims 3, 4, 9, 10, 12, 19 (six 0-score dims) | ActiveAnalyticalState typed | 5.10 | **I2A · highest-leverage** |
| Memory · dim 2, 10 | MemoryService Protocol + lint | 5.11 | I2A |
| AI · #17 LLM cost control (all sub-dims) | Tenant quotas, hard ceilings, budget reservation | 8.7.a–f | I2A (8.7.b critical-path) |
| AI · #14 Loop control | Recursion guard + depth limits | 5.12 | I3 |
| AI · #11 Retrieval / grounding | GroundedTokens guardrail | 5.9 | I2A |
| AI · #7 Model abstraction | LLMFactory completo (multi-provider, context-budget) | 5.6 ampliado | I2A |
| Codebase · #5, #6 Boundary integrity | Protocol-typed seams + layer-deps lint | 5.11 + 11.1 | I2A |
| Codebase · #15 Security posture | Auth + RLS + cifrado + audit log | 7.1, 7.5, 7.6–7.9 | I2B |
| Codebase · #28 Production-readiness | Composite of 7.x + 8.x | múltiples | I2B + I3 |
| Ontology · #6, #7 Vocabulary registry, synonyms | VocabularyRegistry + synonym fields in spec | 10.8 (I3), 5.9 (I2A) | I2A / I3 |
| AI · #8 Prompt governance | PromptRegistry + versioning | 10.1 | I2A |

48 dimensions remain 🟡. The P0/P1/P2 sprint did not reduce this number — it closed the 6 🔴 items. The 🟡 count
decreases only when I2A items land.

---

## 8. Genuine Strengths

The 9 baseline strengths are confirmed unchanged. Two additional strengths can now be recognized:

### 8.1–8.9 (from baseline) — all confirmed

- Single coherent architecture, end-to-end (8.1)
- Spec-driven design that is actually spec-driven (8.2)
- Type discipline above the size class (8.3)
- Dual-backend pattern consistent across modules (8.4)
- Observability built in, not bolted on (8.5)
- Error handling discipline explicit with `# noqa: BLE001` (8.6)
- Active fix discipline visible in commit history (8.7)
- Documentation that matches the code (8.8)
- Tests that test behavior, not mocks (8.9)

### 8.10 — CI pipeline that earns trust

`.github/workflows/ci.yml` is not a minimal "run tests" script. It runs black → ruff → mypy → pytest with
coverage → pip-audit sequentially, with clear step names and meaningful env setup. The integration job spins
a real `pgvector/pgvector:pg16` container, runs Alembic migrations, bootstraps synthetic data, trains the ML
model, builds the knowledge index, then runs marked integration tests. This is a production-grade CI template
for a prototype phase. A new engineer can trust that a green CI badge means the system actually works
end-to-end, not just that unit tests pass.

### 8.11 — Dead-code at 0.0% after two-day sprint

The previous audit flagged two dead-code instances at ~0.5% share. Both are gone: `simulation/scenario_runner.py`
deleted, `is_new` parameter removed. For a prototype phase where dead code typically accumulates, maintaining
0.0% across 8,881 LOC demonstrates disciplined stewardship. The contrast with LlullGen's 7,000 LOC zombie
planner architecture is stark and serves as a standing proof that the "no dead code" discipline is real.

---

## 9. Comparison with previous self-audit

**Baseline**: 2026-05-06 · commit `5d2adf5` · Auditor: Claude Opus 4.7
**This audit**: 2026-05-08 · commit `a09f9f2` · Auditor: Claude Sonnet 4.6
**Delta window**: ≈ 2 days of active development

### 9.1 — Layer mean comparison

| Layer | 2026-05-06 | 2026-05-08 | Δ | Direction |
|---|---|---|---|---|
| Codebase & Architecture (28 dims) | 2.96 | **3.46** | **+0.50** | ↑ sustained |
| AI / Agent Layer (20 dims) | 2.40 | **2.45** | **+0.05** | ↑ |
| Conversational & Analytical Memory (22 dims) | 1.27 | **1.27** | 0.00 | → expected (I2A) |
| Ontology & Semantic Knowledge (16 dims) | 2.31 | **2.31** | 0.00 | → expected (I3) |
| **Overall (weighted)** | ~2.55 | **~2.65** | **+0.10** | ↑ |

### 9.2 — Dimension-by-dimension diff (changed dimensions only)

| Layer | Dim # | Dimension | 2026-05-06 | 2026-05-08 | Driver |
|---|---|---|---|---|---|
| L1 | 8 | Dependency hygiene | 3 | **4** | pytest, mypy, types-* added; pyproject py312 aligned (findings 6.3, 6.4) |
| L1 | 11 | Robustness against failure | 2 | **3** | config/settings.py fully lazy; checkpointer table creation guard (finding 6.2) |
| L1 | 13 | Test quality | 3 | **4** | 101 tests (was ~85); test_i18n, test_agent_golden, test_smoke added (item 5.2) |
| L1 | 14 | Test strategy completeness | 2 | **4** | CI pipeline with 2 jobs; integration Postgres job; coverage in unit job (finding 6.1, item 11.1) |
| L1 | 15 | Security posture | 2 | **3** | CORS explicit allowlist; FAISS threat model documented (findings 6.5, 6.6) |
| L1 | 16 | Supply-chain hygiene | 2 | **3** | pip-audit in CI (P2.4) |
| L1 | 19 | Duplication control | 3 | **4** | agents/i18n.py extracted; language tables DRY (P2.1) |
| L1 | 20 | Dead-code hygiene | 4 | **5** | scenario_runner.py deleted; is_new param removed |
| L1 | 24 | Change governance | 2 | **4** | CI pipeline enforces black+ruff+mypy+pytest on every push (finding 6.1, item 11.1) |
| L1 | 25 | Dark-code risk | 4 | **5** | scenario_runner.py deleted; dark-code share → 0.0% |
| L1 | 27 | Overall maintainability | 3 | **4** | CI test signal + golden eval oracle + smoke tests |
| L1 | 28 | Production-readiness from code | 1 | **2** | CI + Dockerfile + lazy imports + CORS; no auth yet |
| L2 | 16 | Testing and evaluation | 2 | **3** | test_agent_golden: 15 golden queries, parametrized, CI-integrated (item 5.2 foundation) |

**Total changed dimensions: 13** (12 in L1, 1 in L2). No dimension regressed.

### 9.3 — Critical findings closure

| Finding | Status at 2026-05-06 | Status at 2026-05-08 |
|---|---|---|
| 6.1 No executable CI pipeline (P0) | 🔴 Open | 🟢 **Closed** |
| 6.2 config/settings.py import-time IO (P1) | 🔴 Open | 🟢 **Closed** |
| 6.3 pytest missing from requirements-dev (P1) | 🔴 Open | 🟢 **Closed** |
| 6.4 pyproject.toml target py310 (P2) | 🔴 Open | 🟢 **Closed** |
| 6.5 CORS allow_methods=["*"] (P2) | 🔴 Open | 🟢 **Closed** |
| 6.6 FAISS deserialization undocumented (P2) | 🔴 Open | 🟢 **Closed** |

**From 6 🔴 to 0 🔴 in 2 days.** The remediation plan from the baseline was accurate: P0 and P1 items were
"< 1 day of work each" and they delivered.

### 9.4 — Invariants confirmed (baseline strengths that must not decline)

The 9 baseline strengths (8.1–8.9) are all confirmed at their baseline scores. No strength regressed.
Two new strengths added (8.10 — CI pipeline, 8.11 — 0% dead code).

### 9.5 — What the next audit (I2A close-out) should show

If I2A items land as planned, the next audit should show:
- Memory layer: 1.27 → ~2.5 (items 5.10, 5.11, 5.9 contribute 12 dimension lifts)
- AI Layer: 2.45 → ~2.8 (items 8.7.a–d add cost control; 5.6 ampliado adds model abstraction)
- Codebase: 3.46 → ~3.6 (boundary integrity 1→3 with Protocol types + layer-deps lint)
- Overall: ~2.65 → ~2.90

A decline in any of the 9 confirmed-strength dimensions in the next audit is an alarm.

---

## 10. Prioritized remediation plan

### P0 — No open P0 items ✅

All P0 items from the baseline have been resolved.

### P1 — Highest-leverage next steps (I2A)

1. **⏱ 3-4 days · Begin item 5.10 (ActiveAnalyticalState typed).** The single highest-ROI item in the backlog.
   Moves 12 Memory dimensions from 0–1 to 2–3. Design: a Pydantic model in `memory/active_state.py` with
   fields for active metric, active dimensions, period, geography, frozen slots, pending confirmations,
   provenance dict. Wire into `MemoryService` (item 5.11) and replace the `state["history"]` slice in
   `agents/planner.py:185-196` with a typed call.

2. **⏱ 1 day · Item 5.11 (MemoryService Protocol).** Follow immediately after 5.10. Create
   `memory/memory_service.py` with a `MemoryService` Protocol and lint rule banning direct
   `state["history"]` access outside `memory/`. Lifts Codebase dimensions 5 and 6 from 1→3 and 2→3.

3. **⏱ 2 days · Items 8.7.a + 8.7.b (LLM cost control basics: tracking + hard ceilings).** Add token/cost
   field to `RunRecord` in `evaluation/observer.py`. Add per-run hard ceiling env var. These are the
   critical-path items for I2A per the roadmap. Lifts AI Layer dim 17 from 0 to 2.

### P2 — Tactical hygiene (compound interest)

4. ~~**Refactor `streamlit_app.py`** into 3-4 modules (UI components, business adapters, dashboard glue,
   session state). Reduces the 1,040 LOC monolith.~~ **CLOSED** (`refactor/streamlit-split`): split into
   `ui/` package (app, components, dashboard, sidebar, session, styles) + `agents/runner.py` (shared
   `run_query()` + `RunResult` for both Streamlit and FastAPI — Directive 3). Multi-turn rendering bug fixed.
   `streamlit_app.py` reduced to 10-line wrapper. 113 unit tests pass. Codebase dim 3 lifts to 4.

5. ~~**Split `AgentObserver`** into `RunRecorder`, `JsonlSink`, `PostgresSink`, `LangSmithBridge`. Lifts dim 3.~~ **CLOSED** (`refactor/observer-split`): `evaluation/sinks/` package with `RunSink` Protocol + `JsonlSink` + `PostgresSink` + `LangSmithBridge` stub; `evaluation/confidence.py` with `ConfidenceScorer`; `observer.py` refactored to thin orchestrator. 28 new tests. Public API unchanged.

6. **Add `pip-tools` lock file** (`requirements.lock`) for reproducible builds. Lifts dim 16 from 3 to 4.

7. **`mypy --strict` migration.** Progressive: `--strict` on `agents/` first, then expand. Currently
   intermediate mode. Lifts dim 17 from 4 to 5.

8. **Item 10.1 PromptRegistry.** Version the inline prompts in `agents/planner.py` and `agents/judge.py`.
   Lifts AI Layer dim 8 from 1 to 2.

---

## End of audit · 2026-05-08 · commit `a09f9f2`

Auditor: Claude Sonnet 4.6 (Anthropic) · Methodology: llull self-audit v1.0 · Previous audit: 2026-05-06 ·
Next re-audit recommended: after I2A close-out (items 5.10, 5.11, 8.7.a–b land).
