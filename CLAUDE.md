# CLAUDE.md

## What is this project

Decision Intelligence Agent ("llull") — a spec-driven agent that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning. The LLM orchestrates; Python computes. Evolving from prototype to product.

## Core architecture

```
spec/organizational_model.yaml  ← single source of truth (will move to DB in 1.5)
        │
        ├── system/system_graph.py     DAG built from spec's causal_relationships
        ├── system/system_model.py     topological evaluation engine (formula registry)
        ├── simulation/montecarlo.py   Monte Carlo with noise from spec
        ├── optimization/optimizer.py  grid search over decision variable bounds
        ├── knowledge/retriever.py     pgvector search (FAISS fallback)
        │
        ├── agents/
        │    ├── state.py              AgentState TypedDict
        │    ├── planner.py            LLM → structured ToolSelection + fallback policy
        │    ├── llm_factory.py        get_chat_model() + invoke_with_fallback()
        │    ├── tools.py              tool wrappers consuming spec defaults
        │    ├── workflow.py           LangGraph: planner → tool → synthesizer → judge → END
        │    └── judge.py             online quality gate + single-pass revision
        │
        ├── db/
        │    ├── engine.py             SQLAlchemy engine, get_session()
        │    ├── models.py             AgentSession, AgentRun, KnowledgeDocument
        │    └── migrations/           Alembic (001_initial_schema)
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
        └── config/settings.py        thin adapter over spec

app.py                    REPL (legacy)
streamlit_app.py          Web UI
docker-compose.yml        PostgreSQL 16 + pgvector
alembic.ini               migration config
tests/                    unit + integration tests
docs/                     inventario + roadmap
```

## Design principles (non-negotiable)

1. **Spec-driven**: domain knowledge in spec YAML only (moving to DB in 1.5)
2. **LLM orchestrates, never computes**: structured output selects tools
3. **Tools are pure functions**: (spec, params) → result
4. **The graph is the architecture**: LangGraph defines the flow
5. **Provider-agnostic**: multi-provider via `llm_factory.py`
6. **Product-grade**: proper migrations, error handling, tests, Docker
7. **Dual-backend**: Postgres primary, SQLite/FAISS fallback when `DATABASE_URL` not set

## Database

PostgreSQL 16 with pgvector, managed via Docker Compose and Alembic.

```env
DATABASE_URL=postgresql://llull:llull@localhost:5432/llull
```

Three tables: `agent_sessions`, `agent_runs`, `knowledge_documents` (with vector(1536)).

```bash
docker compose up -d                    # start Postgres
alembic upgrade head                    # run migrations
```

Without `DATABASE_URL`, the system falls back to SQLite + FAISS automatically.

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
docker compose up -d                    # Postgres
alembic upgrade head                    # migrations
python data/generate_data.py
python models/train_demand_model.py
python knowledge/build_index.py         # inserts into pgvector (or FAISS)
streamlit run streamlit_app.py          # web UI
```

## Testing

```bash
pytest                                  # unit tests
pytest -m integration                   # DB tests (needs Docker)
```

## Conventions

`black` (88), `ruff`, type hints, numpy docstrings, no bare except, config via .env/YAML.

## What NOT to change without discussion

Spec-driven principle, graph structure, `ToolSelection` schema, `_NODE_FORMULAS` registry.

## Git workflow

`feature/<item-id>-<desc>`, commits `[<item-id>] <desc>`, PRs into main.

## Completed items

### Paquete 1D ✅
- [x] 5.5 History window configurable
- [x] 5.6 Multi-provider LLM (OpenAI + Anthropic)
- [x] 12.4 Fallback between providers
- [x] 12.5 Rate limiting + graceful degradation
- [x] 5.7 Planner fallback policy
- [x] 4.1 Simulation params verified

### Paquete 1E ✅
- [x] 6.6 Streamlit UI

### Paquete 1A (partial) ✅
- [x] 1.1 PostgreSQL migration (PostgresSaver, SQLAlchemy, Alembic, dual-backend)
- [x] 1.2 pgvector (knowledge_documents, cosine search, FAISS fallback)
- [x] 8.1 Runs in Postgres (agent_runs table, dual-write, metrics from Postgres)

## Next: Feature B — Spec as data (item 1.5)

**Branch**: `feature/1.5-spec-as-data`

The spec YAML currently lives as a static file (`spec/organizational_model.yaml`). This feature makes it a database object: stored in Postgres, versioned, editable programmatically, with the YAML file as initial seed.

### Why this matters

Without this, the spec is a file that someone edits manually and restarts the service. With it:
- Multiple specs can coexist (one per domain/client)
- Specs have version history (who changed what, when)
- The DAG builder (I3) can edit specs through the UI
- The conversational generator (I2A) can create specs programmatically
- Each run is tied to the exact spec version used (traceability)

### Database changes

New Alembic migration `002_spec_tables.py`:

```sql
CREATE TABLE specs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_name     TEXT NOT NULL,
    version         TEXT NOT NULL,           -- semver: 1.2.0
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft / active / archived
    yaml_content    TEXT NOT NULL,           -- full YAML as text
    parsed_content  JSONB NOT NULL,          -- parsed YAML as JSON for querying
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      TEXT,
    description     TEXT,
    UNIQUE(domain_name, version)
);

CREATE TABLE spec_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    spec_id         UUID REFERENCES specs(id),
    version         TEXT NOT NULL,
    yaml_content    TEXT NOT NULL,
    parsed_content  JSONB NOT NULL,
    change_summary  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      TEXT
);
CREATE INDEX idx_spec_versions_spec ON spec_versions(spec_id);
```

Add `spec_id` and `spec_version` columns to `agent_runs`:
```sql
ALTER TABLE agent_runs ADD COLUMN spec_id UUID REFERENCES specs(id);
ALTER TABLE agent_runs ADD COLUMN spec_version TEXT;
```

### New files

```
db/models.py          — add Spec and SpecVersion models
db/migrations/versions/002_spec_tables.py — migration
spec/spec_repository.py — CRUD for specs:
    create_spec(yaml_content, domain_name, version) -> Spec
    get_active_spec(domain_name) -> Spec
    get_spec_by_version(domain_name, version) -> Spec
    list_specs(domain_name?) -> List[Spec]
    update_spec(spec_id, yaml_content, new_version, change_summary) -> Spec
    activate_spec(spec_id) -> Spec
    seed_from_yaml(yaml_path) -> Spec   # imports the current YAML file as first version
```

### Files to modify

**spec/spec_loader.py**:
- Add `load_spec_from_db(domain_name) -> OrganizationalModelSpec` that reads from Postgres
- Keep `load_spec(path)` as fallback for when `DATABASE_URL` is not set
- The singleton `get_spec()` tries DB first, YAML file second

**evaluation/observer.py**:
- When writing a run to `agent_runs`, include `spec_id` and `spec_version`

**app.py / streamlit_app.py**:
- On startup, if Postgres is available and the `specs` table is empty, auto-seed from the YAML file
- Display the active spec version in the UI sidebar

### Behavior

- The YAML file (`spec/organizational_model.yaml`) becomes the seed, not the runtime source
- On first run with Postgres: the system imports the YAML into the `specs` table as version `1.0.0` with status `active`
- After that, the system reads from the DB. The YAML file is kept for reference and for SQLite fallback mode
- Editing the spec creates a new version in `spec_versions` and a new row in `specs` with status `draft`
- A spec must be explicitly activated (`status = 'active'`) to be used by the agent
- Only one spec per domain can be `active` at a time

### Tests

In `tests/spec/test_spec_repository.py` (integration, needs Postgres):
- `test_create_spec_from_yaml`
- `test_get_active_spec`
- `test_update_creates_new_version`
- `test_only_one_active_per_domain`
- `test_seed_from_yaml_file`
- `test_run_records_spec_version`

In `tests/spec/test_spec_loader_db.py`:
- `test_load_spec_from_db_returns_typed_spec`
- `test_fallback_to_yaml_when_no_db`

### What NOT to do

- Don't change the spec YAML format — the schema stays the same, it just lives in a DB now
- Don't change `OrganizationalModelSpec` dataclass — it's the typed interface, unchanged
- Don't remove the YAML file — it's the seed and the fallback
- Don't build a UI for spec editing yet — that's the DAG builder in I3

### Post-completion

After merge:
- Update CLAUDE.md (mark 1.5 done, update architecture)
- Update docs/llull_roadmap_v3.md (mark 1.5 done in Paquete 1A)
- Write docs/adr-001-pgvector-over-qdrant.md (item 1.3)
- Commit all doc updates together: `[docs] Update after Paquete 1A completion`

Then proceed to **Paquete 1B** (FastAPI Agent Service) or **Paquete 1C** (CI pipeline).

Full roadmap: `docs/llull_roadmap_v3.md`
Full backlog: `docs/llull_inventario_v3.md`
