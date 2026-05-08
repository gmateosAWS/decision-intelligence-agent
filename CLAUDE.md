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
        │    └── spec_loader.py       get_spec() — DB-first, YAML fallback
        │
        ├── system/system_graph.py     DAG built from spec's causal_relationships
        ├── system/system_model.py     topological evaluation engine (formula registry)
        ├── simulation/montecarlo.py   Monte Carlo with noise from spec (temporal + non-linear)
        ├── optimization/optimizer.py  grid search over decision variable bounds
        ├── knowledge/retriever.py     pgvector search (FAISS fallback)
        │
        ├── agents/
        │    ├── state.py              AgentState TypedDict (includes language: str)
        │    ├── planner.py            LLM → ToolSelection(tool, reasoning, params, language)
        │    ├── llm_factory.py        get_chat_model() + invoke_with_fallback()
        │    ├── i18n.py              LANGUAGE_NAMES, get_synth/revise/directive helpers (skills-ready)
        │    ├── tools.py              tool wrappers consuming spec defaults
        │    ├── workflow.py           LangGraph: planner → tool → synthesizer → judge → END
        │    └── judge.py             online quality gate + single-pass revision
        │
        ├── db/
        │    ├── engine.py             SQLAlchemy engine, get_session()
        │    ├── models.py             AgentSession, AgentRun, KnowledgeDocument, Spec, SpecVersion
        │    └── migrations/           Alembic (001_initial_schema, 002_spec_tables)
        │
        ├── memory/
        │    ├── checkpointer.py       PostgresSaver (SQLite fallback)
        │    └── session_manager.py    SQLAlchemy queries (SQLite fallback)
        │
        ├── evaluation/
        │    ├── observer.py           dual-write: JSONL + Postgres
        │    ├── metrics.py            reads from Postgres (JSONL fallback)
        │    └── dashboard.py          HTML dashboard
        │
        └── config/settings.py        lazy accessor functions over spec (no import-time IO)

api/
├── main.py              FastAPI app, lifespan, CORS (tightened per audit 6.5)
├── dependencies.py      get_db, get_graph (lru_cache singletons)
├── routers/
│    ├── query.py         POST /v1/query
│    ├── sessions.py      CRUD /v1/sessions
│    ├── runs.py          GET /v1/runs
│    ├── specs.py         CRUD /v1/specs
│    └── health.py        /healthz, /readyz, /v1/debug/config
└── schemas/             Pydantic request/response models

app.py                    REPL (legacy)
streamlit_app.py          Web UI (chat + DAG + charts + dashboard + admin)
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
3. **`docs/llull_roadmap_v4.md`** — mark items completed, update paquete status
4. **`docs/llull_roadmap_visual.html`** — mark items completed, update paquete status
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

Five tables: `agent_sessions`, `agent_runs`, `knowledge_documents`, `specs`, `spec_versions`.

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
- [x] P2.4: mypy (intermediate level, --explicit-package-bases) + pip-audit (continue-on-error) added to CI Job 1; 21 pre-existing type errors fixed or suppressed

## Current work: Audit P2.1 + P2.4 — Next: Item 1.6 ObjectBus

**Branch**: `fix/audit-P2-i18n-and-ci-hardening`

Completed 2026-05-08. Three items delivered. Item 5.7 was removed (completed in 1D, subsumed by LLMFactory pattern).

### Item 11.1 — Pipeline CI with GitHub Actions

**This is the P0 finding from the self-audit (finding 6.1). Highest leverage fix in the backlog.**

Create `.github/workflows/ci.yml` with two jobs:

**Job 1 — Unit tests + linting (runs on every push and PR)**

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: black --check .
      - run: ruff check .
      - run: pytest -m "not integration" --tb=short -q --cov=. --cov-report=term-missing
```

**Job 2 — Integration tests with Postgres (runs on PR to main only)**

```yaml
integration:
  runs-on: ubuntu-latest
  needs: test
  if: github.event_name == 'pull_request'
  services:
    postgres:
      image: pgvector/pgvector:pg16
      env:
        POSTGRES_DB: llull_test
        POSTGRES_USER: llull
        POSTGRES_PASSWORD: llull
      ports:
        - 5432:5432
      options: >-
        --health-cmd pg_isready
        --health-interval 10s
        --health-timeout 5s
        --health-retries 5
  env:
    DATABASE_URL: postgresql://llull:llull@localhost:5432/llull_test
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    - run: pip install -r requirements.txt -r requirements-dev.txt
    - run: alembic upgrade head
    - run: python data/generate_data.py
    - run: python models/train_demand_model.py
    - run: python knowledge/build_index.py
    - run: pytest -m integration --tb=short -q
```

**Important CI considerations:**

- The workflow must NOT require OpenAI or Anthropic API keys to pass. Unit tests mock LLM calls. Integration tests that need LLM calls should be marked `@pytest.mark.llm` and skipped in CI.
- Add `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` as optional GitHub Secrets for future LLM-based integration tests, but don't block CI on them.
- Add a badge to README.md: `![CI](https://github.com/gmateosAWS/decision-intelligence-agent/actions/workflows/ci.yml/badge.svg)`

### Item 11.3 — Dockerfile multi-stage

Create `Dockerfile` in project root. Multi-stage build:

```dockerfile
# Stage 1: builder
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: runtime
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

# Generate data and train model at build time (baked into image)
RUN python data/generate_data.py && \
    python models/train_demand_model.py

# Default: run the API
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Add to `docker-compose.yml`:

```yaml
api:
  build: .
  ports:
    - '8000:8000'
  environment:
    - DATABASE_URL=postgresql://llull:llull@postgres:5432/llull
  depends_on:
    postgres:
      condition: service_healthy
```

Add health check to postgres service:

```yaml
postgres:
  # ... existing config ...
  healthcheck:
    test: ['CMD-SHELL', 'pg_isready -U llull']
    interval: 5s
    timeout: 5s
    retries: 5
```

**Design note (Directive 3 — API-first):** The Dockerfile's default CMD runs the API server, not Streamlit. The API is the primary interface; Streamlit is a presentation layer. A separate compose profile or command override can run Streamlit:

```bash
docker compose run --rm api streamlit run streamlit_app.py --server.port=8501
```

Add `.dockerignore`:

```
.git
.env
__pycache__
*.pyc
.pytest_cache
logs/
venv/
.venv/
```

### Item 5.2 — Test suites v1 (golden eval foundation)

Create `tests/evaluation/test_agent_golden.py` — a structured test suite of 10-15 canonical queries with expected behaviors. This is NOT a test of exact LLM output text — it tests:

- **Routing correctness**: query → expected tool (optimization/simulation/knowledge)
- **Result shape**: tool output has expected keys and value types
- **Parameter propagation**: queries with explicit params pass them to the tool
- **Language detection**: Spanish queries get `language='es'` in state

Structure the tests as a parametrized fixture so they can be extended to golden eval (item 10.11) later:

```python
GOLDEN_QUERIES = [
    {
        "id": "opt-01",
        "query": "What price maximizes profit?",
        "expected_tool": "optimization",
        "expected_keys": ["optimal_price", "optimal_marketing", "optimal_profit"],
        "language": "en",
    },
    {
        "id": "opt-02",
        "query": "¿Qué precio maximiza el beneficio?",
        "expected_tool": "optimization",
        "expected_keys": ["optimal_price", "optimal_marketing", "optimal_profit"],
        "language": "es",
    },
    {
        "id": "sim-01",
        "query": "Simulate profit at price 25",
        "expected_tool": "simulation",
        "expected_keys": ["mean_profit", "std_profit", "n_simulations"],
        "language": "en",
    },
    {
        "id": "sim-02",
        "query": "Simula el beneficio con precio 25 y marketing 8000",
        "expected_tool": "simulation",
        "expected_keys": ["mean_profit", "std_profit"],
        "language": "es",
        "expected_params": {"price": 25},
    },
    {
        "id": "know-01",
        "query": "What is the demand model?",
        "expected_tool": "knowledge",
        "language": "en",
    },
    {
        "id": "know-02",
        "query": "¿Cómo afecta el marketing a la demanda?",
        "expected_tool": "knowledge",
        "language": "es",
    },
    # ... add 8-10 more covering edge cases:
    # - ambiguous queries that could be simulation or knowledge
    # - queries with boundary params (price at min/max)
    # - multi-turn follow-ups
    # - queries in other languages (fr, de) to test language detection
]

@pytest.mark.parametrize("case", GOLDEN_QUERIES, ids=[c["id"] for c in GOLDEN_QUERIES])
def test_golden_routing(case, mock_graph):
    """Verify that the planner routes each query to the expected tool."""
    ...

@pytest.mark.parametrize("case", [c for c in GOLDEN_QUERIES if "expected_keys" in c], ...)
def test_golden_result_shape(case, mock_graph):
    """Verify that tool output contains expected keys."""
    ...
```

The mock_graph fixture should:

- Use a real planner (with mocked LLM that returns deterministic ToolSelection)
- Use real tools (simulation, optimization, knowledge) against test data
- NOT use real LLM for synthesis/judge — mock those

**Design note (Directive 5 — no orphaned implementations):** This test suite is the foundation for item 10.11 (Golden eval CI gates from ADR-003). The parametrized structure with `GOLDEN_QUERIES` list is designed to evolve into three CI gates: routing gate, plan gate, and response-shape gate. When 10.11 lands, it extends this file — it doesn't replace it.

### Tests for CI and Docker

In `tests/ci/test_smoke.py`:

- `test_imports_succeed` — verify all main modules import without error (catches import-time IO bugs)
- `test_api_healthz` — FastAPI TestClient, verify `/healthz` returns 200
- `test_api_readyz` — verify `/readyz` returns dependency status

### After this block

Mark 11.1, 11.3, 5.2 as completed. Update audit report (finding 6.1 fixed).

**Next: Item 1.6 ObjectBus** — deferred until we have access to LlullGen codebase for reference (per ADR-003 Principle 1: read the code as reference). After that, open I2A formally.

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
