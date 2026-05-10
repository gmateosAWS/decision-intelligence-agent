# CLAUDE.md

## What is this project

Decision Intelligence Agent ("llull") — a spec-driven agent that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning. The LLM orchestrates; Python computes. Evolving from prototype to product.

**Vision**: llull is a Decision Platform (Data + Knowledge + Decision). It answers "What should we do?" — not "What data do we have?" (Databricks) or "What do the data mean?" (Palantir). The platform is built on Inverence's 30+ years of domain modelling expertise (Bayesian, time series, causal inference) and makes that knowledge accessible through a conversational agentic interface and programmatic APIs/MCP.

## Architectural directives (apply to EVERY change)

These directives apply to every PR, every feature, every refactor. They are not optional. Claude Code must verify alignment before committing.

### Directive 1 — Product-grade, not prototype patches

Every change must be production-ready: proper error handling, tests, migrations, documentation. No "we'll fix it later" shortcuts. If a change is knowingly incomplete, document what the product version will require in a `TODO(product)` comment and a note in this file.

### Directive 2 — Alignment check with target architecture

Before implementing, verify the change aligns with:

- The CEO's "llull Decision Intelligence Architecture" diagram (7 blocks + transversals)
- The ADRs (001 pgvector, 002 LangGraph orchestration, 003 LlullGen component reuse)
- The inventory v4 (116 items) and roadmap v4 — check if later items subsume or extend what you're doing
- The skills engine concept (item 4.3) — every capability should eventually be exposable as a skill/MCP server

If a change touches something that a later inventory item will extend, implement it with that extension in mind from day one. Don't build a wall that the next iteration has to tear down.

### Directive 3 — API-first as pervasive principle

The FastAPI service (paquete 1B) is not a one-time "wrap the prototype" task — it's a design principle that applies to everything we build. Every new capability must be:

1. **Internally callable** as a typed Python function with clear contract
2. **Exposable via REST API** through a FastAPI router with Pydantic schemas
3. **Exposable via MCP** as a skill that external agents can consume (item 4.3)

This means: when you build a new tool, service, or analytical capability, design the interface first (input schema → output schema), then implement. The interface is the contract; the implementation is replaceable. If you find yourself writing logic that only Streamlit can call, refactor it behind an interface that the API and MCP can also call.

### Directive 4 — Skills-aware design

Every analytical capability (simulation, optimization, knowledge, future Inverence models) is a potential **skill** in the skills engine (item 4.3). Design with this in mind:

- Tools have typed input/output schemas (already done via `ToolSelection`)
- Results are structured dicts, not free text
- Each tool's contract is declared in the spec (or will be when 4.3 lands)
- The tool can be invoked independently of the LangGraph graph (for MCP exposure)

### Directive 5 — No orphaned implementations

When completing items from the original roadmap (v3), cross-reference against v4 to check:

- Has the item been subsumed by a v4 item? If so, implement the v4 version.
- Has the item been extended in v4? If so, implement with the extension in mind.
- Has the item become redundant? If so, skip it and document why.
- Does a later item depend on this one? If so, design the interface to support that dependency.

Example: item 5.7 (planner fallback) was in 1C originally, but was completed in 1D and is now subsumed by the LLMFactory pattern from ADR-003/paquete 2A.3. It no longer belongs in 1C.

## Core architecture

```
spec/organizational_model.yaml  ← seed + SQLite fallback (runtime: specs table in DB)
        │
        ├── spec/
        │    ├── spec_repository.py   CRUD: create/activate/update/seed specs in DB
        │    ├── spec_loader.py       get_spec() — DB-first, YAML fallback
        │    ├── versioning.py        SpecVersion, BumpType, validate_version, detect_bump_type
        │    └── autonomy.py          AutonomyPolicy, AutonomyLevel, ToolAutonomyPolicy
        │                             Foundation for items 7.3 + 5.3.b (per-agent policies)
        │
        ├── system/system_graph.py     DAG built from spec's causal_relationships
        ├── system/system_model.py     topological evaluation engine (formula registry)
        ├── simulation/montecarlo.py   Monte Carlo with noise from spec (temporal + non-linear)
        ├── optimization/optimizer.py  grid search over decision variable bounds
        ├── knowledge/retriever.py     pgvector search (FAISS fallback)
        │
        ├── prompts/
        │    ├── models.py             PromptRecord, PromptStatus (GovernableArtifact pattern, item 10.8)
        │    └── registry.py           CRUD + lifecycle (draft→certified→deprecated); get_prompt_template()
        │                              with inline-template fallback; seed_prompts_from_code() idempotent seed
        │
        ├── agents/
        │    ├── state.py              AgentState TypedDict (language, requires_confirmation,
        │    │                         requires_approval, confirmation_message,
        │    │                         planner/synthesizer/judge_prompt_version)
        │    ├── planner.py            LLM → ToolSelection; consults AutonomyPolicy per tool;
        │    │                         reads planner prompt from registry (fallback to inline)
        │    ├── llm_factory.py        get_chat_model() + invoke_with_fallback()
        │    ├── i18n.py              LANGUAGE_NAMES, get_synth/revise/directive helpers (skills-ready)
        │    ├── tools.py              tool wrappers consuming spec defaults
        │    ├── workflow.py           LangGraph: planner →[auto]→ tool → synthesizer → judge → END
        │    │                                            [policy]→ synthesizer (proposal) → judge
        │    │                         synthesizer reads prompt from registry (fallback to inline)
        │    ├── judge.py             online quality gate + single-pass revision;
        │    │                         judge + judge.revision prompts from registry (fallback to inline)
        │    └── runner.py            run_query(query, thread_id, observer, graph) → RunResult
        │                             shared by Streamlit UI + FastAPI (Directive 3)
        │
        ├── db/
        │    ├── engine.py             SQLAlchemy engine, get_session()
        │    ├── models.py             AgentSession, AgentRun (+3 prompt_version cols),
        │    │                         KnowledgeDocument, Spec, SpecVersion, Prompt
        │    └── migrations/           Alembic (001–003 existing; 004 prompts table;
        │                              005 prompt_version cols on agent_runs)
        │
        ├── memory/
        │    ├── checkpointer.py       PostgresSaver (SQLite fallback)
        │    └── session_manager.py    SQLAlchemy queries (SQLite fallback)
        │
        ├── evaluation/
        │    ├── observer.py           thin orchestrator: RunRecord accumulation + sink dispatch;
        │    │                         record_planner/synthesizer/judge accept prompt_version
        │    ├── confidence.py         ConfidenceScorer: 0-1 score from tool output (extractable skill)
        │    ├── sinks/
        │    │    ├── base.py          RunSink Protocol (ObjectBus-ready, item 1.6)
        │    │    ├── jsonl_sink.py    JsonlSink: appends to agent_runs.jsonl
        │    │    ├── postgres_sink.py PostgresSink: writes to agent_runs table
        │    │    └── langsmith_sink.py LangSmithBridge stub (TODO product)
        │    ├── metrics.py            reads from Postgres (JSONL fallback)
        │    └── dashboard.py          HTML dashboard
        │
        └── config/settings.py        lazy accessor functions over spec (no import-time IO)

api/
├── main.py              FastAPI app, lifespan, CORS; seeds spec + prompt registry at startup
├── dependencies.py      get_db, get_graph (lru_cache singletons)
├── routers/
│    ├── query.py         POST /v1/query
│    ├── sessions.py      CRUD /v1/sessions
│    ├── runs.py          GET /v1/runs
│    ├── specs.py         CRUD /v1/specs + POST /v1/specs/{id}/bump
│    │                    GET /v1/specs/{id}/autonomy
│    │                    PUT /v1/specs/{id}/autonomy → new spec version (MINOR bump)
│    ├── prompts.py       GET/POST /v1/prompts; GET /v1/prompts/{id}/{version}
│    │                    PUT /v1/prompts/{id}/{version}/certify|deprecate
│    └── health.py        /healthz, /readyz, /v1/debug/config
└── schemas/             Pydantic request/response models (incl. SpecBumpRequest/Response,
                         AutonomyPolicyUpdate, QueryResponse.requires_confirmation,
                         PromptResponse, PromptCreateRequest, PromptDeprecateRequest)

app.py                    REPL (legacy)
streamlit_app.py          Thin wrapper: st.set_page_config() + from ui.app import main
ui/
├── __init__.py
├── app.py              main() orchestrator — composes sidebar, header, tabs, chat
├── components.py       pure render functions (render_chat_message, render_result_cards, …)
├── dashboard.py        render_dashboard() — observability tab
├── sidebar.py          render_sidebar() — session mgmt, LLM config, domain, admin
├── session.py          init_session_state(), handle_query(), resume_session()
└── styles.py           CSS constants, LOGO_*, TOOL_LABELS, sanitize_markdown()
docker-compose.yml        PostgreSQL 16 + pgvector
alembic.ini               migration config
tests/                    unit + integration tests
docs/                     inventario v4, roadmap v4, ADRs, audit reports
```

## Design principles (non-negotiable)

1. **Spec-driven**: domain knowledge in spec DB (versioned); YAML is seed + fallback
2. **LLM orchestrates, never computes**: structured output selects tools
3. **Tools are pure functions**: (spec, params) → result
4. **The graph is the architecture**: LangGraph defines the flow
5. **Provider-agnostic**: multi-provider via `llm_factory.py`
6. **Product-grade**: proper migrations, error handling, tests, Docker
7. **Dual-backend**: Postgres primary, SQLite/FAISS fallback when `DATABASE_URL` not set
8. **API-first**: every capability callable via REST and eventually via MCP
9. **Skills-aware**: every analytical tool is a potential skill for external consumption

## MANDATORY: Documentation updates on every PR

**Every PR must update ALL relevant documentation. This is not optional.**

1. **`CLAUDE.md`** — architecture diagram, completed items, current work
2. **`README.md`** — file tree, setup steps, env vars, features
3. **`docs/llull_roadmap_v4.md`** — mark items completed if applicable, update paquete status
4. **`docs/llull_roadmap_visual.html`** — mark items completed if applicable, update paquete status
5. **`docs/llull_inventario_v4.md`** — mark items completed if applicable
6. **`docs/adr-*.md`** — new ADR if architectural decision was made
7. **`.env.example`** — new environment variables
8. **`docs/2026-05-06_llull_self_audit.md`** — mark findings as fixed if applicable

## MANDATORY: Pre-commit discipline

Run `black` and `ruff` BEFORE committing, not after. Pre-commit hooks will reject non-compliant code. Save time by running them proactively:

```bash
black . && ruff check --fix .
```

## Database

PostgreSQL 16 with pgvector. Docker Compose + Alembic.

```env
DATABASE_URL=postgresql://llull:llull@localhost:5432/llull
```

Six tables: `agent_sessions`, `agent_runs`, `knowledge_documents`, `specs`, `spec_versions`, `prompts`.

Without `DATABASE_URL`, falls back to SQLite + FAISS automatically.

## LLM configuration

```env
PLANNER_PROVIDER=openai
PLANNER_MODEL=gpt-4o-mini
SYNTHESIZER_PROVIDER=openai
SYNTHESIZER_MODEL=gpt-4o-mini
JUDGE_PROVIDER=openai
JUDGE_MODEL=gpt-4o-mini
FALLBACK_PROVIDER=anthropic
FALLBACK_MODEL=claude-sonnet-4-20250514
LLM_MAX_RETRIES=2
LLM_TIMEOUT=30
HISTORY_WINDOW=3
```

## Build and run

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt    # pytest, black, ruff, pre-commit
docker compose up -d
alembic upgrade head
python data/generate_data.py
python models/train_demand_model.py
python knowledge/build_index.py
streamlit run streamlit_app.py          # Web UI
uvicorn api.main:app --reload --port 8000  # API
```

## Testing

```bash
pytest                                  # unit tests
pytest -m integration                   # DB tests (needs Docker)
pytest --cov=. --cov-report=term-missing  # with coverage
mypy --ignore-missing-imports --no-strict-optional --warn-return-any --warn-unused-configs --explicit-package-bases agents/ api/ spec/ system/ simulation/ optimization/ config/ db/ memory/ evaluation/
pip-audit --strict --desc               # supply-chain scan (run manually or in CI)
```

## Conventions

`black` (88), `ruff`, type hints, numpy docstrings, no bare except, config via .env/YAML. Every feature includes tests. Every PR updates docs. Pre-commit hooks run before commit.

## What NOT to change without discussion

Spec-driven principle, graph structure, `ToolSelection` schema (tool, reasoning, params, language), `_NODE_FORMULAS` registry.

## Git workflow

`feature/<item-id>-<desc>`, commits `[<item-id>] <desc>`, PRs into main.

## Completed items

### Paquete 1D ✅

- [x] 5.5, 5.6, 12.4, 12.5, 5.7, 4.1

### Paquete 1E ✅

- [x] 6.6 Streamlit UI + UX polish + Community Cloud + dashboard tab + admin panel
- [x] Planner-driven language detection (ISO 639-1 via ToolSelection.language)
- [x] Temporal data generation (36 months, seasonality, trend, log-marketing, quadratic price)

### Paquete 1A ✅

- [x] 1.1 PostgreSQL, 1.2 pgvector, 8.1 runs in Postgres, 1.5 spec as data, 1.3 ADR

### Paquete 1B ✅

- [x] 6.1.e Agent Service (FastAPI), 6.4 health endpoints, 6.5 API versioning /v1/

### Paquete 1C ✅

- [x] 11.1 CI pipeline: `.github/workflows/ci.yml` (unit job: black+ruff+pytest -m "not integration"; integration job: Postgres service + alembic + data bootstrap)
- [x] 11.3 Dockerfile multi-stage + `.dockerignore` + docker-compose api service + postgres healthcheck
- [x] 5.2 Test suites v1: `tests/evaluation/test_agent_golden.py` (15 canonical queries: routing, param propagation, result shape) + `tests/ci/test_smoke.py` (import smoke + health endpoints). 76 unit tests total.

### Audit fixes ✅

- [x] P02: config/settings.py lazy (finding 6.2)
- [x] P03: pytest + pytest-cov in requirements-dev (finding 6.3)
- [x] P1 hygiene: pyproject target py312 (6.4), CORS tightened (6.5), scenario_runner inlined, is_new removed, FAISS threat model documented (6.6)
- [x] Fix: planner \_SYSTEM_PROMPT lazy (import-time IO)
- [x] P2.1: `agents/i18n.py` extracted — LANGUAGE_NAMES, SYNTH_INSTRUCTIONS, REVISE_INSTRUCTIONS, get_system_language_directive(); workflow.py + judge.py refactored; 9 tests added
- [x] P2.3: `evaluation/observer.py` split into RunSink Protocol + JsonlSink + PostgresSink + LangSmithBridge + ConfidenceScorer; public API unchanged; 28 new tests in `tests/evaluation/test_sinks.py`
- [x] P2.4: mypy (intermediate level, --explicit-package-bases) + pip-audit (continue-on-error) added to CI Job 1; 21 pre-existing type errors fixed or suppressed
- [x] P2.2: `streamlit_app.py` (~1040 LOC) split into `ui/` package + `agents/runner.py`; multi-turn rendering bug fixed; API and UI share same `run_query()` code path (Directive 3); 113 unit tests pass

### Item 3.6 ✅

- [x] 3.6 Semantic versioning for specs: `spec/versioning.py` (SpecVersion, BumpType, detect_bump_type), semver validation in create_spec/update_spec/seed_from_yaml, auto-bump from YAML diff, monotonicity check, `POST /v1/specs/{id}/bump` endpoint, migration 003 CHECK constraint

### Item 3.5 ✅

- [x] 3.5 Autonomy policies in spec: `spec/autonomy.py` (AutonomyLevel, ToolAutonomyPolicy, AutonomyPolicy), `autonomy_policy` section in YAML + spec_loader, planner consults policy after tool selection, conditional edge `_route_after_planner` in workflow (skips tool when policy ≠ auto), `GET/PUT /v1/specs/{id}/autonomy` endpoints, 26 new tests. Foundation for items 7.3 + 5.3.b.

### Item 10.1 ✅

- [x] 10.1 Prompt Registry: `prompts/` package (models.py, registry.py); `PromptRecord` as first GovernableArtifact (10.8-ready); `PromptStatus` lifecycle draft→certified→deprecated; `get_prompt_template(stage, fallback)` registry-with-fallback pattern for all 3 agents; migration 004 (prompts table, semver+status CHECKs), migration 005 (3 prompt_version cols on agent_runs); `seed_prompts_from_code()` idempotent seed at startup; 5 CRUD+lifecycle REST endpoints (`/v1/prompts`); prompt_version propagated through AgentState → RunRecord → PostgresSink → agent_runs rows; 220 tests pass (15 new in tests/prompts/, 10 new in tests/api/).

## Current work: Item 10.1 (Prompt Registry) — Next: Item 1.6 ObjectBus

**Branch**: `feature/10.1-prompt-registry`

Completed 2026-05-10.

### Audit P2.2 — Streamlit split into ui/ package + Directive 3 runner

`streamlit_app.py` (~1040 LOC) was a monolith mixing UI rendering, session management,
agent invocation, and dashboard logic. Split into:

- `agents/runner.py` — `RunResult` dataclass + `run_query(query, thread_id, observer, graph) → RunResult`
  (Directive 3: shared by Streamlit UI and FastAPI, callable independently for MCP future)
- `ui/styles.py` — CSS constants, logos, TOOL_LABELS, `sanitize_markdown()`
- `ui/components.py` — pure render functions (no session_state access)
- `ui/dashboard.py` — `render_dashboard()` extracted from inline code
- `ui/sidebar.py` — `render_sidebar()` with all sidebar sections
- `ui/session.py` — `init_session_state()`, `handle_query()`, `resume_session()`
- `ui/app.py` — `main()` orchestrator
- `streamlit_app.py` — 10-line thin wrapper: `st.set_page_config()` + `main()`

**Multi-turn rendering bug fixed**: previous code rendered current-turn messages OUTSIDE
`with tab_chat:`, causing them to appear below the tab panel. Fix: all rendering happens
INSIDE `with tab_chat:`. `handle_query()` updates `session_state` only (no rendering).

**API updated**: `api/routers/query.py` now delegates to `agents.runner.run_query()`.
Error types (`LLMUnavailableError`) propagated via `RunResult.error_type` for 503 vs 500
HTTP status distinction.

**Next: Item 1.6 ObjectBus** — deferred until we have access to LlullGen codebase for reference (per ADR-003 Principle 1: read the code as reference). After that, continue I2A with remaining LLMOps items (10.2 A/B testing, 10.3 shadow evaluation). Item 3.6 (spec semver) and 10.1 (prompt registry) from I2A completed ahead of schedule.

## Pending improvements (noted, not blocking)

- API `POST /v1/query` should accept optional `context.month` param (noted when temporal data was added)
- Streamlit Community Cloud uses SQLite checkpointer (no langgraph-checkpoint-postgres) — acceptable for demo
- Neon Postgres connection: verify spec is seeded to v1.3.0 with temporal fields

## Reference documents

- `docs/llull_inventario_v4.md` — full backlog (116 items)
- `docs/llull_roadmap_v4.md` — iteration plan with progress
- `docs/adr-001-pgvector-over-qdrant.md`
- `docs/adr-002-langgraph-orchestration.md` (ADR-002)
- `docs/adr-003-llullgen-component-reuse-policy.md` (ADR-003)
- `docs/2026-05-06_llull_self_audit.md` — architecture audit with findings
