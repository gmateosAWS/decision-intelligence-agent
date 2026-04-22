# CLAUDE.md

## What is this project

Decision Intelligence Agent ("llull") — a spec-driven agent that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning. The LLM orchestrates; Python computes. This is a working prototype evolving toward production.

## Core architecture

```
spec/organizational_model.yaml  ← single source of truth for the domain
        │
        ├── system/system_graph.py     DAG built from spec's causal_relationships
        ├── system/system_model.py     topological evaluation engine (formula registry)
        ├── simulation/montecarlo.py   Monte Carlo with noise from spec
        ├── optimization/optimizer.py  grid search over decision variable bounds
        ├── knowledge/retriever.py     FAISS RAG (lazy-loaded)
        │
        └── agents/
             ├── state.py              AgentState TypedDict
             ├── planner.py            LLM → structured ToolSelection (Pydantic) + fallback policy
             ├── llm_factory.py        get_chat_model() + invoke_with_fallback() + LLMUnavailableError
             ├── tools.py              tool wrappers consuming spec defaults
             ├── workflow.py           LangGraph: planner → tool → synthesizer → judge → END
             └── judge.py             online quality gate + single-pass revision

memory/checkpointer.py   SqliteSaver + agent_sessions table
evaluation/observer.py    JSONL run logging (includes fallback events)
config/settings.py        thin adapter over spec (backward-compatible)
app.py                    REPL entry point (legacy, kept for dev use)
streamlit_app.py          Web UI entry point (NEW)
tests/agents/             unit tests
```

## Design principles (non-negotiable)

1. **Spec-driven**: all domain knowledge lives in `spec/organizational_model.yaml`. To change the domain, edit the YAML — no code changes.
2. **LLM orchestrates, never computes**: the LLM selects tools via structured output. All calculations are deterministic Python.
3. **Each tool is a pure function of (spec, params) → result**: tools read from the spec, receive params, return dicts. No side effects.
4. **The graph is the architecture**: LangGraph defines the flow. Adding a node = adding a capability. The judge is inside the graph, not outside.
5. **Provider-agnostic**: the system works with multiple LLM providers via `agents/llm_factory.py`. No hardcoded dependency on a single provider.

## Key files to understand first

- `spec/organizational_model.yaml` — read this first, everything derives from it
- `spec/spec_loader.py` — typed dataclasses that parse the YAML into `OrganizationalModelSpec`
- `agents/llm_factory.py` — LLM provider factory with fallback and retry logic
- `agents/workflow.py` — the LangGraph graph definition
- `agents/planner.py` — tool selection with structured output + formalized fallback policy
- `system/system_model.py` — `_NODE_FORMULAS` dict and topological evaluation
- `app.py` — legacy REPL entry point
- `streamlit_app.py` — web UI entry point (current task)

## Current tech stack

- Python 3.10+
- LangGraph >= 1.0 with `langgraph-checkpoint-sqlite`
- LangChain (openai, anthropic, community, core) >= 0.3
- LLM providers: OpenAI and Anthropic, configurable per node via env vars
- Fallback: automatic provider switch on failure, exponential backoff on rate limits (tenacity)
- `HISTORY_WINDOW` env var controls conversation history depth (default: 3)
- FAISS for vector search (faiss-cpu)
- scikit-learn for the demand model (RandomForest)
- networkx for the causal DAG
- SQLite for checkpointing and session persistence
- Streamlit for web UI (NEW)

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

## Build steps

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python data/generate_data.py
python models/train_demand_model.py
python knowledge/build_index.py

# Run web UI
streamlit run streamlit_app.py

# Run legacy REPL (for dev)
python app.py
```

## Testing policy

Every PR must include tests for the code it changes. Use `pytest`.

- **Unit tests**: mock LLM calls, don't hit real APIs.
- **Integration tests**: marked `@pytest.mark.integration`.
- **Test location**: `tests/` mirroring source structure.
- **Naming**: `test_<function_name>_<scenario>`.

```bash
pytest
pytest -m integration
pytest --tb=short -q
```

## Conventions

- Formatter: `black` (line-length 88)
- Linter: `ruff`
- Type hints on all function signatures
- Docstrings on all modules and public functions (numpy-style)
- No bare `except:` — always catch specific exceptions
- All config via `.env` or spec YAML — never hardcode values
- Every new feature must include unit tests

## What NOT to change without discussion

- The spec-driven principle
- The graph structure (planner → tool → synthesizer → judge)
- The `ToolSelection` Pydantic schema in `agents/planner.py`
- The `_NODE_FORMULAS` registry in `system/system_model.py`

## Git workflow

- Feature branches: `feature/<item-id>-<short-description>`
- Commit messages: `[<item-id>] <description>`
- PRs into main

## Completed items

- [x] **5.5** History window configurable via `HISTORY_WINDOW` env var
- [x] **5.6** Multi-provider LLM support (OpenAI + Anthropic) via `agents/llm_factory.py`
- [x] **12.4** Fallback policy between providers (automatic switch on failure)
- [x] **12.5** Rate limiting with exponential backoff (tenacity) + graceful degradation
- [x] **5.7** Formalized planner fallback policy (5 failure modes, `fallback_triggered` tracked)
- [x] **4.1** Simulation with arbitrary params verified and tested

## Current work: Item 6.6 — Streamlit UI

**Branch**: `feature/6.6-streamlit-ui`

### What to build

A Streamlit web app (`streamlit_app.py` in project root) that replaces the terminal REPL with a visual interface. The agent logic does NOT change — Streamlit is a presentation layer that invokes the same LangGraph graph.

### Pages / layout

**Main page — Chat**
- `st.chat_input` + `st.chat_message` for conversational interaction
- Each user message invokes the graph (`graph.invoke(...)`) same as `app.py` does
- Display the agent's response in a chat bubble
- Show which tool was used (optimization / simulation / knowledge) as a small badge or expander under each response
- Show latency per node (planner, tool, synthesizer, judge) in a collapsed expander — not by default, only if user clicks "details"
- Session management: sidebar buttons for "New session", "Resume session" from a selectbox of existing sessions
- Multi-turn works the same as in app.py — thread_id in config, SqliteSaver for persistence

**Sidebar**
- Session info: session ID (short), turn count, last active
- Active LLM config: which provider/model each node is using (read from env vars)
- Domain info: spec domain name, version, number of variables (read from spec_loader)
- A "DAG" button/expander that shows the causal graph

**DAG visualization**
- Read the causal graph from `system/system_graph.py` (it's a networkx DiGraph)
- Render it using `plotly` (networkx → plotly scatter plot with edges) or `streamlit-agraph` if simpler
- Color nodes by type: decision variables = blue, intermediate = gray, target = green
- Show on click or in expander, not always visible

**Results visualization (when tool output is available)**
- For **simulation** results: histogram of profit distribution (matplotlib or plotly), key stats (mean, std, p10, p90, downside risk) as metrics cards
- For **optimization** results: the optimal values as metric cards, and optionally a sensitivity chart if multi-param
- For **knowledge** results: just the text response, no special viz
- These render inside the chat flow, below the agent's text response, as `st.expander("Results details")`

### Technical approach

- Single file `streamlit_app.py` in project root (keep it simple for now, can refactor later)
- Import and reuse existing modules: `agents.workflow.build_graph`, `memory.checkpointer`, `spec.spec_loader.load_spec`, `system.system_graph`
- The graph invocation logic is essentially the same as in `app.py` — extract it, don't duplicate it
- Use `st.session_state` to persist the graph and session across Streamlit reruns
- Add `streamlit` and `plotly` to `requirements.txt`
- Do NOT modify any existing agent code — Streamlit wraps what's there

### Visual style

- Clean, professional, minimal. This is for showing to a CEO and a company president.
- Use Streamlit's native dark/light mode — don't fight it
- Title: "llull — Decision Intelligence Agent"
- Subtitle or sidebar note: "Prototype v1 · Inverence"
- No flashy animations. Clear typography. Let the agent's responses be the star.

### What NOT to do

- Don't rewrite the agent logic — call the existing graph
- Don't add authentication (that's I2B)
- Don't add multi-tenancy (that's I2B)
- Don't build a custom frontend framework — Streamlit is the right tool for this stage
- Don't make it a multi-page app yet — one page with sidebar is enough

### Tests

Streamlit UI testing is lightweight at this stage:
- Verify `streamlit_app.py` imports without errors: `python -c "import streamlit_app"`
- Verify the graph builds correctly in the Streamlit context
- Manual testing: run `streamlit run streamlit_app.py` and test the three query types

## Next in roadmap (paused)

**Paquete 1A — Base de persistencia**: PostgreSQL, pgvector, spec as data, runs in Postgres.

Full roadmap: see `llull_roadmap_v3.md` in project knowledge.
Full backlog: see `llull_inventario_v3.md` in project knowledge.
