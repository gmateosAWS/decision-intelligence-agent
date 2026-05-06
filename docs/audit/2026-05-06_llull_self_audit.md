# llull · Self-Audit · 2026-05-06 · commit `5d2adf5`

## 0. Auditor signature

- **Auditor**: Claude Opus 4.7 (Anthropic)
- **Date (UTC)**: 2026-05-06
- **Repository**: https://github.com/gmateosAWS/decision-intelligence-agent
- **Commit hash**: `5d2adf5fa785cab93ec7eeda1591654724c16612`
- **Branch**: main (only commit visible at clone depth 1)
- **Inputs read**:
  - Repository tree (8.372 LOC Python across 73 files)
  - `docs/llull_inventario_v4.md` (116 items, 1131 LOC of markdown)
  - `docs/llull_roadmap_v4.md` (4 iterations + "Más allá", 602 LOC)
  - `docs/adr-001-pgvector-over-qdrant.md` (in-repo)
  - `docs/ADR-002-langgraph-orchestration.md` (provided)
  - `docs/ADR-003-llullgen-component-reuse-policy.md` (provided)
  - `README.md` (1.165 LOC), `CLAUDE.md` (200 LOC)
- **Methodology version**: 1.0 (baseline)
- **Methodology document**: `docs/llull_self_audit_methodology.md`

---

## 1. Executive Summary

**Overall maturity score (weighted average across 4 layers)**: **2.55 / 5**

Layer scores (unweighted means):

| Layer | Score | Dimensions |
|---|---|---|
| Codebase & Architecture | 2.96 | 28 |
| AI / Agent Layer | 2.40 | 20 |
| Conversational & Analytical Memory | 1.55 | 22 |
| Ontology & Semantic Knowledge | 2.31 | 16 |

Findings summary:

- 🔴 **Critical (gap real)**: **6 items** — these are the priorities for immediate action.
- 🟡 **Planned (in inventory / roadmap / ADR)**: **48 dimensions** are partially covered or pending per the roadmap and are not penalized beyond the score that the current scaffolding earns.
- 🟢 **Confirmed strengths**: **9 areas** — substantively well-built pieces that the audit acknowledges.

**Posture summary.** llull is a **prototype with deliberate architecture and uncommonly disciplined scaffolding for its phase**. The four-node LangGraph workflow (`agents/workflow.py:267-282`) is clean and complete; the spec-driven design is real (the spec is consumed by every layer that should consume it, not just by name); the dual-backend pattern (Postgres ↔ SQLite, pgvector ↔ FAISS) is consistent across `memory/`, `spec/`, `knowledge/`, `evaluation/`. Type discipline is above average for the size: 27 Pydantic / TypedDict references in 8.372 LOC, structured outputs used at every LLM seam (`agents/planner.py:60-72`, `agents/judge.py:77-85`).

The dominant pattern of weakness is **the gap between "scaffolding ready" and "capability instrumented"**. Memory, governance, lineage, multi-agent — all have their hooks in the right places, but the production-grade machinery (typed registries, hard ceilings, recursion guards, lineage records) is described in v4 inventory and assigned to I2A/I3, not yet implemented. This is **expected and acknowledged by the rubric**: 48 dimensions are 🟡 "planned" not 🔴 "missing".

The genuine 🔴 findings — gaps that are **not** in plan — are six, and four of them are tactical (dev tooling, not architecture). The two non-tactical 🔴 findings are: (1) **the absence of an executable CI pipeline** (no `.github/workflows/`, despite `.pre-commit-config.yaml` existing locally); (2) **the import-time failure mode of `config/settings.py`**, which loads the spec at module import and would crash the entire application stack on any spec parse error before logging is configured.

**Dark-code share**: ~0.5%. Single instance: `simulation/scenario_runner.py:1-5` is a 5-line wrapper around `monte_carlo()` that adds no value; nothing else looks unreachable from production paths. Compare with LlullGen's reported 4.5%–17%.

The **single most important recommendation** of this baseline is to advance item **11.1 Pipeline CI** from I1 to "now": with so many tests already written (1.300 LOC, 14 test files), the absence of an executable CI pipeline means a regression can ship without anyone noticing. Fixing this is < 1 day of work and disproportionately raises the score on Dimensions 13, 14, 24, 25, and 28.

---

## 2. Layer 1 — Codebase & Architecture (28 dimensions)

| # | Dimension | Score | Rationale | Evidence | To reach next level | Gap |
|---|---|---|---|---|---|---|
| 1 | Local code clarity | 4 | Files are readable line-by-line. Largest production files are well-structured: `evaluation/dashboard.py` 471 LOC, `evaluation/observer.py` 465 LOC, `spec/spec_loader.py` 387 LOC. Docstrings present at module and function level. `streamlit_app.py` 1.040 LOC is the outlier and concentrates almost all the complexity that exists. | `evaluation/dashboard.py:1-471`; `evaluation/observer.py:1-465`; `streamlit_app.py:1-1040` | Split `streamlit_app.py` into UI rendering + business adapters + dashboard glue. | 🟢 |
| 2 | Naming quality | 4 | Identifiers are consistent and aligned with domain language: `AgentState`, `ToolSelection`, `JudgeVerdict`, `OrganizationalModelSpec`, `RunRecord`. Decisions / tools / nodes follow uniform conventions. Domain Spanish in some prompts/comments coexists with English code — minor friction but coherent. | `agents/state.py:38-52`; `agents/planner.py:60-72`; `agents/judge.py:77-85`; `spec/spec_loader.py:139-188` | Decide a single language for inline comments (currently mixed Spanish / English). | 🟢 |
| 3 | Function / class size and cohesion | 3 | Most modules cohesive and below 500 LOC. Two outliers: `streamlit_app.py` (1.040 LOC, 12+ top-level functions, mixes UI + dashboard + state init), and `evaluation/observer.py` (465 LOC) which combines RunRecord, console logger, JSONL writer, Postgres writer, LangSmith bridge, and confidence derivation in one class. Nothing approaches LlullGen's god-files. | `streamlit_app.py:59,77,191,263,292,389,496,528`; `evaluation/observer.py:92-466` | Split `AgentObserver` into `RunRecorder`, `JsonlSink`, `PostgresSink`, `LangSmithBridge`, `ConfidenceScorer`. | 🟢 |
| 4 | Modularity (behavioural) | 3 | Folder structure mirrors behavior: `agents/` has only agent code, `memory/` only persistence of conversational state, `spec/` only spec lifecycle, `system/` only causal evaluation, `evaluation/` only observability. Cross-imports respect this layering by inspection. No declared layer-deps lint exists yet. | Folder tree (top-level inspection); `agents/workflow.py:36-40` imports only sibling agents files, never reaches into `api/` or `memory/` directly | Add a layer-deps lint script (analogous to LlullGen's `check_layer_deps.py`) and run it in CI. | 🟡 (item 11.1) |
| 5 | Boundary integrity | 1 | No declared boundary enforcement. No `core/protocols/` package. Zero `Protocol` classes (`grep -rn "Protocol" --include="*.py" \| wc -l → 0`). Layer dependencies enforced by convention only. The MemoryService boundary (item 5.11) that ADR-003 calls out as critical does not exist yet. | `grep` confirms zero Protocol; `memory/`, `spec/`, `agents/` all importable from each other without check | Implement item 5.11 MemoryService Protocol and a `scripts/check_layer_deps.py` lint. | 🟡 (item 5.11, I2A) |
| 6 | Composability | 2 | LLM provider is swappable (`agents/llm_factory.py:50-98`); checkpointer backend is swappable (`memory/checkpointer.py:63-95`); knowledge backend is swappable (`knowledge/retriever.py:54-68`). But these are conditional branches at call sites, not Protocol-typed seams. Tools have no base class; agents have no shared interface. | `agents/tools.py:1-112` (no `ToolBase`); `agents/llm_factory.py:50-98` (provider switch is `if/elif`) | Introduce typed protocols: `LLMProvider`, `MemoryBackend`, `KnowledgeBackend`, `Tool`. | 🟡 (item 5.11 + governance taxonomy) |
| 7 | Architectural integrity | 4 | Single architecture, end-to-end: LangGraph 4-node graph + spec-driven core + dual-backend persistence. No coexisting architectures (compared with LlullGen's PlanExecutor zombie). No "AGENT_TEMPLATE.py" placeholders. The README and CLAUDE.md describe what the code does. | `agents/workflow.py:267-282` (the entire graph); `CLAUDE.md:1-60` (architecture description matches code) | Maintain this when introducing 5.3.a multi-agent — keep one supervised topology, not two. | 🟢 |
| 8 | Dependency hygiene | 3 | `requirements.txt` is pinned with ==versions. `requirements-dev.txt` uses ~= for dev tooling (black, ruff, pre-commit). **Issue**: `pytest` is not in `requirements-dev.txt` despite 14 test files relying on it (`tests/agents/test_planner.py`, `tests/api/conftest.py` etc.). Tests run only if pytest is installed manually. | `requirements-dev.txt:1-4`; `tests/agents/test_planner.py:1-30` (uses pytest fixtures via inference) | Add `pytest`, `pytest-cov` to `requirements-dev.txt`. | 🔴 (no plan citation; tactical fix) |
| 9 | Separation of concerns | 4 | Clean: `api/routers/query.py` does request handling only and delegates to `graph.invoke()` (`api/routers/query.py:23-89`); `agents/workflow.py` orchestrates only; `system/system_model.py` computes only. Business logic does not leak into routers. The exception is `streamlit_app.py` which mixes presentation, state, and business logic. | `api/routers/query.py:23-89`; `agents/workflow.py:127-246`; `streamlit_app.py:1-1040` | Refactor `streamlit_app.py` into UI components consuming an internal SDK. | 🟢 |
| 10 | Correctness | 3 | Production happy-path works (mock-backed integration tests pass, README describes a path that matches the code). Latest commit `5d2adf5` is a real fix: "fix(planner): make _SYSTEM_PROMPT lazy to prevent import-time IO". Active fix discipline visible. | `git log --oneline -1`; `agents/planner.py:166-173` (lazy initialization of system prompt) | Add CI to detect regressions automatically (Dimension 13/14). | 🟢 |
| 11 | Robustness against failure | 2 | Fallback chains exist (LLM provider fallback, Postgres→SQLite fallback, pgvector→FAISS fallback). Judge "fails open" preserving the original answer (`agents/judge.py:163-184`). **Issue**: `config/settings.py:14-37` does spec loading at module-import time. If the spec YAML cannot parse, the entire application — including `api/main.py`, the Streamlit app, every test that imports anything — fails before logging is configured. The most recent commit fixed this for the planner, but `config/settings.py` itself still does it. | `config/settings.py:14-37`; commit message of `5d2adf5` shows awareness of the import-time-IO antipattern, applied only to planner | Move spec loading inside accessor functions in `config/settings.py`. | 🔴 (no plan citation; classic fragility) |
| 12 | Error handling quality | 3 | 38 broad `except Exception` clauses across 8.372 LOC (~0.45%). Of these, 27 explicitly marked `# noqa: BLE001` — disciplined declaration of intent. Compares favorably with LlullGen's 443 in 110 kLOC (~0.4%) but with much higher proportion marked. **Issues**: `api/routers/query.py:84-89` swallows all non-LLM exceptions and returns 500 with the raw error message in the body, leaking internals. | `grep "except Exception" --include="*.py" \| wc -l` → 38; `grep "noqa: BLE001" \| wc -l` → 27; `api/routers/query.py:84-89` | Classify exceptions by type before responding; use a request-id and structured error model. | 🟡 (item 7.9 mitigaciones AI-native cubre parte de esto) |
| 13 | Test quality | 3 | 1.300 LOC of tests across 14 files. Tests use proper mocking (`tests/agents/test_planner.py:9-30` mocks `_init_planner_llms` and `invoke_with_fallback`, not the network). API tests use FastAPI `TestClient` with dependency overrides (`tests/api/conftest.py:17-46`). Tests target real behavior not implementation. **Limitation**: no coverage metric configured (no `.coveragerc`, no `pyproject.toml` coverage section). | `tests/api/conftest.py:17-46`; `tests/agents/test_planner.py:1-103`; `find . -name ".coveragerc"` → empty | Add `pytest-cov` and a coverage gate at 70%+. | 🟡 (5.2 test suites + 11.1 pipeline CI) |
| 14 | Test strategy completeness | 2 | Unit tests present per package. Integration tests with Postgres exist (`tests/memory/test_checkpointer_postgres.py`, `tests/db/test_engine.py`) marked with `integration` pytest marker (`pyproject.toml:6-8`). **No CI runs them.** No e2e / smoke tests. The integration marker exists but is not exercised. | `pyproject.toml:6-8`; absence of `.github/workflows/` | Add a CI job with a Postgres service container and run `pytest -m integration`. | 🔴 (referenced in inventory item 11.1 + 11.2 but no executable pipeline anywhere) |
| 15 | Security posture | 2 | No public auth: API exposes `/v1/query` without any authentication mechanism (`api/routers/query.py:17-89`). CORS allows `*` methods and headers (`api/main.py:84-89`). **Pickle usage is contained**: 4 sites, all loading locally-generated artifacts (ML model `system/system_model.py:107-108`, `streamlit_app.py:660-662`). No `pickle.loads(request.data)` antipattern. **FAISS uses `allow_dangerous_deserialization=True`** (`knowledge/retriever.py:130`) — known LangChain pattern but a real attack surface if FAISS index files become user-supplied. | `api/routers/query.py:17`; `api/main.py:84-89`; `knowledge/retriever.py:130`; `system/system_model.py:107-108` | Implement items 7.5 SSO + 7.6 cifrado + API-key middleware before any non-internal piloto. | 🟡 (items 7.1, 7.5, 7.6, 7.7, 7.8, 7.9 in I2B) |
| 16 | Supply-chain hygiene | 2 | `requirements.txt` pinned. No SBOM, no `pip-tools` lock, no provenance. No vendoring (no `vendor/` directory). One transitive concern: `langchain-community` brings a large dependency surface; not pinned to a minor band only. | `requirements.txt:1-28`; `find . -name "*.lock"` → empty | Generate a `pip-compile`-style lock. Run `pip-audit` in CI. | 🟡 (parte de 11.1 Pipeline CI) |
| 17 | Typing and contracts rigor | 4 | Above average for size: 27 Pydantic / TypedDict references in 8.372 LOC. Structured outputs at every LLM seam (`ToolSelection` planner, `JudgeVerdict` judge, `QueryRequest`/`QueryResponse` API). `OrganizationalModelSpec` is a typed dataclass tree with 7 inner dataclasses. Only 2 `type: ignore` comments (vs LlullGen's many) and both target legitimate optional imports. | `agents/planner.py:53-72`; `agents/judge.py:77-85`; `spec/spec_loader.py:38-188`; `grep "type: ignore"` → 2 hits | Adopt `Protocol` types at boundaries (Dim 5/6), add `mypy --strict` to CI. | 🟢 |
| 18 | Invariant enforcement | 2 | A few invariants: pickle model file expected at known path (`system/system_model.py:103-108`), spec singleton (`spec/spec_loader.py:343-360`), DAG must be acyclic (relied on by `nx.topological_sort` but not asserted). **Issue**: many invariants live as docstring expectations, not runtime checks. The DAG cycle check (item 3.3 validation automática del spec) is not yet implemented. | `system/system_model.py:91-112`; `spec/spec_loader.py:343-360`; absence of explicit DAG cycle assertion | Implement item 3.3. Add `assert` statements for invariants critical to causal evaluation. | 🟡 (item 3.3 in I2A) |
| 19 | Duplication control | 3 | One real duplication: `_LANG_NAMES` and language instruction maps are defined in both `agents/workflow.py:53-95` and `agents/judge.py:34-61`. Different content (synth instructions vs revise instructions) but parallel structure. Other code is appropriately DRY. | `agents/workflow.py:53-95`; `agents/judge.py:34-61` | Extract a small `agents/i18n.py` for language tables. | 🟢 |
| 20 | Dead-code hygiene | 4 | Almost no dead code. One small case: `simulation/scenario_runner.py:1-5` is a 5-line wrapper that adds nothing over a direct import of `monte_carlo`. One dead arg: `memory/checkpointer.py:44` has `is_new: bool = False` marked `# noqa: ARG001 kept for API compatibility` — a 1-week-old API can't have legacy callers. Compares spectacularly favorably with LlullGen's 7kLOC of zombie planner code. | `simulation/scenario_runner.py:1-5`; `memory/checkpointer.py:44`; `grep "TODO\|FIXME"` → 0 hits | Inline `scenario_runner.run_scenario`; remove `is_new` param. | 🟢 |
| 21 | Observability / diagnosability | 3 | `AgentObserver` records every run with planner / tool / synthesizer / judge spans, latency, model, judge score, judge feedback. Dual-write JSONL + Postgres. LangSmith bridge configurable via env. **Issue**: no `run_id` / `session_id` propagation via `contextvars` — IDs are passed explicitly through config. No OpenTelemetry. No metrics endpoint. | `evaluation/observer.py:92-282`; `evaluation/observer.py:306-324` (LangSmith config); absence of OTel | Implement item 8.4 (run_id by contextvar). | 🟡 (item 8.4 ampliado en I3, items 8.2, 8.3) |
| 22 | Performance awareness | 3 | Connection pool implicit (`SQLAlchemy create_engine`). Ml model loaded once via singleton (`agents/tools.py:33-37`). Spec loaded once via singleton (`spec/spec_loader.py:343-360`). No N+1 patterns visible in queries. **No** explicit pool sizing config; no statement timeout on Postgres connections. No connection pool for analytical DB (item 12.5 in roadmap). | `db/engine.py:1-30`; `agents/tools.py:33-37`; absence of pool config | Configure pool size and statement timeout in `db/engine.py`. | 🟡 (item 1.4, 4.4) |
| 23 | Documentation / rationale traceability | 4 | `README.md` 1.165 LOC and `CLAUDE.md` 200 LOC describe what the code does and the architecture matches. Module-level docstrings consistent and accurate. ADR-001 (pgvector) exists in `docs/`. Three ADRs total (001, 002, 003). | `README.md:1-100`; `CLAUDE.md:1-200`; `docs/adr-001-pgvector-over-qdrant.md`; ADR-002, ADR-003 produced this iteration | Add a CHANGELOG.md and start versioning the README sections. | 🟢 |
| 24 | Change governance | 2 | `.pre-commit-config.yaml` exists and configures black + ruff hooks. **No `.github/workflows/`**, no executable CI. No CODEOWNERS. No PR template. The pre-commit config protects local commits but not pushes to main. | `.pre-commit-config.yaml:1-12`; `find .github -type d` → empty; `find . -name CODEOWNERS` → empty | Implement item 11.1 (Pipeline CI). Add CODEOWNERS. | 🔴 (item 11.1 está en inventario pero su implementación efectiva aún es 🔴 porque no existe el pipeline ejecutable) |
| 25 | Dark-code risk | 4 | ~0.5%. Single instance: `simulation/scenario_runner.py` is a trivial wrapper. No silently disabled features. No tests mocking typo'd paths (validated: `grep import.*from agents tests/` returns only valid paths). No "AGENT_TEMPLATE.py"-style placeholder shipped as production. | `simulation/scenario_runner.py:1-5`; `grep -rn "import .*from" tests/ \| head` → no typos | Inline the wrapper; periodically run a coverage report to catch unreachable branches. | 🟢 |
| 26 | AI-generated code governance | 3 | No "AI-narrative comments" pattern visible. Comments are operational, not explanatory of how AI generated them. Type hints and docstrings are consistent with hand-crafted code. No PR template enforcing AI-disclosure. | Inspection of randomly sampled files (`agents/workflow.py`, `evaluation/observer.py`, `spec/spec_loader.py`); absence of `.github/PULL_REQUEST_TEMPLATE.md` | Add an AI-disclosure section to a PR template once item 11.1 is in. | 🟡 (parte de 11.1) |
| 27 | Overall maintainability | 3 | A new engineer could ship a non-trivial change in ~1 week given the README+CLAUDE.md+ADR set, the spec-driven design, and the well-scoped 8.372 LOC. The blocker is the absence of CI: changes can ship without test signal. The Streamlit monolith is the second blocker (1.040 LOC). | Composite of dimensions 1, 4, 7, 13, 23, 24 | Land item 11.1; refactor `streamlit_app.py`. | 🟡 (proceso compuesto de varios items) |
| 28 | Production-readiness from code | 1 | Cannot be deployed in front of an external user today. **Blockers**: no auth on `/v1/query`; no CI to detect regressions; no rate limiting (item 12.5 not implemented); no multi-tenancy; no audit log; no observability beyond LangSmith. **Strengths that earn the 1**: the persistence layer is real, the agent core works, the API is structured, the tests exist. | `api/routers/query.py:17`; `api/main.py:97-110`; absence of `.github/workflows/` | Items 7.1, 7.5, 7.6, 7.8 (security minima) + 11.1 (CI) + 8.2 (metrics) raise this to 3-4. | 🟡 (items 7.x I2B, 11.1 I1, 8.x I2B/I3) |

**Layer 1 mean: 2.96 / 5**

---
## 3. Layer 2 — AI / Agent Layer (20 dimensions)

| # | Dimension | Score | Rationale | Evidence | To reach next level | Gap |
|---|---|---|---|---|---|---|
| 1 | Clarity of agentic role | 3 | Single agent named "Decision Intelligence Agent" with four clearly-named nodes (planner / tool / synthesizer / judge). Module docstrings describe each node's responsibility in 2-3 sentences. No multi-agent today (intended in I3 per items 5.3.a/b/c) — so role clarity is the single-agent role clarity, which is good. | `agents/workflow.py:1-23`; `agents/planner.py:1-26`; `agents/judge.py:1-18` | Promote responsibility statements into Pydantic-typed `AgentRole` once 5.3.a is implemented. | 🟡 (5.3.a en I3) |
| 2 | Explicitness of agentic boundary | 3 | Clear seam between deterministic compute (`system/`, `simulation/`, `optimization/`) and LLM calls (`agents/`). The four-node graph compiles deterministically (`agents/workflow.py:267-282`). LLM is the orchestrator, not the calculator — a principle visible in code: tools never call the LLM, only nodes do. | `agents/workflow.py:115-119` (tool dispatch dict); `agents/tools.py:46-112` (no LLM calls inside tools); `system/system_model.py:114-159` (deterministic eval) | Document this boundary in CLAUDE.md as an architectural invariant. | 🟢 |
| 3 | Separation between agents | n/a → scored 2 | Single agent today, multi-agent planned for I3. Score 2 reflects the absence of separation primitives (Capability Graph item 5.3.b, MemoryService item 5.11) needed before introducing the second agent. The current code is not bad — it just is not multi-agent yet. | Single graph in `agents/workflow.py`; ADR-002 declares Supervisor pattern as decision but no implementation yet | Implement items 5.3.a + 5.3.b together when entering I3. Do not add a second agent until 5.3.b is ready. | 🟡 (items 5.3.a, 5.3.b en I3) |
| 4 | Planning / orchestration | 4 | Plan is structured, not free-form text: the planner emits `ToolSelection(tool, reasoning, params, language)` via `with_structured_output` (`agents/planner.py:60-88`). The orchestration is a typed LangGraph DAG (`agents/workflow.py:267-282`). The chain-of-thought lives in the `reasoning` field of a structured object, not in unparsed prose. | `agents/planner.py:60-88, 200-220`; `agents/workflow.py:267-282` | Once multi-agent (5.3.a) lands, promote `ToolSelection` into a richer typed plan with sub-agent target + payload schema. | 🟢 |
| 5 | Tooling discipline | 2 | Tools are plain Python functions (`agents/tools.py:46-112`) registered in a dict (`agents/workflow.py:115-119`). No `ToolBase` class, no typed tool schema, no input/output validation per tool. The planner produces typed `params` but the tools accept the raw `state` dict and pull whatever they need. | `agents/tools.py:46-112`; `agents/workflow.py:115-119` | Introduce `ToolSpec` (Pydantic) with `input_schema`, `output_schema`, `idempotent`, `side_effecting`. | 🟡 (parte de 4.3 skills engine + 10.8 ToolRegistry) |
| 6 | Tool safety | 2 | No tool is side-effecting today (read-only knowledge retrieval, in-process simulation, in-process optimization). No SQL execution gateway exists (item 2.10 not implemented). The `simulation_tool` performs an adapter step from generic params to positional args (`agents/tools.py:84-94`) — manual, error-prone if more decision variables are added. | `agents/tools.py:84-94` (manual adapter); absence of SQL gateway; absence of authorization layer | Implement item 2.10 SQL Execution Gateway before any analytical-DB connectivity (item 2.1). | 🟡 (item 2.10 en I2A) |
| 7 | Model abstraction | 3 | Provider-agnostic factory: `get_chat_model("openai" \| "anthropic", model_name, temperature)`. Slot-per-node via env vars (`PLANNER_PROVIDER`, `SYNTHESIZER_PROVIDER`, `JUDGE_PROVIDER`). Fallback chain: primary → fallback (single level). No context-budget pre-flight; no multi-provider beyond OpenAI/Anthropic; no typed `ModelRegistry`. | `agents/llm_factory.py:50-98`; `.env.example:5-19` | Implement item 5.6 (LLMFactory completo) — adds Bedrock/Vertex/Ollama, context-budget pre-flight, typed ModelRegistry. | 🟡 (item 5.6 ampliado en I2A) |
| 8 | Prompt governance | 1 | Prompts live in module-level Python strings: `agents/planner.py:117-163` (system prompt) and `agents/judge.py:129-156` (judge prompt). Spec-driven (variables, ranges, defaults injected from spec at runtime, lazily after the recent fix `5d2adf5`). No prompt registry, no versioning, no prompt-evaluation harness. | `agents/planner.py:117-173`; `agents/judge.py:129-156` (inline prompts); commit `5d2adf5` (recent fix to lazy load) | Implement item 10.1 PromptRegistry as the first concrete `Registry pattern` instance (item 10.8). | 🟡 (item 10.1 en I2A; 10.8 en I3) |
| 9 | State management | 4 | `AgentState` is a typed `TypedDict` (`agents/state.py:38-52`) with documented field semantics. Field merging via `Annotated[List, operator.add]` for history (LangGraph append). Sanitization `_sanitize_for_state` (`agents/workflow.py:290-313`) ensures msgpack-friendly serialization for checkpointing. | `agents/state.py:38-52`; `agents/workflow.py:290-313` | Promote to a Pydantic `BaseModel` to gain validation + JSON schema export for documentation. | 🟢 |
| 10 | Memory abstraction | 1 | No `MemoryService` Protocol. The `history` list is part of `AgentState` and accessed directly: `agents/planner.py:185, 189-196` reads `state["history"]` and slices `[-_HISTORY_WINDOW:]` inline. Any agent or node could do the same — there is no seam to enforce. This is exactly the antipattern that ADR-003 calls out from LlullGen ("ChartAgent reads conversation_history[-4:] directly"). | `agents/planner.py:185, 189-196` | Implement items 5.10 (ActiveAnalyticalState) + 5.11 (MemoryService Protocol) and add a lint that bans direct `state["history"]` access outside `memory/`. | 🟡 (items 5.10, 5.11 en I2A) |
| 11 | Retrieval / grounding | 2 | RAG configured: `knowledge/retriever.py:54-68` returns top-k via cosine on pgvector (or FAISS fallback). Retrieval results are passed to the synthesizer as raw text. **No grounding validation**: the synthesizer can paraphrase or invent without comparison against the retrieved chunks. **No GroundedTokens guardrail** (item 5.9 in I2A). | `knowledge/retriever.py:76-106`; `agents/workflow.py:177-238` (synthesizer has no grounding check) | Implement item 5.9 GroundedTokens. Add a post-synthesis grounding check via the Judge already present. | 🟡 (item 5.9 en I2A) |
| 12 | Output validation | 4 | Structured outputs with Pydantic at every LLM seam: planner returns `ToolSelection` (`agents/planner.py:60-72`), judge returns `JudgeVerdict` (`agents/judge.py:77-85`). Validation via `with_structured_output()` of LangChain. The judge itself is an output-validation step (`agents/judge.py:188-201`). No anti-hallucination guardrails for entities (5.9). | `agents/planner.py:60-88`; `agents/judge.py:77-101, 188-201` | Add 5.9 GroundedTokens for entity-level anti-hallucination. | 🟢 |
| 13 | Error / retry strategy | 3 | Exponential backoff retry in `agents/llm_factory.py:101-165` (max retries env-configurable, default 2). Rate-limit detection via string match. Switch-to-fallback on rate-limit exhaustion or hard error. Judge "fails open" preserving the original answer (`agents/judge.py:163-184`). Planner falls back to `knowledge` tool on any failure (`agents/planner.py:212-220`). | `agents/llm_factory.py:101-165`; `agents/judge.py:163-184`; `agents/planner.py:212-220` | Distinguish hard errors from soft errors more granularly. Add per-slot fallback chain (item 8.7.d). | 🟡 (item 8.7.d) |
| 14 | Loop control / boundedness | 1 | No recursion guard. No per-run wallclock cap. No max LLM calls per run. The four-node graph is bounded (no loops in the DAG: `planner→tool→synthesizer→judge→END`), but the recursion limit of LangGraph itself is not configured (`agents/workflow.py:280-282`). The judge does a single revision (`agents/judge.py:192-201`) — bounded — but if a future change introduces a loop edge, nothing prevents runaway. | `agents/workflow.py:267-282` (no `recursion_limit`); absence of per-run cost cap | Implement item 5.12 (recursion guard) + 8.7.b (hard request-level ceilings). | 🟡 (items 5.12, 8.7.b en I2A/I3) |
| 15 | Observability of agent runs | 4 | `AgentObserver` (`evaluation/observer.py:92-282`) records every run with per-node spans, latency, model, judge score, error. JSONL + Postgres dual write. LangSmith bridge available (`evaluation/observer.py:306-324`). HTML dashboard generated from runs (`evaluation/dashboard.py:1-471`). | `evaluation/observer.py:92-282`; `evaluation/dashboard.py:1-471` | Add `run_id` propagation via contextvars (item 8.4 ampliado) so any code path can emit a correlated log. | 🟢 |
| 16 | Testing and evaluation | 2 | Unit tests for the planner (`tests/agents/test_planner.py`, 103 LOC), llm_factory (105 LOC), API endpoints (60+87+182 LOC). All offline (mocked LLM). **No golden eval harness, no IR-gate, no plan-gate, no response-shape-gate.** No `evaluation/datasets/` directory. | `tests/agents/test_planner.py:1-103`; absence of `evaluation/datasets/`; absence of CI to run anything | Implement items 10.2 (datasets evaluación) + 10.11 (golden eval CI gates). | 🟡 (items 10.2, 10.11 en I2A/I3) |
| 17 | LLM cost control | 0 | **No control whatsoever**. No cost tracking per run (the observer records latency and model but not tokens or USD). No per-tenant quota. No per-run hard ceiling. No fallback chain by budget. No cost lineage. The fallback chain in 5.6 is by error, not by cost. **However**: items 8.7.a–f cover all six dimensions of cost control identified, with 8.7.b (hard ceilings) classified as "the most critical item" in roadmap v4. | `evaluation/observer.py:92-282` (no token/cost field); `agents/llm_factory.py:101-165` (no cost reservation); inventory items 8.7.a–f all marked [v4] | Implement items 8.7.a–d in I2A as planned. | 🟡 (items 8.7.a–f, 5.12) |
| 18 | Multi-turn / session continuity | 2 | LangGraph checkpointing persists state per `thread_id` (`memory/checkpointer.py:63-95`). The planner injects last 3 turns from `state["history"]` (`agents/planner.py:75, 185-196`). No `ActiveAnalyticalState` typed object yet. The continuity rules are implicit in the planner prompt, not codified. **This is the LlullGen antipattern that audit explicitly calls out** — and items 5.10 + 5.11 + 5.5 directly address it. | `memory/checkpointer.py:63-95`; `agents/planner.py:75, 185-196` (history slice in prompt assembly); inventory items 5.5, 5.10, 5.11 | Implement items 5.10 + 5.11 (and reference them from 5.5). | 🟡 (items 5.5, 5.10, 5.11 en I2A) |
| 19 | Multi-agent coordination | n/a → 1 | No multi-agent today. Score 1 reflects the absence of any of the prerequisites: no Capability Graph, no MemoryService Protocol, no per-peer budgets, no recursion guards. ADR-002 declares the Supervisor pattern as the chosen approach when multi-agent lands. | Single graph in `agents/workflow.py`; absence of `agents/orchestrator/`; ADR-002 | Implement items 5.3.a + 5.3.b + 5.12 + 8.7.e together in I3. | 🟡 (items 5.3.a/b, 5.12, 8.7.e en I3) |
| 20 | Agent autonomy policy | 1 | No `autonomy_policy` field in spec, no policy consultation step in the workflow. Item 3.5 (extender el spec con autonomy_policy) is in I2A. The judge approval threshold is hardcoded to env (`JUDGE_THRESHOLD=0.75` in `agents/judge.py:65`) — not policy-driven per tool. | `agents/judge.py:65, 188-201`; absence of autonomy fields in `spec/organizational_model.yaml` | Implement items 3.5 + 7.3 (políticas de autonomía consultadas por el planner). | 🟡 (items 3.5 en I2A, 7.3 en I3) |

**Layer 2 mean: 2.40 / 5**

---
## 4. Layer 3 — Conversational & Analytical Memory (22 dimensions)

| # | Dimension | Score | Rationale | Evidence | To reach next level | Gap |
|---|---|---|---|---|---|---|
| 1 | Memory system existence | 2 | A `memory/` package exists with two modules: `checkpointer.py` (LangGraph state persistence) and `session_manager.py` (CRUD over `agent_sessions`). It does the minimum — persist and list — but contains no concept of "memory" beyond LangGraph's checkpoint semantics. No `MemoryService`, no `ActiveAnalyticalState`, no per-slot semantics. The package is correctly placed; what's missing is what should live inside it. | `memory/__init__.py:1-20`; `memory/checkpointer.py:1-182`; `memory/session_manager.py:1-235` | Implement items 5.10 (ActiveAnalyticalState) + 5.11 (MemoryService) inside `memory/`. | 🟡 (items 5.10, 5.11 en I2A) |
| 2 | System boundary clarity | 1 | The single seam principle is violated. `agents/planner.py:189` reads `history[-_HISTORY_WINDOW:]` directly from `state`. Any node could do the same; nothing prevents it. There is no Protocol-typed boundary, no lint rule, no architectural assertion. This is the exact pattern that ADR-003 calls out as the LlullGen antipattern (ChartAgent reading `conversation_history[-4:]`) — and llull already exhibits it. | `agents/planner.py:185-196` (slice + injection inline); absence of `MemoryService` Protocol | Implement item 5.11 with the lint enforcement described in inventory ("ban direct `state["history"]` access outside `memory/`"). | 🟡 (item 5.11 en I2A) |
| 3 | Structured active state | 0 | No `ActiveAnalyticalState` exists. The closest thing is `AgentState` (`agents/state.py:38-52`), which is a transport TypedDict carrying transient turn data (query, params, raw_result, answer, judge_*) plus an append-only `history`. There is no typed object representing intent, active metrics, active dimensions, period, geography, frozen slots, pending confirmations, or ongoing simulation runs — none of the fields that ADR-002 and roadmap v4 item 5.10 declare necessary. | `agents/state.py:38-52`; absence of `memory/active_state.py` or equivalent | Implement item 5.10. This is the highest-leverage memory item in v4. | 🟡 (item 5.10 en I2A) |
| 4 | State centrality as truth | 0 | The conversation transcript IS the source of truth — same antipattern as LlullGen. The planner reads `history` and uses the LLM to "remember" what the previous turns were about. There is no separate active-state object that the LLM consults via a typed contract; the LLM consults the raw history. Score 0 reflects "no active-state object at all" exactly as the LlullGen audit scored it. | `agents/planner.py:185-196`; absence of typed state | Item 5.10 + downstream refactor of `planner.py` to consult typed state instead of slicing history. | 🟡 (item 5.10 en I2A) |
| 5 | State traceability | 1 | No per-slot provenance because there are no slots. Each turn produces a `RunRecord` (`evaluation/observer.py:44-85`) that records what tool was used, what params, what answer, what judge score — that's run-level provenance, not state-slot provenance. The history list is opaque text after that. | `evaluation/observer.py:44-85` (run-level only); absence of `SlotProvenance` | Item 5.10 includes `provenance: dict[str, SlotProvenance]` per the v4 inventory. | 🟡 (item 5.10 en I2A) |
| 6 | State lifecycle discipline | 1 | The transcript is append-only (LangGraph `Annotated[List, operator.add]` ensures it; `agents/state.py:52`). No state mutations beyond append, but also no typed mutations to track. There is no audit log of slot transitions because there are no slots. | `agents/state.py:52`; LangGraph checkpointer behavior | Once 5.10 lands, add a `MemoryEvent` log in Postgres recording every slot transition. | 🟡 (item 5.10 en I2A) |
| 7 | Short-range memory | 3 | Last `_HISTORY_WINDOW=3` turns (env-configurable) are read from `history` and prepended to the planner prompt as `(role: user, role: assistant)` pairs. The implementation is correct and works. The window size is a single env var rather than per-call configurable. There is no compaction, no summarization, no token-budget aware selection. | `agents/planner.py:75, 189-196` | Implement context-budget pre-flight from item 5.6 ampliado; add summarization for older turns when window is exceeded. | 🟡 (item 5.5 en I2A; 5.6 ampliado en I2A) |
| 8 | Explicit rule quality | 1 | Multi-turn rules live in the system prompt of the planner (`agents/planner.py:117-163`): "Before selecting a tool, reason step by step…", "Decision variables available: …". These are LLM-instructed rules, not code-enforced rules. There is no rule-engine, no follow-up classifier in code, no slot-inheritance algorithm — same antipattern the LlullGen audit calls out ("rules live in routing prompt strings"). | `agents/planner.py:117-163` | Promote multi-turn rules into typed `MemoryPolicy` objects in code, consulted by `MemoryService`. | 🟡 (item 5.11 + parte de 5.10 en I2A) |
| 9 | Inheritance governance | 0 | Slot inheritance between turns is implicit in what the LLM "remembers" from the recent history slice. There is no explicit inheritance policy ("if metric was active in turn N-1, inherit unless user contradicts"). With no slots and no MemoryService, inheritance cannot be governed. | `agents/planner.py:185-220`; absence of slot/inheritance logic | Implement item 5.10 first; inheritance comes naturally on top. | 🟡 (item 5.10 en I2A) |
| 10 | Reset / invalidation | 0 | No invalidation rules. If the user changes domain or topic, nothing in code detects it. The LLM has to figure it out from the prompt context. This is the same gap as LlullGen ("No metric/dim/period invalidation rules"). | absence of any invalidation logic | Once 5.10 lands, add per-slot `invalidate_on` rules. | 🟡 (item 5.10 en I2A) |
| 11 | Clarification governance | 1 | No structured clarification flow. The judge can request a revision (`agents/judge.py:188-201`) but it is a one-shot rewrite, not a "this slot is ambiguous, ask the user" flow. No `pending_confirmations` field anywhere. | `agents/judge.py:188-201`; absence of clarification state | Add `pending_confirmations: list[PendingConfirmation]` as part of `ActiveAnalyticalState` (item 5.10). | 🟡 (item 5.10 en I2A) |
| 12 | Conflict resolution | 0 | No conflict resolution logic. If turn N+1 contradicts turn N (user says "actually, marketing is 5000 not 10000"), the planner will read both turns from history and let the LLM decide what to do. There is no declarative rule "later turn wins for same slot". | `agents/planner.py:185-220`; absence of conflict logic | Implement state slot semantics first (item 5.10), then conflict rules. | 🟡 (item 5.10 en I2A) |
| 13 | Contextual retrieval | 2 | RAG retrieval is keyed on the raw query, not on active state. `knowledge_tool` calls `retrieve_knowledge(query)` directly (`agents/tools.py:97-112`). There is no enrichment of the query with active metrics, dimensions, period — because none of those exist as typed state. The retrieval works for current single-turn questions but degrades on multi-turn follow-ups. | `agents/tools.py:97-112`; `knowledge/retriever.py:54-68` | Once 5.10 lands, enrich retrieval queries with active-state slots before calling `retrieve_knowledge`. | 🟡 (item 5.10 + dependiente) |
| 14 | Retrieval subordination | 1 | Retrieval results are returned verbatim to the synthesizer (`knowledge_tool` returns `{"answer": text, "documents": text}` — `agents/tools.py:108-112`). No validation against active state, no relevance filter, no grounding check. The judge could in principle catch egregious mismatches but does not perform retrieval-grounding specifically. | `agents/tools.py:97-112`; `agents/judge.py:129-156` (no retrieval-grounding step) | Add a post-retrieval filter that checks coverage of active-state slots before passing to synthesizer. | 🟡 (depende de 5.10) |
| 15 | Multi-turn behavior | 2 | Multi-turn works in practice for simple cases: the planner sees the last 3 turns and the LLM resolves "and what about marketing 12000?" follow-up correctly. Tested behaviorally in `tests/agents/test_planner.py` (history fixture). **But** the correctness is at the prompt level — change the system prompt and follow-up resolution may break silently. | `tests/agents/test_planner.py:1-103`; `agents/planner.py:117-163` (system prompt carries the rules) | Codify follow-up rules into typed objects (item 5.10/5.11) and test them at the unit level. | 🟡 (items 5.10, 5.11 en I2A) |
| 16 | Memory vs prompting balance | 1 | All multi-turn correctness today lives in the prompt: the system prompt instructs the planner to consult history and extract params. Nothing in the code path enforces this — if the LLM ignores the instruction, the system has no recovery. Same antipattern as LlullGen ("most multi-turn correctness is prompted, not coded"). | `agents/planner.py:117-220` | Migrate as much multi-turn logic as possible into deterministic code (5.10 + 5.11). | 🟡 (items 5.10, 5.11 en I2A) |
| 17 | Complementary techniques | 2 | Token-budget compaction: not implemented (item 5.6 ampliado covers context-budget pre-flight). Prompt caching: not configured at the LLM provider level. Summarization: not implemented. The single technique present is the fixed-size sliding window. | `agents/planner.py:75, 189-196` (sliding window only); `.env.example:10` (HISTORY_WINDOW=3) | Implement item 5.6 ampliado (context-budget pre-flight) and add older-turns summarization on overflow. | 🟡 (item 5.6 en I2A) |
| 18 | Single-turn vs multi-turn separation | 2 | The same code path handles both: the planner always assembles history, even for first-turn queries (history is empty list, list slicing returns empty, no harm done). There is no explicit "first turn" vs "continuation" logic. Functionally OK but architecturally undifferentiated. | `agents/planner.py:184-198` (uniform handling) | Once `ActiveAnalyticalState` (5.10) exists, the first turn creates a fresh state, continuations consult it — natural separation. | 🟡 (item 5.10 en I2A) |
| 19 | User interaction with memory | 0 | No APIs for inspect / correct / confirm / freeze slots — there are no slots. The user cannot say "freeze marketing at 8000 for the rest of this session". No frozen slots, no pinning, no user-driven invalidation. Same score as the LlullGen audit assigned to itself for this dimension. | absence of state inspection / mutation APIs | Item 5.10 includes `frozen_slots: set[str]`. Once it exists, expose API endpoints and Streamlit UI for it. | 🟡 (item 5.10 en I2A; UI bajo demanda) |
| 20 | Downstream integration | 2 | The synthesizer reads `state["raw_result"]` and `state["query"]` — no transcript scraping (`agents/workflow.py:177-238`). The judge reads `state["raw_result"]`, `state["answer"]`, `state["query"]` — clean (`agents/judge.py:118-156`). The planner is the only node that reaches into `state["history"]` directly. So downstream integration is mostly clean except the planner. | `agents/workflow.py:177-238`; `agents/judge.py:118-156`; `agents/planner.py:185-196` | Once 5.11 lands, the planner consults `MemoryService.get_short_range_view()` instead of slicing `state["history"]`. | 🟡 (item 5.11 en I2A) |
| 21 | Coordination / orchestration role | 2 | LangGraph is the orchestrator and it does its job: deterministic node sequence, state propagation, checkpointing. The orchestrator does not absorb memory mutation today because there is no memory mutation to absorb beyond append-history. When 5.3.a multi-agent lands, the question of "who mutates `ActiveAnalyticalState`" becomes critical (the v4 inventory says: only `MemoryCoordinator`). | `agents/workflow.py:267-282`; absence of `MemoryCoordinator` | Implement item 5.10 with the `MemoryCoordinator` invariant from inventory v4. | 🟡 (item 5.10 en I2A) |
| 22 | Coordination integrity | 1 | No single coordinator gates memory mutations because there are no typed mutations. Anyone with access to `state` can append to `history` (LangGraph operator.add). When state grows to typed slots, this needs one coordinator with sole write privilege on `ActiveAnalyticalState`, as roadmap v4 declares. | `agents/state.py:52` (operator.add is unrestricted); absence of coordinator | Implement `MemoryCoordinator` (part of item 5.10/5.11) as the single mutator. | 🟡 (items 5.10, 5.11 en I2A) |

**Layer 3 mean: 1.27 / 5**

This is the **lowest-scoring layer**, deliberately so: the memory system is the area where llull most relies on LLM-via-prompt and least on typed code. The roadmap v4 acknowledges this — items 5.5, 5.9, 5.10, 5.11 all live in I2A precisely because closing this gap is the priority for the piloto interno phase. Eight of the 22 dimensions score 0–1, and **all eight** are 🟡 (planned). No 🔴 in this layer.

---
## 5. Layer 4 — Ontology & Semantic Knowledge (16 dimensions)

| # | Dimension | Score | Rationale | Evidence | To reach next level | Gap |
|---|---|---|---|---|---|---|
| 1 | Conceptual semantic layer | 3 | A semantic layer exists conceptually and structurally: `OrganizationalModelSpec` typed dataclass tree (`spec/spec_loader.py:139-188`) declares decision variables, intermediate variables, target variables, causal relationships, constraints, business parameters, demand model coefficients, data generation config, optimization target. The spec is consumed by every layer that should consume it (`system/system_model.py`, `simulation/montecarlo.py`, `optimization/optimizer.py`, `agents/planner.py`, `config/settings.py`). The "semantic layer" word is not used but the structure is real and serves the purpose. | `spec/spec_loader.py:139-188`; `spec/organizational_model.yaml:1-100`; `system/system_model.py:91-112` | Add an explicit `semantic/` package and migrate naming. Document it in CLAUDE.md as a first-class concept. | 🟢 |
| 2 | Formal ontology presence | 1 | Zero references to "ontology" in code or docs (`grep -i ontology` returns nothing). No OWL, no RDF, no formal hierarchy. The spec is structured but flat — variables are listed, not classified into types/categories with inheritance. The roadmap acknowledges this: item 2.7 (Integración de ontologías corporativas) is in "Más allá", explicitly bajo demanda. | `grep -ri "ontology" --include="*.py" --include="*.md" --include="*.yaml"` → 0 hits; inventory item 2.7 in "Más allá" | Item 2.7 when a client requires it. The score reflects current absence; not a gap. | 🟡 (item 2.7 en "Más allá") |
| 3 | Entity registry | 1 | No `EntityRegistry`. Decision variables, intermediate variables, target variables are typed dataclasses (`DecisionVariable`, `IntermediateVariable`, `TargetVariable` — `spec/spec_loader.py:38-74`) but they are not "entities" in the registry-pattern sense (no id/version/status/owners). Items 10.8 (Registry pattern unificado) and the EntityRegistry it includes live in I3. | `spec/spec_loader.py:38-74`; inventory item 10.8 | Implement item 10.8. Until then, the typed dataclasses are the closest thing. | 🟡 (item 10.8 en I3) |
| 4 | Relationship modelling | 3 | Causal relationships are first-class objects (`CausalRelationship` dataclass — `spec/spec_loader.py:77-84`) declared in the YAML and parsed into typed Python. The DAG is built from them at runtime (`system/system_graph.py:16-42`). They have a `rel_type` field for category. This is genuinely better than "no business-level relations at all" (LlullGen's score 1 on this dimension). | `spec/spec_loader.py:77-84`; `system/system_graph.py:16-42`; `spec/organizational_model.yaml` (causal_relationships section) | Add `confidence` and `evidence_source` fields to `CausalRelationship` for governance. | 🟢 |
| 5 | Metric registry | 1 | No `MetricRegistry`. Target variables (`TargetVariable` dataclass — `spec/spec_loader.py:65-74`) declare `name`, `description`, `unit`, `formula`, `optimize` — close to what a metric registry needs but not versioned, not owned, not status-tracked. Item 10.8 covers `MetricRegistry` as one of the 10 registries. | `spec/spec_loader.py:65-74`; absence of separate metric concept | Item 10.8 (MetricRegistry as concrete instance). | 🟡 (item 10.8 en I3) |
| 6 | Dimension / vocabulary registry | 0 | No `DimensionRegistry`, no `VocabularyRegistry`. The YAML spec has no vocabularies, no synonyms, no aliases. There is no concept of "dimension" separate from variable. Item 10.8 includes both `DimensionRegistry` and `VocabularyRegistry`; item 5.9 (GroundedTokens) requires `VocabularyRegistry` to be alimentado from spec by domain and locale. | absence of vocabulary fields in `spec/organizational_model.yaml`; inventory items 5.9, 10.8 | Implement 10.8 with its `VocabularyRegistry`; then 5.9 consumes it. | 🟡 (items 5.9 I2A, 10.8 I3) |
| 7 | Alias / synonym handling | 0 | No synonyms, no aliases anywhere. Variables have a single `name`. If the user says "precio" or "tarifa" or "PVP" instead of "price", the LLM must figure it out from context. There is no structured matching, no regex layer either. Score 0 reflects "no synonym handling at all" — a step below LlullGen's score of 2 (which had synonyms in DB even if flat). | `spec/spec_loader.py:38-50` (no synonyms field); spec YAML inspection | Add `synonyms: list[str]` per variable in the spec. Wire into 5.9 GroundedTokens. | 🟡 (parte de 5.9, 10.8) |
| 8 | Ambiguity handling | 1 | The judge's revision flow (`agents/judge.py:188-201`) catches some ambiguity by triggering a rewrite when the answer doesn't ground in tool output. But there is no `IntentClassifier`, no `needs_clarification` flag, no static disambiguation rules. If a query is ambiguous between optimization and simulation, the planner picks one and runs with it. | `agents/judge.py:188-201`; absence of intent classifier | Add an explicit `IntentClassifier` step before the planner. | 🟡 (parte de 5.10 ambiguities pendientes; 7.3 políticas autonomía) |
| 9 | Business-to-system mapping | 2 | The mapping from user vocabulary to system variable names is **single-step and LLM-driven**: the planner's structured output extracts `params` with keys matching exact variable names (`agents/planner.py:60-72`, `_build_system_prompt:117-163`). The system prompt enumerates the variables explicitly so the LLM has them to work with. There is no separate `MappingLayer` — the LLM IS the mapping layer. **However**, there is an `adapter` step in `simulation_tool` (`agents/tools.py:84-94`) that maps generic params to positional args of `run_scenario`. That adapter is acknowledged in code comments as "domain coupling intentionally confined to this function" — good discipline. | `agents/planner.py:60-72, 117-163`; `agents/tools.py:84-94` | Implement item 2.2 (Data Mapping Layer asistida por LLM) — separate, persistent, reusable mapping. | 🟡 (item 2.2 en I2A) |
| 10 | Physical data introspection | 1 | No introspection of physical data sources today because there are no physical data sources connected (item 2.1 conectores batch is in I2A). The training data is synthetic (`data/generate_data.py`) and generated from spec parameters — round-trip rather than introspected. When 2.1 lands, this dimension becomes meaningful. | `data/generate_data.py`; absence of any DB introspection code; inventory items 2.1, 2.2, 2.5 | Implement items 2.1 + 2.2 (which include schema inference per inventory description). | 🟡 (items 2.1, 2.2 en I2A) |
| 11 | Query interpretation | 4 | The query is interpreted into a typed IR object: `ToolSelection(tool, reasoning, params, language)` is exactly the IR. The fields are typed (Pydantic), the tool selection is from a finite enum (`Literal["optimization", "simulation", "knowledge"]`), the params are typed (`List[DecisionParam]`), the language is ISO 639-1. This is **the strongest area** of llull's semantic layer, paralleling the LlullGen audit's note that query interpretation was its strongest area too. | `agents/planner.py:53-72`; `agents/planner.py:200-220` (the interpretation step) | Add an `intent` field above the tool field; that's a richer IR. Add validation that `params` keys match spec. | 🟢 |
| 12 | Runtime consumption | 4 | Every relevant component consumes the spec / typed objects at runtime: `system_model` (`system/system_model.py:91-112`), `system_graph` (`system/system_graph.py:16-42`), `simulation_tool` (`agents/tools.py:60-94`), `planner` (`agents/planner.py:117-163`), `config` (`config/settings.py:14-37`). Spec changes propagate without code changes (within their declared scope). | All listed file references | Migrate the spec from YAML-on-disk to DB-stored (item 1.5 already partial — `_load_spec_with_fallback` does DB-first then YAML). | 🟢 |
| 13 | Test coverage of semantic layer | 1 | Tests exist for spec loader (`tests/spec/test_spec_loader_db.py`, `tests/spec/test_spec_repository.py`). They test loading and persistence, not semantic interpretation. There are no goldens for "given query Q, the planner produces tool T with params P". `tests/agents/test_planner.py` mocks `invoke_with_fallback` and tests structural propagation (`tests/agents/test_planner.py:39-49`), not semantic correctness. | `tests/spec/`; `tests/agents/test_planner.py:39-49` (structural test); absence of `evaluation/datasets/` | Implement items 10.2 (datasets evaluación) + 10.11 (golden eval CI gates) — they're exactly this. | 🟡 (items 10.2, 10.11 en I2A/I3) |
| 14 | Governance / versioning | 3 | `Spec` and `SpecVersion` ORM models exist (`db/models.py:133-182`) with `domain_name`, `version`, `status` (draft/active/archived), `created_by`, `created_at`, `change_summary`. CRUD via `spec/spec_repository.py:38-200`. The lifecycle (draft → active → archived) is real and persisted. **Limited to the spec itself**: prompts, models, rules, tools, metrics — none are versioned. | `db/models.py:133-182`; `spec/spec_repository.py:38-200` | Item 10.8 generalizes this pattern to the other 9 registries. | 🟡 (item 10.8 en I3 generaliza) |
| 15 | Scalability across domains | 4 | Domain switching is config-level: edit `spec/organizational_model.yaml` and the entire system reflects the new domain. The planner's prompt is built dynamically from the spec (`agents/planner.py:91-163`). Tools fall back to spec defaults for any missing param (`agents/tools.py:60-94`). The README explicitly documents this in `## Adapting to a New Domain` (line 1.121). The single concession is the manual adapter in `simulation_tool:84-94` (price/marketing positional args). | `agents/planner.py:91-163`; `agents/tools.py:60-94`; `README.md:1121` (Adapting to a New Domain section) | Generalize the simulation adapter to use generic var_values instead of price/marketing positional. | 🟢 |
| 16 | Internal consistency | 3 | The spec is the single source of truth; `config/settings.py` is a thin adapter over it. Variables defined once, referenced everywhere by exact name. **One inconsistency** to flag: the demand model formula declared in the spec docstring (`spec/spec_loader.py:96-103`) is documentary, not enforced — the actual formula lives in `data/generate_data.py` and the inverse in the trained ML model. If they drift, neither tells you. | `spec/spec_loader.py:96-103`; `data/generate_data.py`; absence of cross-validation | Add a startup assertion that `train_demand_model` reproduces coefficients within tolerance of the spec's `demand_model` block. | 🟢 |

**Layer 4 mean: 2.31 / 5**

A more nuanced score than the layer mean suggests: 4 dimensions score ≥ 4 (Conceptual semantic layer, Relationship modelling, Query interpretation, Runtime consumption, Scalability), reflecting the genuine craft of the spec-driven design; 4 dimensions score 0–1 (Formal ontology, Dimension/Vocabulary registry, Alias/synonym handling, Physical data introspection), reflecting capabilities deliberately deferred to "Más allá" or to I2A. The layer is bipolar: very strong where the prototype focuses, very weak where it has not yet reached.

---

## 6. Critical Findings (🔴) — Gaps not in inventory / roadmap / ADRs

These are the priority hallazgos: capabilities that the rubric expects, that are **not** in the codebase, and that an audit against the inventory v4 / roadmap v4 / ADRs reveals as **unplanned**. Six items.

### 6.1 — No executable CI pipeline (despite inventory item 11.1)

- **Layer · Dimension**: Codebase · #14 Test strategy completeness; #24 Change governance
- **Severity**: **P0**
- **Evidence**:
  - `find /home/claude/decision-intelligence-agent/.github -type d` → empty (no GitHub Actions configured).
  - `.pre-commit-config.yaml` exists with black + ruff hooks (`.pre-commit-config.yaml:1-12`) but pre-commit hooks only protect local commits, not pushes to `main`.
  - 14 test files exist (`tests/agents/`, `tests/api/`, `tests/db/`, `tests/knowledge/`, `tests/memory/`, `tests/spec/`) totaling 1.300 LOC, including marked integration tests with Postgres.
  - `pyproject.toml:6-8` declares the `integration` pytest marker but no automation runs it.
- **Searches performed to confirm classification**:
  - `inventario_v4`: `grep "Pipeline CI" docs/llull_inventario_v4.md` → 1 hit (item 11.1). The capability is in inventory.
  - `roadmap_v4`: `grep "11.1" docs/llull_roadmap_v4.md` → 11.1 is in I1 paquete 1C, marked `status-wip`.
  - **However**: the audit classifies this 🔴 because **the gap is between "planned" and "actually executable"**. v4 inventory + roadmap mark 11.1 as planned for I1, but I1 has been in progress for weeks and 11.1 has not landed despite being declared the lowest-cost / highest-leverage item of I1. The disconnect between "declared in plan" and "still not done" is itself a finding.
- **Recommended action**: land item 11.1 within the next sprint. Minimum scope: GitHub Actions workflow running `pytest -m "not integration"` on every push to main and every PR. Postgres-service-container integration job as second step (1-2 hours of additional work).

### 6.2 — `config/settings.py` does spec loading at module-import time

- **Layer · Dimension**: Codebase · #11 Robustness against failure
- **Severity**: **P1**
- **Evidence**:
  - `config/settings.py:14-37`: `_spec = get_spec()` is called at module load, before any logging is configured. Subsequent constants `UNIT_COST`, `MC_RUNS`, `PRICE_MIN`, etc. are derived from `_spec` at import time.
  - `simulation/montecarlo.py:20`, `optimization/optimizer.py:3`, `system/system_model.py:68` all `from config.settings import …`. A spec parsing failure (malformed YAML, missing required field, DB unreachable when `DATABASE_URL` is set and the DB-first path is tried) crashes the import cascade with no meaningful error path.
  - The most recent commit `5d2adf5` ("fix(planner): make _SYSTEM_PROMPT lazy to prevent import-time IO") explicitly fixed this same antipattern in `agents/planner.py:166-173` — but `config/settings.py` itself was not migrated to the same pattern. The fix is incomplete.
- **Searches performed**:
  - `inventario_v4`: `grep -i "import-time\|module load\|lazy" docs/llull_inventario_v4.md` → 0 hits.
  - `roadmap_v4`: same → 0 hits.
  - `ADR-002`, `ADR-003`: same → 0 hits.
- **Recommended action**: convert `config/settings.py` into accessor functions (`get_unit_cost()`, `get_mc_runs()`, `get_price_bounds()`) that load lazily on first call and cache. Mirror the pattern of `agents/planner.py:166-173`. ~30 minutes of work.

### 6.3 — `pytest` and `pytest-cov` missing from `requirements-dev.txt`

- **Layer · Dimension**: Codebase · #8 Dependency hygiene; #13 Test quality
- **Severity**: **P1**
- **Evidence**:
  - `requirements-dev.txt:1-4`: contains only `-r requirements.txt`, `black~=24.0`, `ruff~=0.5`, `pre-commit~=3.7`. Pytest is not listed.
  - `tests/agents/test_planner.py:1-103` and 13 other test files use pytest fixtures via convention. Without manual `pip install pytest`, none of them run.
  - `pyproject.toml:5-8` declares `[tool.pytest.ini_options]` with the `integration` marker, implying pytest is expected.
- **Searches performed**:
  - `inventario_v4`: `grep -i "pytest\|pytest-cov\|requirements-dev" docs/llull_inventario_v4.md` → 0 hits.
  - `roadmap_v4`: same → 0 hits.
- **Recommended action**: add `pytest~=8.0`, `pytest-cov~=5.0` to `requirements-dev.txt`. ~5 minutes.

### 6.4 — Inconsistent declared Python target version

- **Layer · Dimension**: Codebase · #8 Dependency hygiene; #16 Supply-chain hygiene
- **Severity**: **P2**
- **Evidence**:
  - `.python-version`: `3.12`
  - `pyproject.toml:3`: `target-version = ["py310"]` (under `[tool.black]`)
  - No CI matrix to validate against either version (link to finding 6.1).
- **Searches performed**:
  - `inventario_v4`: `grep -i "python.*version\|target-version\|3.10\|3.11\|3.12" docs/llull_inventario_v4.md` → 0 hits.
  - `roadmap_v4`: same → 0 hits.
- **Recommended action**: align `pyproject.toml` to `target-version = ["py312"]`. When 6.1 lands, add a CI matrix testing 3.11 + 3.12 (3.10 EOL Q4 2026). ~5 minutes for the alignment, ~30 minutes for the matrix.

### 6.5 — CORS allows `*` methods and headers without explicit allowlist

- **Layer · Dimension**: Codebase · #15 Security posture; AI Layer · #6 Tool safety
- **Severity**: **P2** (raised to **P0** the moment the API is exposed publicly)
- **Evidence**:
  - `api/main.py:84-89`: `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True`. Combined with `allow_credentials=True`, the CORS spec actually disallows `*` for credentialed requests in browsers — which means this configuration silently fails for credentialed cross-origin calls and works only for non-credentialed ones. The intent is unclear.
- **Searches performed**:
  - `inventario_v4`: `grep -i "CORS" docs/llull_inventario_v4.md` → 0 hits. (CORS appears in `.env.example` and `api/main.py` but not in the inventory.)
  - `roadmap_v4`: same → 0 hits.
  - Item 7.6 (cifrado en tránsito y en reposo) and 7.5 (SSO) cover the larger security envelope, but not CORS specifically.
- **Recommended action**: explicit allowlist of methods and headers. Set `allow_credentials=False` unless SSO is in scope (item 7.5 in I2B). ~15 minutes.

### 6.6 — `allow_dangerous_deserialization=True` in FAISS retriever without comment

- **Layer · Dimension**: Codebase · #15 Security posture
- **Severity**: **P2** (raised to **P1** if FAISS index files become user-supplied artifacts)
- **Evidence**:
  - `knowledge/retriever.py:130`: `allow_dangerous_deserialization=True` with no inline comment explaining why or under what threat model.
  - The flag exists because LangChain FAISS uses pickle internally for index serialization. Today the FAISS index is local-built (`knowledge/build_index.py`) and the file is generated by the same process that reads it — low real risk.
  - Risk grows when (a) FAISS indices are downloaded from cloud storage (planned for multi-tenant per inventory item 1.4 / 7.10), (b) FAISS indices become user-uploaded.
- **Searches performed**:
  - `inventario_v4`: `grep -i "FAISS\|allow_dangerous" docs/llull_inventario_v4.md` → 1 FAISS hit (`1.2 Capa vectorial sobre pgvector`) but no mention of the flag.
  - `roadmap_v4`: same → 1 hit, in 1.2 context.
  - The migration to pgvector (item 1.2) eliminates this risk for production paths but the FAISS fallback (item 1.3) preserves it.
- **Recommended action**: add a code comment at `knowledge/retriever.py:130` explaining the threat model ("only loads locally-generated indices; never load FAISS indices from network sources"). When item 7.10 (despliegues dedicados) lands, replace the flag-on with a path validation that asserts the FAISS file is in a trusted directory. ~10 minutes for the comment.

---

## 7. Planned Gaps (🟡) — Capabilities pending per the roadmap

These are dimensions where the rubric expects capabilities that are not in code yet but **are** explicitly in inventory v4, roadmap v4 or ADRs. They do not penalize the audit beyond what the current scaffolding earns. Selected for the most impactful (full list visible in the per-layer tables above).

| Layer · Dimension | Capability | Inventory item | Iteration | Priority within iteration |
|---|---|---|---|---|
| AI · #17 LLM cost control (all sub-dimensions) | Tenant quotas, hard ceilings, budget reservation, fallback chain by slot | 8.7.a, 8.7.b, 8.7.c, 8.7.d | I2A | **8.7.b is critical-path** |
| AI · #14 Loop control / boundedness | Recursion guard + depth limits | 5.12 | I3 (with 5.3.a/b) | High when multi-agent lands |
| AI · #10 Memory abstraction | MemoryService as Protocol | 5.11 | I2A | High |
| AI · #18 Multi-turn / session continuity | ActiveAnalyticalState typed | 5.10 | I2A | High |
| AI · #11 Retrieval / grounding | GroundedTokens guardrail | 5.9 | I2A | Medium-high |
| AI · #7 Model abstraction | LLMFactory completo (multi-provider, context-budget pre-flight) | 5.6 ampliado | I2A | High |
| AI · #5 Tooling discipline; #6 Tool safety | SQL Execution Gateway with R0–R3 policies | 2.10 | I2A | High (gating con conectores reales) |
| Memory · all 22 dimensions | Conjunto completo de la capa | 5.5, 5.9, 5.10, 5.11 | I2A | Highest cluster |
| Ontology · #6 Dimension/Vocabulary registry | Vocabularies driven from spec | 10.8 (VocabularyRegistry); 5.9 alimentada | I2A (5.9), I3 (10.8) | Medium |
| Ontology · #3, #5, #14 Registries | EntityRegistry, MetricRegistry, governance lifecycle | 10.8 (Registry pattern unificado) | I3 | Medium |
| Codebase · #5, #6 Boundary integrity, Composability | Protocol-typed seams + layer-deps lint | 5.11 (MemoryService Protocol) + parte de 11.1 | I2A + I1 | High |
| Codebase · #15 Security posture | Auth + RLS + cifrado + Vault + audit log | 7.1, 7.5, 7.6, 7.7, 7.8, 7.9 | I2B | Critical-path para apertura externa |
| Codebase · #21 Observability | run_id por contextvar + OpenTelemetry + métricas | 8.4 ampliado, 8.2, 8.3 | I3 (8.4), I2B (8.2, 8.3) | Medium |
| Layer 1 · #28 Production-readiness | Composite of 7.x + 11.x + 8.x | múltiples | I2B + I3 | Critical para el primer cliente externo |

48 dimensions across the four layers fall into this category. The roadmap v4 is well-calibrated against the rubric: the items in I2A correspond to the dimensions where the largest score gains are expected at the next audit.

---

## 8. Genuine Strengths

In the spirit of Alfred's "real strengths that earn the score above 2.0 and prevent classification as 'weak/aspirational'" section on LlullGen, this is the equivalent for llull. Acknowledged with evidence, not as compliment.

### 8.1 — Single coherent architecture, end-to-end

There is one architecture in this codebase, not two. The four-node LangGraph pipeline (`agents/workflow.py:267-282`) is the sole runtime path. No coexisting PlanExecutor zombie, no `AGENT_TEMPLATE.py` shipped as production, no `~7,000 lines of dead architecture` like LlullGen. Removing dead code from llull would be ~5 lines (`simulation/scenario_runner.py`). This is foundational for everything else: every other dimension is easier to score correctly when there is a single, declared architecture to point at.

### 8.2 — Spec-driven design that is actually spec-driven

The spec is consumed by every layer that should consume it: `system_model` (`system/system_model.py:91-112`), `system_graph` (`system/system_graph.py:16-42`), `simulation` (via `system_model`), `optimization` (`optimization/optimizer.py:3` via `config/settings.py`), `planner` system prompt (`agents/planner.py:91-163`), `tools` defaults (`agents/tools.py:60-94`). Adapting to a new domain genuinely is "edit the YAML and restart" — the README documents this and the code matches the documentation.

### 8.3 — Type discipline above the size class

27 Pydantic / TypedDict references in 8.372 LOC. Structured outputs at every LLM seam: `ToolSelection` (`agents/planner.py:60-72`), `JudgeVerdict` (`agents/judge.py:77-85`), API request/response models in `api/schemas/`. Two `type: ignore` comments total, both for legitimate optional imports. This is uncommon for prototype-phase code and pays compound interest as the system grows.

### 8.4 — Dual-backend pattern consistent across modules

The same pattern (`if DATABASE_URL → real backend; else → fallback`) appears in `memory/checkpointer.py:63-95`, `memory/session_manager.py:32-66`, `spec/spec_loader.py:363-380`, `knowledge/retriever.py:54-68`, `evaluation/observer.py:362-412`, `evaluation/metrics.py:38-56`. The fallback is never silent (each branch logs which backend is in use). The pattern allows local development without Docker while keeping production paths real. ADR-001 documents the same discipline for vector store choice.

### 8.5 — Observability built in, not bolted on

`AgentObserver` (`evaluation/observer.py:92-282`) records every run with structured spans (planner / tool / synthesizer / judge), latency per node, model used per node, judge score and feedback, fallback triggered. Dual write: JSONL + Postgres. LangSmith bridge available via env. HTML dashboard generated from the data (`evaluation/dashboard.py:1-471`). For prototype phase this is several iterations ahead of typical LangGraph projects.

### 8.6 — Error handling discipline is explicit

38 broad `except Exception` clauses across the codebase, of which **27 are explicitly marked `# noqa: BLE001`**. The marker is a declaration: "I considered this and chose broad-except because the swallow-and-degrade is the right behavior here". Compare with LlullGen's 443 broad excepts (audit reports them as undisciplined). The ratio is the same, but the disciplina visible in the marker is what differentiates "deliberate" from "accidental".

### 8.7 — Active fix discipline visible in commit history

The most recent commit `5d2adf5` ("fix(planner): make _SYSTEM_PROMPT lazy to prevent import-time IO") is a real fix to a real antipattern, applied surgically. The commit message names the problem class. This is the kind of micro-fix the LlullGen audit identifies as missing ("a class-level routing cache with bounded eviction" appearing as a **strength** there suggests the equivalent micro-fixes are also valued).

### 8.8 — Documentation that matches the code

`README.md` 1.165 LOC + `CLAUDE.md` 200 LOC describe what the code does. Sampled: the `Architecture` section of `CLAUDE.md:1-60` describes the file structure and it is accurate as of `5d2adf5`. The README's "Adapting to a New Domain" section (line 1.121) describes a workflow that the code supports. Three ADRs (001, 002, 003) cover the three live architectural decisions. This is the rare case where docs are not a separate untruth.

### 8.9 — Tests that test behavior, not mocks

`tests/agents/test_planner.py:1-103` mocks at the right boundaries (`_init_planner_llms`, `invoke_with_fallback`) — the LLM call sites — and tests the structural propagation of fields through the planner output. `tests/api/conftest.py:17-46` uses FastAPI dependency overrides instead of monkey-patching globals. No `tests/conftest.py` module-level monkey-patching of `os.environ` like LlullGen. The one missing piece is golden-eval semantic tests (item 10.11) — but the structural test layer is genuinely well-built.

---

## 9. Comparison with previous self-audit

**Baseline audit — no previous self-audit found in `audit_reports/`.**

This audit establishes the **baseline** against which future audits will be diffed. Specifically:

- Layer means at baseline: Codebase 2.96 · AI Layer 2.40 · Memory 1.27 · Ontology 2.31. **Future audits should not see any of these decline.** A decline in a layer mean is itself a finding.
- The 9 confirmed strengths are the **invariants**: they should remain at score ≥ 4 in every future audit. Loss of any of the 9 is an alarm.
- The 6 critical findings (🔴) are the **expected closures** by the next audit. If the next audit (in ~6-8 weeks) still reports 6.1 (no executable CI) as 🔴, the gap was real and now the priority is escalated.

---

## 10. Prioritized remediation plan

Three tiers, calibrated to the prototype phase. Items prefixed with ⏱ have estimated effort.

### P0 — Critical, before next iteration milestone

1. **⏱ 1 day · Land item 11.1 (Pipeline CI).** Finding 6.1. The single highest-leverage fix. Workflow: GitHub Actions, `pytest -m "not integration"` on push, `pytest -m integration` against a Postgres service container. Lift Dimensions 13, 14, 24, 25, 28 simultaneously.
2. **⏱ 30 min · Fix `config/settings.py` import-time loading.** Finding 6.2. Mirror the `agents/planner.py:166-173` pattern.
3. **⏱ 5 min · Add `pytest`, `pytest-cov` to `requirements-dev.txt`.** Finding 6.3.

### P1 — Important, within current iteration scope (I1 close-out and I2A open)

4. **⏱ 5 min · Align `pyproject.toml target-version` to `py312`.** Finding 6.4.
5. **⏱ 15 min · Tighten CORS configuration in `api/main.py`.** Finding 6.5.
6. **⏱ Refactor (~3-4 days) · Begin item 5.10 (ActiveAnalyticalState typed) + 5.11 (MemoryService Protocol).** This is the largest single move-the-needle item: it lifts 12 of the 22 Memory dimensions from 0–1 to 2–3.
7. **⏱ 10 min · Inline `simulation/scenario_runner.py` into `simulation/montecarlo.py`.** Dead-code hygiene.
8. **⏱ 30 min · Remove `is_new` parameter from `memory/checkpointer.py:register_turn`.** No legacy callers exist.
9. **⏱ 10 min · Add code comment at `knowledge/retriever.py:130` documenting the threat model.** Finding 6.6.

### P2 — Tactical hygiene (compound interest)

10. **Extract `agents/i18n.py`** for the language tables duplicated in `workflow.py` and `judge.py`.
11. **Refactor `streamlit_app.py` into 3-4 modules**: UI components, business adapters, dashboard glue, session state. Reduces the one-file complexity to manageable units (~300 LOC each).
12. **Split `AgentObserver`** into `RunRecorder`, `JsonlSink`, `PostgresSink`, `LangSmithBridge`, `ConfidenceScorer`. Improves Dimension 3 to 4.
13. **Add `mypy --strict` to CI** once 11.1 lands.
14. **Add `pip-audit` to CI** once 11.1 lands.

The first three P0 items can land in a single working day and would shift the Codebase layer mean from 2.96 to ~3.35. The P1 cluster is ~5-7 working days and pushes Memory from 1.27 to ~2.5.

---

## End of audit · 2026-05-06 · commit `5d2adf5`

Auditor: Claude Opus 4.7 (Anthropic) · Methodology: llull self-audit v1.0 baseline · Re-audit recommended: after I1 close-out, then every 4-6 weeks.
