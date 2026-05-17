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
- The ADRs (001 pgvector ⚠️ superseded, 002 LangGraph orchestration, 003 LlullGen component reuse, 005 pgvector + pgvectorscale strategy)
- The inventory v4 (117 items) and roadmap v4 — check if later items subsume or extend what you're doing
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
        │    ├── spec_loader.py       get_spec() — DB-first, YAML fallback;
        │    │                        DecisionVariable + TargetVariable now have aliases: list[str];
        │    │                        DerivedMetric dataclass (id, name, description, unit, aliases);
        │    │                        OrganizationalModelSpec.derived_metrics: List[DerivedMetric] (item 5.9)
        │    ├── versioning.py        SpecVersion, BumpType, validate_version, detect_bump_type
        │    └── autonomy.py          AutonomyPolicy, AutonomyLevel, ToolAutonomyPolicy
        │                             Foundation for items 7.3 + 5.3.b (per-agent policies)
        │
        ├── system/system_graph.py     DAG built from spec's causal_relationships
        ├── system/system_model.py     topological evaluation engine (formula registry)
        ├── system/grounded_tokens.py  Spec-driven vocabulary guardrail (item 5.9):
        │                              Vocabulary (frozenset of canonical + alias tokens);
        │                              validate_strict(token, vocab) — blocking (planner);
        │                              check_observational(tokens, vocab) — non-blocking (judge);
        │                              build_vocabulary(spec) cached by spec.version;
        │                              invalidate_vocabulary_cache() for tests/hot-reload.
        │                              Lives in system/ NOT agents/ (Directive 4 — skills-ready)
        ├── simulation/montecarlo.py   Monte Carlo with noise from spec (temporal + non-linear)
        ├── optimization/optimizer.py  grid search over decision variable bounds
        ├── knowledge/retriever.py     pgvector search (FAISS fallback — local dev only, per ADR-005)
        │
        ├── prompts/
        │    ├── models.py             PromptRecord, PromptStatus (GovernableArtifact pattern, item 10.8)
        │    │                         PromptVariant, PromptVariantStatus (item 10.2)
        │    ├── routing.py            select_variant(stage, session_id) → PromptVariant | None
        │    │                         Deterministic sha256-bucket routing; lru_cache per stage;
        │    │                         invalidate_variant_cache() called by all mutation functions
        │    └── registry.py           CRUD + lifecycle (draft→certified→deprecated); variant CRUD
        │                              (start_rollout, adjust_rollout, promote_to_champion, deprecate_variant);
        │                              get_prompt_template(stage, fallback, session_id) → (content, version, label);
        │                              _get_cached_prompt_content lru_cache (immutable by (id, version));
        │                              seed_prompts_from_code() seeds prompts + CHAMPION variants idempotently
        │
        ├── agents/
        │    ├── state.py              AgentState TypedDict (language, requires_confirmation,
        │    │                         requires_approval, confirmation_message,
        │    │                         planner/synthesizer/judge_prompt_version,
        │    │                         clarification_needed, ungrounded_token,
        │    │                         clarification_message — item 5.9)
        │    ├── planner.py            LLM → ToolSelection; consults AutonomyPolicy per tool;
        │    │                         reads planner prompt from registry (fallback to inline);
        │    │                         validate_strict() inner check on params (item 5.9 blocking)
        │    ├── llm_factory.py        get_chat_model() + invoke_with_fallback() + _extract_usage()
        │    │                         _extract_usage() handles 3 patterns: (1) direct AIMessage.usage_metadata
        │    │                         (synthesizer/revision), (2) dict["raw"] from with_structured_output(include_raw=True)
        │    │                         (planner/judge), (3) response_metadata.token_usage fallback.
        │    │                         IMPORTANT: all with_structured_output() chains MUST use include_raw=True
        │    │                         so the raw AIMessage (with token counts) is preserved alongside the parsed model.
        │    ├── i18n.py              LANGUAGE_NAMES, get_synth/revise/directive helpers (skills-ready)
        │    ├── tools.py              tool wrappers consuming spec defaults
        │    ├── workflow.py           LangGraph: planner →[auto]→ tool → synthesizer → judge → END
        │    │                                            [policy]→ synthesizer (proposal) → judge
        │    │                                            [clarification]→ clarification → END (item 5.9)
        │    │                         synthesizer reads prompt from registry (fallback to inline)
        │    ├── judge.py             online quality gate + single-pass revision;
        │    │                         judge + judge.revision prompts from registry (fallback to inline)
        │    └── runner.py            run_query(query, thread_id, observer, graph) → RunResult
        │                             shared by Streamlit UI + FastAPI (Directive 3)
        │
        ├── db/
        │    ├── engine.py             SQLAlchemy engine, get_session()
        │    ├── models.py             AgentSession (+analytical_state JSONB + version col),
        │    │                         AgentRun (+3 prompt_version cols + 6 cost cols),
        │    │                         SessionStateTransition (item 5.10 audit log),
        │    │                         KnowledgeDocument, Spec, SpecVersion, Prompt
        │    └── migrations/           Alembic 001–007 (007: analytical_state +
        │                              session_state_transitions table)
        │
        ├── memory/
        │    ├── checkpointer.py       PostgresSaver (SQLite fallback)
        │    ├── session_manager.py    SQLAlchemy queries (SQLite fallback)
        │    ├── state/
        │    │    ├── types.py         Intent (closed enum), ResolvedMetric, SlotProvenance
        │    │    ├── active.py        ActiveAnalyticalState (mutable) + FrozenActiveAnalyticalState
        │    │    │                    Single source of typed analytical context between turns.
        │    │    │                    frozen() returns immutable deep-copy for consumers.
        │    │    └── audit.py         StateTransition, TransitionOp — append-only mutation log
        │    ├── service.py             LocalMemoryService — concrete MemoryService implementation.
        │    │                          Coordinator cache (session_id → MemoryCoordinator).
        │    │                          _get_or_load() lazy DB load, fail-open on error.
        │    │                          get_memory_service() singleton (process-level).
        │    └── coordinator/
        │         ├── coordinator.py   MemoryCoordinator — ONLY writer of ActiveAnalyticalState
        │         │                    Single-writer pattern: all other code reads frozen() snapshots.
        │         │                    persist_to_db() / load_from_db() — Postgres + fail-open.
        │         │                    Used only by LocalMemoryService (item 5.11 boundary).
        │         └── intent_mapping.py  map_tool_to_intent(tool) → Intent
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

core/                                 Shared contracts and protocols (PEP 544) — item 5.11
├── __init__.py
└── protocols/
     ├── __init__.py
     └── memory.py                   MemoryService Protocol (@runtime_checkable) — 7 methods.
                                     StateProposal, StateCommitDecision, StateCommitResult (v1 stubs).
                                     Only seam through which agents/API/UI interact with memory.

governance/
└── memory_boundary_exceptions.yaml  Allowlist for justified exceptions to memory boundary lint.
                                     Empty in v1 — entries added with sunset dates as tech debt resolves.

scripts/
└── check_memory_boundary.py         Boundary lint (item 5.11) — blocks direct imports of
                                     memory.coordinator.* / memory.state.* outside memory/.
                                     Run in CI + pre-commit; excluded from its own scan.

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

## MANDATORY: Consult technical debt register before implementing

**Before starting any implementation, check `docs/tech_debt.md`.**

If the work you are about to do touches a known debt entry (e.g., ObjectBus fields,
ObjectId types), you MUST:
1. Note the dependency in the PR description
2. Implement in the constrained way documented (not the final form)
3. Add/update the relevant `TODO(X.Y/component)` comment in code
4. NOT remove the debt entry — it stays until the blocking item ships

If the work you are completing resolves a debt entry, strike it through in
`docs/tech_debt.md` and add a "Resolved in: [item]" note.

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
9. **`docs/tech_debt.md`** — add new entries for knowingly transitional implementations;
   resolve entries when the blocking dependency ships

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

Seven tables: `agent_sessions`, `agent_runs`, `knowledge_documents`, `specs`, `spec_versions`, `prompts`, `session_state_transitions`.

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
mypy --config-file=mypy-agents-strict.ini --explicit-package-bases agents/  # strict zone (L1 dim 17)
pip-audit --strict --desc               # supply-chain scan (run manually or in CI)
```

## Conventions

`black` (88), `ruff`, type hints, numpy docstrings, no bare except, config via .env/YAML. Every feature includes tests. Every PR updates docs. Pre-commit hooks run before commit.

## What NOT to change without discussion

Spec-driven principle, graph structure, `ToolSelection` schema (tool, reasoning, params, language), `_NODE_FORMULAS` registry.

## Plan review discipline (before any implementation)

Inspired by Garry Tan's Claude Code senior engineer prompt, adapted to llull's
spec-driven workflow. The architectural decisions are taken upstream (Claude + architect)
and arrive in the prompt as a detailed spec. Claude Code's role is NOT to redesign,
but to act as a senior reviewer who catches subtle issues BEFORE writing code.

Every implementation prompt that lands on Claude Code must begin with a "Plan review"
phase before touching any code:

### Plan review — required output before implementation

1. **Restatement (5–6 lines)**: summarize the intent of the item in your own words.
   State what changes, what stays, and what is the user-visible effect.

2. **Concrete risks (2–3 items)**: name specific risks tied to the existing code,
   not generic ones. Examples of good risks:
     - "If I add field X to AgentState, the PostgresSink INSERT at sinks/postgres_sink.py:46
       needs the new column or it will fail silently."
     - "The boundary lint at scripts/check_memory_boundary.py will block imports if I
       forget to add the new module to its allowlist."
   Examples of bad (too generic) risks:
     - "This might break things." → useless.
     - "Tests might fail." → not actionable.

3. **Assumptions to confirm (if any)**: list assumptions you are about to make that
   are not explicit in the prompt. Stop and ask if any is uncertain. If all are
   obvious from the existing code, say "no clarifications needed" and proceed.

4. **Engineering principles to follow (acknowledge):**
   - DRY — flag duplication aggressively before introducing it.
   - Tests are mandatory; better too many than too few.
   - "Engineered enough" — not fragile, not over-engineered.
   - Correctness and edge cases > implementation speed.
   - Explicit > clever.
   - Backward compatibility is non-negotiable unless the prompt explicitly says
     otherwise. The UI and the API must keep working identically.

Only after the Plan review is shown should implementation start. The user reads
the Plan review and either approves or sends adjustments before any code lands.

For routine items (small, well-bounded, obvious risk profile), the Plan review
can be condensed to 3–4 lines. For BIG changes (touching the agent workflow, the
memory layer, the API contracts, the database schema, the CI pipeline, the spec
system, the prompt registry), the Plan review is mandatory in full form.

### What this is NOT

This discipline does NOT mean Claude Code redesigns the architecture. The
architecture is decided upstream and lives in:
- The Memory Architecture target documents
- The five Architectural Directives in this CLAUDE.md
- ADR-002, ADR-003, ADR-005
- The inventory v4 and roadmap v4

Claude Code's review is a final safety net against subtle integration mistakes,
not an invitation to question architectural decisions.

---

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

- [x] 1.1 PostgreSQL, 1.2 pgvector + pgvectorscale (ADR-005), 8.1 runs in Postgres, 1.5 spec as data, 1.3 triggers formales

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

### Item 3.3 ✅

- [x] 3.3 DAG cycle assertion: `assert_dag_acyclic()` in `system/system_graph.py` (called at graph-build time); lazy-import hook in `spec_loader._parse_raw()` (called on every spec load, avoids circular import); `_validate_dag_acyclic()` in `spec_repository.create_spec()` and `update_spec()` (called before DB write, uses inline networkx). 7 tests: `tests/system/test_dag_cycle.py` (6 unit tests), `tests/api/test_spec_cycle_validation.py` (1 API test: POST /v1/specs with cycle → 422).

### Supply-chain lock files ✅

- [x] `requirements.lock` and `requirements-dev.lock` generated with `pip-compile --generate-hashes --allow-unsafe`. Dockerfile uses `pip install --no-cache-dir --no-deps -r requirements.lock`. CI uses `pip install --no-deps -r requirements-dev.lock` (superset). `requirements.txt` preserved for Streamlit Community Cloud.

### Item 5.10 ✅

- [x] 5.10 ActiveAnalyticalState MVP v1: `memory/state/types.py` (Intent enum, ResolvedMetric, SlotProvenance); `memory/state/active.py` (ActiveAnalyticalState mutable Pydantic model + FrozenActiveAnalyticalState immutable subclass with deep-copy via `.frozen()`); `memory/state/audit.py` (StateTransition, TransitionOp — append-only log); `memory/coordinator/coordinator.py` (MemoryCoordinator — single writer, persist_to_db/load_from_db fail-open); `memory/coordinator/intent_mapping.py` (map_tool_to_intent); migration 007 (analytical_state JSONB + session_state_transitions table); wired into `agents/runner.py` + `agents/workflow.py` (planner records intent, tool_node records active run); `GET /v1/sessions/{id}/state` + `/state/audit` read-only endpoints; `docs/tech_debt.md` (ObjectBus migration path); 24 new tests (281 total). v2 slots (dimensions, period, geography) deferred to 5.11.

### Item 5.11 ✅

- [x] 5.11 MemoryService Protocol: `core/protocols/memory.py` (`MemoryService` Protocol with `@runtime_checkable`, 7 methods); `memory/service.py` (`LocalMemoryService` — concrete implementation with coordinator cache, lazy DB load, fail-open); `memory/__init__.py` updated with `LocalMemoryService` + `get_memory_service()` process-level singleton; `agents/runner.py` + `agents/workflow.py` + `api/routers/sessions.py` refactored to use service (not coordinator directly); `agents/planner.py` reads frozen `active_state` snapshot and injects typed context into prompt; `scripts/check_memory_boundary.py` (boundary lint — blocks direct imports of `memory.coordinator.*` / `memory.state.*` outside `memory/`); `governance/memory_boundary_exceptions.yaml` (allowlist for justified exceptions); boundary lint in CI + pre-commit hook; `propose_state_update` / `commit_state_update` as v1 stubs (see `docs/tech_debt.md`, unblocked by 5.13); 22 new tests (303 total, includes 11 protocol, 4 planner, 5 lint, 2 API v2).

### Hardening: mypy --strict on agents/ ✅

- [x] `mypy-agents-strict.ini` — dedicated mypy config: `[mypy-agents.*] strict = True` + `follow_imports = silent` for all non-agents packages (prevents strict-check leakage into imported modules)
- [x] All 8 `agents/` files pass `mypy --config-file=mypy-agents-strict.ini --explicit-package-bases agents/` with 0 errors
- [x] Fixes: `_build_few_shot_examples(spec: Any)`, `_build_system_prompt() -> tuple[str, Optional[str]]`, `planner_node() -> dict[str, Any]`, `judge_node() → Optional[Any]` config, `action: str = state.get("action") or "unknown"` narrowing, `_get_observer/tracker() -> Any`, `build_graph(checkpointer: Any = None) -> Any`, all 4 node functions `-> dict[str, Any]`, 2 `# type: ignore[no-untyped-call]` for cross-zone calls (SystemModel, optimize_price, get_checkpointer)
- [x] `agents/` uses mypy --strict in CI (L1 dim 17: type safety 4→5) and pre-commit (`mirrors-mypy` hook, `files: ^agents/.*\.py$`)
- [x] Strict CI step added after existing mypy step in `.github/workflows/ci.yml`

### Item 10.2 ✅

- [x] 10.2 Prompt A/B Testing: `prompts/models.py` (`PromptVariantStatus` + `PromptVariant` Pydantic model); `prompts/routing.py` (deterministic `select_variant()` via sha256 bucket, `_load_active_variants` with `@lru_cache(maxsize=8)`, `invalidate_variant_cache()` called on every mutation); `prompts/registry.py` (`start_rollout`, `adjust_rollout`, `promote_to_champion`, `deprecate_variant` CRUD + `list_variants` + `get_variant`; `get_prompt_template()` promoted to 3-tuple `(content, version, variant_label)`; `_get_cached_prompt_content` `@lru_cache(maxsize=256)` for immutable prompt content; `seed_prompts_from_code()` auto-creates CHAMPION variants at startup); migration 008 (`prompt_variants` table with CHECK constraints and FK to `prompts`); migration 009 (3 `*_variant_label` Text columns on `agent_runs`); `db/models.py` `PromptVariantRow` ORM + 3 `AgentRun` columns; `agents/state.py` 3 new `*_variant_label` fields; `agents/planner.py` module-level cache removed (spec caching in `spec_loader`), `session_id` param added to `_build_system_prompt()` + `planner_node()`; all 4 `get_prompt_template` call sites (planner, synthesizer, judge, judge.revision) updated to 3-tuple unpack; `evaluation/observer.py` `RunRecord` + `record_planner/synthesizer/judge()` extended with `variant_label`; `evaluation/sinks/postgres_sink.py` 3 new kwargs; 6 new API endpoints (`GET /v1/prompts/variants`, `GET/POST/PUT /v1/prompts/variants/{stage}/{label}`, `PUT .../adjust`, `PUT .../promote`, `PUT .../deprecate`); read-only variant table in `ui/dashboard.py`; 27 new tests (routing, registry 3-tuple, observer). Tech debt entry: 10.2→10.3 (auto-promotion deferred).

### Item 5.9 ✅

- [x] 5.9 GroundedTokens guardrail: `system/grounded_tokens.py` (`Vocabulary`, `UngroundedTokenError`,
  `UngroundedMention`, `build_vocabulary(spec)` / `get_vocabulary(spec)` cached by `spec.version`,
  `validate_strict()` blocking check, `check_observational()` non-blocking scan,
  `invalidate_vocabulary_cache()`); `spec/spec_loader.py` extended with `aliases: list[str]` on
  `DecisionVariable` + `TargetVariable`, new `DerivedMetric` dataclass, `derived_metrics` on
  `OrganizationalModelSpec`; `agents/planner.py` inner try/except catches `UngroundedTokenError`
  and returns `clarification_needed=True` state dict; `agents/workflow.py` adds `clarification_node`
  + `_route_after_planner` returns "clarification" as priority branch; `agents/judge.py`
  `check_observational()` scan on `raw_result.keys()`, prefixes `judge_feedback` with
  `[ungrounded: ...]`; `agents/state.py` 3 new fields
  (`clarification_needed`, `ungrounded_token`, `clarification_message`);
  `agents/runner.py` `RunResult.clarification_needed/message` + early return on clarification;
  `api/schemas/query.py` + `api/routers/query.py` return HTTP 200 with clarification fields;
  `ui/components.py` `render_clarification_message()` with `st.info()` style;
  `tests/fixtures/healthcare_demo_spec.yaml` healthcare domain (not retail) proves no hardcoding;
  34 new tests (21 grounded_tokens, 3 planner, 2 judge, 7 workflow+clarification, 1 API);
  tech debt entry "5.9 → futuro: Near-match suggestion" in `docs/tech_debt.md`. 370 tests total.

## Current work: Item 5.9 ✅ — Next: Item 10.3 (eval-gated auto-promotion) or 5.13 (state mutations)

**Branch**: `feature/5.9-grounded-tokens`

5.9 Completed 2026-05-17.
10.2 Completed 2026-05-17.

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

Item 3.6 (spec semver) and 10.1 (prompt registry) from I2A completed ahead of schedule. Item 5.10 (ActiveAnalyticalState MVP) completed 2026-05-13. Item 5.11 (MemoryService Protocol + boundary lint) completed 2026-05-14. Next: Item 1.6 ObjectBus deferred until LlullGen codebase is accessible (per ADR-003); 5.13 (user-correction mutations) is the natural continuation of 5.11.

### Item 8.7.a + 8.7.b ✅

- [x] 8.7.a LLM cost tracking: `config/model_pricing.yaml` (pricing table, all providers), `evaluation/cost.py` (ModelPricing, calculate_cost_usd, reload_pricing), `evaluation/currency.py` (Frankfurter API USD→EUR, 1-hour cache, env fallback)
- [x] 8.7.b Hard ceilings per run: `evaluation/budget.py` (RunBudget.from_env(), BudgetTracker, BudgetExceededError); tracker wired through `invoke_with_fallback()` in `agents/llm_factory.py`; passed via `config["configurable"]["budget_tracker"]` to all nodes (planner, synthesizer, judge, revision)
- [x] Cost fields propagated: RunResult → QueryResponse → RunRecord → PostgresSink → `agent_runs` table (migration 006)
- [x] Budget endpoints: `GET /v1/budget/current` + `GET /v1/budget/exchange-rate` in `api/routers/budget.py`
- [x] UI: cost metrics in `render_technical_details()` + cost KPIs row in dashboard
- [x] 25 new tests (test_cost.py, test_currency.py, test_budget.py, test_runner_budget.py, test_query_cost_in_response.py)

## Pending improvements (noted, not blocking)

- API `POST /v1/query` should accept optional `context.month` param (noted when temporal data was added)
- Streamlit Community Cloud uses SQLite checkpointer (no langgraph-checkpoint-postgres) — acceptable for demo
- Neon Postgres connection: verify spec is seeded to v1.3.0 with temporal fields

## Reference documents

- `docs/llull_inventario_v4.md` — full backlog (117 items)
- `docs/llull_roadmap_v4.md` — iteration plan with progress
- `docs/adr-001-pgvector-over-qdrant.md` ⚠️ SUPERSEDED by ADR-005
- `docs/adr-002-langgraph-orchestration.md` (ADR-002)
- `docs/adr-003-llullgen-component-reuse-policy.md` (ADR-003)
- `docs/ADR-005-vector-store-strategy.md` (ADR-005) — pgvector + pgvectorscale strategy, supersedes ADR-001
- `docs/2026-05-06_llull_self_audit.md` — architecture audit with findings
