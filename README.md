# Decision Intelligence Agent

A **Decision Intelligence prototype** that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning -- orchestrated by an LLM agent.

The system combines spec-driven development and deterministic analytical components (causal model, ML, Monte Carlo simulation, optimization) with LLM-based orchestration using LangGraph and basic RAG for system knowledge. The LLM **does not compute decisions**: it orchestrates specialized tools that do.

---

## Concept

Traditional analytics pipelines stop at descriptive insight:

```
data -> dashboards -> human decision
```

Decision Intelligence systems reason about decisions directly:

```
data -> causal system model -> simulation -> optimization -> recommendation
```

In this prototype:

- the **organizational spec** declares the domain model as explicit, editable configuration
- the **causal graph (DAG)** represents how business variables relate and propagate
- **ML models** estimate unknown relationships from historical data
- **Monte Carlo simulation** evaluates decisions under uncertainty
- **optimization** searches for the best decision across the decision space
- an **LLM agent** orchestrates the process and synthesizes results in natural language

---

## Design Principles

### 1 - Spec-driven architecture

The entire organizational model is declared in `spec/organizational_model.yaml`. This single file is the **source of truth** for all system components: the causal graph, the simulation engine, the optimizer, and the agent all read from it.

To adapt the system to a new domain or change a business parameter: **edit the spec**. No code changes required.

```yaml
# spec/organizational_model.yaml (excerpt)
variables:
  decisions:
    - name: price
      bounds: { min: 10.0, max: 50.0 }
  targets:
    - name: profit
      optimize: maximize

causal_relationships:
  - from: [price, marketing_spend]
    to: demand
    type: ml_estimated
```

### 2 - LLM orchestrates, tools compute

The LLM never computes a business decision. It selects the appropriate analytical tool (via structured output), passes the query to it, and synthesizes the tool result into a natural language response.

```
User query -> Planner (LLM, tool selection) -> Tool (deterministic computation) -> Synthesizer (LLM, natural language) -> Answer
```

This separation makes the system **auditable, testable, and governable**: every computation is deterministic and inspectable, independent of the LLM.

### 3 - Graph-driven propagation

The causal DAG is not decorative. The `SystemModel.evaluate()` method propagates values through the graph in **topological order**: each node is computed only after all its causal predecessors have been resolved. Adding a new causal variable requires only registering its formula and adding an edge to the graph -- no changes to the evaluation logic.

---

## Architecture

```mermaid
flowchart TD
    User[User]
    Agent["LangGraph Agent\nplanner - tool - synthesizer"]
    Spec["Organizational Spec\nspec/organizational_model.yaml"]
    SimTool[Simulation Tool]
    OptTool[Optimization Tool]
    KnowTool[RAG Knowledge Tool]
    SimEngine[Monte Carlo Engine]
    VectorDB["Vector Database\n20 documents - 6 categories"]
    SystemModel["System Model\ncausal DAG traversal"]
    MLModel["RandomForest\ndemand estimator"]
    Data[Historical Sales Data]

    User --> Agent
    Spec --> SystemModel
    Spec --> SimEngine
    Spec --> OptTool

    Agent --> SimTool
    Agent --> OptTool
    Agent --> KnowTool

    SimTool --> SimEngine
    OptTool --> SimEngine
    KnowTool --> VectorDB

    SimEngine --> SystemModel
    SystemModel --> MLModel
    MLModel --> Data
```

---

## Improvements Summary

Four incremental improvements were implemented and fully tested on top of the baseline prototype:

| # | Improvement | What it solves |
|---|---|---|
| 1 | Spec-driven architecture | Domain model in YAML; business parameters configurable without touching code |
| 2 | Observability layer | JSONL logging + LangSmith integration + HTML dashboard; every run is auditable |
| 3 | Multi-turn conversational memory | SQLite checkpointing; persistent sessions with conversation history injection into LLM context |
| 4 | Dynamic generic parameters | `params` dict in `ToolSelection`; planner prompt generated from spec; fully domain-agnostic parameter extraction |

---

## Agent Execution Flow

```mermaid
flowchart LR
    User[User Query]
    Planner["Planner\n(LLM - structured output)"]
    Opt[Optimization Tool]
    Sim[Simulation Tool]
    Know[Knowledge RAG]
    Synth["Synthesizer\n(LLM - natural language)"]
    Answer[Answer]

    User --> Planner
    Planner -->|optimization| Opt
    Planner -->|simulation| Sim
    Planner -->|knowledge| Know
    Opt --> Synth
    Sim --> Synth
    Know --> Synth
    Synth --> Answer
```

The planner uses **structured output** (Pydantic schema) to guarantee the tool selection is always a valid, typed value -- no fragile string parsing.

The synthesizer receives the raw tool result and produces a business-oriented response: it explains what the numbers mean, not just what they are.

---

## Core Components

### Organizational Spec (`spec/`)

`organizational_model.yaml` declares:

- **Decision variables**: controllable inputs (price, marketing spend), with bounds and defaults
- **Intermediate variables**: derived or ML-estimated (demand, revenue, cost)
- **Target variables**: business outcomes to optimize (profit)
- **Causal relationships**: the edges of the DAG, with type (ml_estimated / formula)
- **Business parameters**: unit cost and other domain constants
- **Simulation configuration**: Monte Carlo runs, noise model
- **Optimization configuration**: target, method, fixed variables

`spec_loader.py` parses the YAML into typed Python dataclasses and exposes a singleton `get_spec()` used across all components.

---

### Data Layer (`data/`)

Synthetic sales data is generated to simulate historical observations.

Variables: `price`, `marketing`, `demand`

Demand follows the relationship:

```
demand = 120 - 1.6 x price + 0.0009 x marketing + noise(sigma=5)
```

- `price` is sampled from `uniform(10, 50)` -- matching the spec decision variable range
- `marketing` is sampled from `uniform(1000, 20000)` -- reflecting real business scale in EUR
- The coefficient `0.0009` is calibrated so that marketing at its default value (EUR 10,000) contributes ~9 demand units, keeping the marketing effect meaningful but secondary to price

2,000 samples are generated with `numpy` random seed 42 for reproducibility.

---

### Predictive Model (`models/`)

A **RandomForest regressor** estimates the demand function from historical data:

```
(price, marketing_spend) -> demand
```

Training includes an 80/20 train/test split stratified by price quantiles. Verified performance on held-out test set:

| Metric | Value |
|---|---|
| R2 | 0.9257 -- explains 92.6% of demand variability |
| MAE | 4.58 units |
| RMSE | 5.66 units |

Feature importances confirm the expected causal structure:

| Feature | Importance |
|---|---|
| price | 90.87% |
| marketing_spend | 9.13% |

The trained model is persisted to `models/demand_model.pkl`.

---

### System Model (`system/`)

The business is represented as a **causal Directed Acyclic Graph (DAG)**:

```mermaid
flowchart LR
    price([price])
    marketing([marketing_spend])
    demand([demand])
    revenue([revenue])
    cost([cost])
    profit([profit])

    price --> demand
    marketing --> demand
    price --> revenue
    demand --> revenue
    demand --> cost
    revenue --> profit
    cost --> profit

    classDef decision fill:#4A90D9,stroke:#2C5F8A,color:#fff
    classDef variable fill:#6EAF7C,stroke:#3D7A4A,color:#fff
    classDef target   fill:#E8A838,stroke:#B07820,color:#fff

    class price,marketing decision
    class demand,revenue,cost variable
    class profit target
```

`SystemModel.evaluate()` performs a **topological traversal** of the DAG:

1. Initialises decision nodes with input values
2. For each node in topological order: computes via ML model (demand) or registered formula (revenue, cost, profit)
3. Returns a complete dict of all variable values

The graph structure is loaded from the spec -- adding a new causal variable requires only a new formula entry and a new edge in `system/system_graph.py`.

---

### Simulation Engine (`simulation/`)

`monte_carlo()` evaluates a `(price, marketing)` decision under uncertainty by running **N independent simulations** (default: 500, configurable in the spec), each with a Gaussian perturbation on the demand estimate.

Output statistics:

| Field | Description |
|---|---|
| `expected_profit` | Mean profit across all runs |
| `profit_std` | Standard deviation -- spread of outcomes |
| `profit_p10` | 10th percentile -- pessimistic scenario |
| `profit_p90` | 90th percentile -- optimistic scenario |
| `expected_demand` | Mean demand across all runs |
| `demand_std` | Demand variability |
| `downside_risk_pct` | % of runs where profit < 0 |
| `n_runs` | Number of simulations executed |

---

### Optimization (`optimization/`)

`optimize_price()` performs a **grid search** over the price range (bounds from spec), evaluating each candidate price via Monte Carlo simulation and selecting the one that maximises `expected_profit`.

Marketing spend is held fixed at the value declared in `spec.optimization.fixed_variables`.

Validated scenario results:

| Scenario | Price | Demand | Expected Profit | Downside Risk |
|---|---|---|---|---|
| Default | EUR 25 | ~88 units | ~EUR 1,328 | 0% |
| Optimized | ~EUR 48.64 | ~55 units | ~EUR 2,139 | 0% |

The optimum reflects the trade-off between lower volume and higher margin per unit: even though demand drops from 88 to 55 units (-38%), the margin increase from EUR 15 to EUR 38.64 per unit (+158%) more than compensates.

---

### Knowledge Layer (`knowledge/`)

A FAISS vector database indexes **20 domain documents** across 6 categories:

| Category | Content |
|---|---|
| `business_model` | Business overview, decision variables, constraints |
| `causal_model` | Demand function, revenue, cost, profit relationships |
| `ml_model` | RandomForest description, uncertainty interpretation |
| `simulation` | Monte Carlo methodology, output interpretation, risk metrics |
| `optimization` | Grid search approach, optimal price interpretation |
| `interpretation` | Price elasticity, marketing ROI, decision guidance |

The vector store is loaded **lazily** (on first query, not at import time). If the index does not exist, an explicit error is raised with instructions.

---

### Agent Layer (`agents/`)

The agent is implemented as a **3-node LangGraph graph**:

**`planner_node`** -- Selects the appropriate tool using `gpt-4o-mini` with structured output. The system prompt is built dynamically from the spec, listing all decision variable names and ranges. Output is a typed `ToolSelection(tool, reasoning, params)` object -- no string parsing.

**`tool_node`** -- Executes the selected tool. Wrapped in `try/except`: errors are captured and propagated to the state rather than crashing the graph.

**`synthesizer_node`** -- Receives the raw tool output and the original query, and produces a business-oriented natural language answer: what do the numbers mean, what should the decision-maker do.

**`AgentState`** TypedDict fields:

| Field | Set by | Description |
|---|---|---|
| `query` | Input | User's original question |
| `action` | Planner | Selected tool name |
| `reasoning` | Planner | LLM's reasoning for tool selection |
| `params` | Planner | Generic dict of extracted variable values -- e.g. `{"price": 30.0}` |
| `raw_result` | Tool | Raw output from the analytical tool |
| `answer` | Synthesizer | Final natural language response |
| `run_id` | Input | Observability correlation ID |
| `history` | Synthesizer | Accumulated (query, answer) turn pairs -- merged via `operator.add` |

---

## Repository Structure

```
decision-intelligence-agent/
+-- spec/
|   +-- organizational_model.yaml   # Single source of truth for the domain model
|   +-- spec_loader.py              # Typed YAML parser, singleton get_spec()
|   +-- __init__.py
+-- data/
|   +-- generate_data.py            # Synthetic sales dataset (2,000 samples)
|   +-- checkpoints.db              # SQLite: LangGraph state + agent_sessions
+-- models/
|   +-- train_demand_model.py       # RF training, evaluation metrics, model export
+-- system/
|   +-- system_graph.py             # Causal DAG -- edges loaded from spec
|   +-- system_model.py             # Graph-traversal evaluation engine
+-- simulation/
|   +-- montecarlo.py               # Monte Carlo engine (N runs, noise model)
|   +-- scenario_runner.py          # Scenario wrapper
+-- optimization/
|   +-- optimizer.py                # Grid search over price range
+-- knowledge/
|   +-- build_index.py              # FAISS index builder (20 docs, 6 categories)
|   +-- retriever.py                # Lazy-loaded similarity search
+-- agents/
|   +-- state.py                    # AgentState TypedDict
|   +-- tools.py                    # Tool wrappers (spec-driven defaults + generic params)
|   +-- planner.py                  # LLM planner: dynamic prompt + structured output
|   +-- workflow.py                 # LangGraph: planner -> tool -> synthesizer
+-- memory/
|   +-- __init__.py                 # Public exports
|   +-- checkpointer.py             # SqliteSaver singleton + agent_sessions table
|   +-- session_manager.py          # CRUD and session listing (CLI helpers)
+-- evaluation/
|   +-- __init__.py
|   +-- observer.py                 # AgentObserver: run lifecycle, JSONL logging, confidence
|   +-- metrics.py                  # load_runs / compute_metrics / print_report
|   +-- dashboard.py                # HTML dashboard generator + CLI entry point
+-- config/
|   +-- settings.py                 # Thin adapter over spec (backward-compatible)
+-- logs/                           # Created at runtime
|   +-- agent_runs.jsonl            # Append-only run log (one JSON per line)
|   +-- agent.log                   # Verbose debug log
|   +-- dashboard.html              # Generated by evaluation/dashboard.py
+-- app.py                          # REPL entry point with observability
+-- .env.example                    # Environment variable template
+-- requirements.txt
+-- README.md
```

---

## Setup

**1. Create and activate a virtual environment**

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows
# Git Bash on Windows:
source venv/Scripts/activate
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure API key**

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_api_key
```

Get your key from: https://platform.openai.com/api-keys

---

## Build Artefacts

These steps generate the files the agent needs at runtime. Run them once after setup (and again if you modify the spec or data):

**Generate synthetic dataset**

```bash
python data/generate_data.py
```

**Train the demand model**

```bash
python models/train_demand_model.py
```

Output: `models/demand_model.pkl` -- also prints MAE, RMSE and R2 on the test set.

**Build the knowledge index**

```bash
python knowledge/build_index.py
```

Output: `knowledge_index/` directory -- FAISS index of 20 domain documents.

> The organizational spec (`spec/organizational_model.yaml`) is loaded automatically at runtime. No additional build step required.

---

## Run the Agent

```bash
python app.py
```

**Example session:**

```
+--------------------------------------------------------------+
|  Decision Intelligence Agent  *  v3 (memory)                |
+--------------------------------------------------------------+
|  Ask business questions about pricing and marketing.         |
|  Commands:                                                   |
|    session new | list | resume <id|#> | info | delete <id>   |
|    dashboard * exit                                          |
+--------------------------------------------------------------+

* New session: 3f8a2c1d-...

Ask a business question: What price maximises profit?

  The optimization analysis recommends a price of approximately EUR 48.64,
  yielding an expected profit of ~EUR 2,139 with 55 units of demand.
  Downside risk is 0%. While demand drops from ~88 units at the default
  EUR 25 price, the higher margin per unit (EUR 38.64 vs EUR 15.00) more
  than compensates. Profit at the 10th percentile is still ~EUR 1,865,
  confirming a stable outcome.

Ask a business question: What about simulating at price 30?

  At EUR 30.00 the simulation shows expected profit of ~EUR 1,559 (demand
  ~78 units, std ~8 units). Compared to the optimum of EUR 48.64, this
  represents a EUR 580 reduction in expected profit but higher volume.
  Downside risk remains 0%.

Ask a business question: exit
Goodbye.
```

---

## Observability and Evaluation Layer (`evaluation/`)

Every agent run is captured, measured and visualisable.

### Architecture

```
app.py
  +-- AgentObserver.start_run(query)          opens a RunRecord
       +-- planner_node  -> obs.record_planner()
       +-- tool_node     -> obs.record_tool()
       +-- synthesizer_node -> obs.record_synthesizer()
  +-- AgentObserver.end_run()                 writes to JSONL

logs/
  +-- agent_runs.jsonl   one JSON record per run (append-only)
  +-- agent.log          verbose debug log
  +-- dashboard.html     generated on demand
```

### Components

| Module | Responsibility |
|---|---|
| `evaluation/observer.py` | `AgentObserver` -- wraps each run, records timing, derives confidence score, writes JSONL |
| `evaluation/metrics.py` | `load_runs` / `compute_metrics` -- aggregates stats from JSONL; `print_report` -- CLI summary |
| `evaluation/dashboard.py` | `generate_html_dashboard` -- self-contained HTML with Chart.js; CLI entry point |

### RunRecord fields

| Field | Source | Description |
|---|---|---|
| `run_id` | observer | Unique ID per query (12-char hex) |
| `session_id` | observer | Groups runs within one session |
| `timestamp` | observer | ISO-8601 UTC |
| `query` | input | Raw user question |
| `action` | planner | `optimization` / `simulation` / `knowledge` |
| `reasoning` | planner | LLM's explanation of tool choice |
| `planner_latency_ms` | planner node | Time from entry to structured output |
| `tool_latency_ms` | tool node | Time to execute the analytical tool |
| `synthesizer_latency_ms` | synthesizer node | Time for natural-language response |
| `total_latency_ms` | observer | End-to-end wall time |
| `confidence_score` | observer | Derived: `1 - downside_risk_pct/100` for Monte Carlo, `1.0` for optimization, `0.9` for RAG |
| `raw_result_keys` | tool node | Dict keys returned by the tool |
| `success` | observer | `false` if any node raised an exception |
| `error` | observer | Exception message if `success=false` |
| `answer_length` | synthesizer | Character count of the final answer |

### LangSmith integration

Set these variables in `.env` to enable automatic tracing of every LangGraph invocation:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=ls__your_key
LANGCHAIN_PROJECT=decision-intelligence-agent
```

`AgentObserver.langsmith_config()` injects `run_name`, `tags` and `metadata` so each run appears named and tagged in the LangSmith UI. No code changes required -- tracing activates automatically when the env var is present.

### View metrics

**CLI report** (prints to terminal):

```bash
python -m evaluation.dashboard
```

**HTML dashboard** (opens in browser):

```bash
python -m evaluation.dashboard --out logs/dashboard.html
# then open logs/dashboard.html in your browser
```

**Inline (from the REPL)**:

```
Ask a business question: dashboard
```

The dashboard includes:

- KPI cards: total runs, success rate, avg latency, avg confidence
- Tool distribution doughnut chart
- Latency breakdown bar chart (planner / tool / synthesizer)
- Recent runs table with per-run confidence bars
- Error log (if any failures occurred)

---

## Conversational Memory

### Goal

Give the agent **persistent multi-turn memory** and a **session management** system that allows:

- Maintaining conversation context across multiple turns within the same session
- Resuming previous sessions after restarting the process
- Listing, inspecting and deleting sessions from the CLI

### Architecture

```
app.py (REPL)
|
+-- memory/
|   +-- __init__.py          Public exports
|   +-- checkpointer.py      SqliteSaver singleton + agent_sessions table
|   +-- session_manager.py   CRUD and session listing (CLI helpers)
|
+-- agents/
|   +-- state.py             adds `history` field (Annotated + operator.add)
|   +-- planner.py           injects last 3 turns into LLM prompt
|   +-- workflow.py          build_graph(checkpointer=...) with persistence
|
+-- data/
    +-- checkpoints.db       SQLite: LangGraph tables + agent_sessions
```

### `memory/checkpointer.py`

| Responsibility | Detail |
|---|---|
| `get_checkpointer()` | Singleton `SqliteSaver` pointing to `data/checkpoints.db` |
| `register_turn()` | Upsert in `agent_sessions`: updates `last_active` and `turn_count` |
| `_ensure_sessions_table()` | Creates the `agent_sessions` table if it does not exist |

Schema of `agent_sessions`:

```sql
session_id  TEXT PRIMARY KEY
title       TEXT    -- first 60 chars of the first query
created_at  TEXT    -- ISO 8601 UTC
last_active TEXT    -- ISO 8601 UTC, updated on each turn
turn_count  INTEGER
```

### `memory/session_manager.py`

```python
SessionManager.list_sessions()        # -> List[dict]
SessionManager.get_session(sid)       # -> dict | None
SessionManager.delete_session(sid)    # -> bool
SessionManager.print_sessions()       # numbered table in stdout
SessionManager.session_info(sid)      # details of a session
```

### `agents/state.py`

```python
history: Annotated[List[Dict[str, str]], operator.add]
```

`operator.add` tells LangGraph that `history` returns from each node are **concatenated** rather than replaced, accumulating all turns.

### `agents/planner.py`

```python
_HISTORY_WINDOW = 3   # previous turns injected into the prompt

messages = [system_prompt]
for turn in history[-_HISTORY_WINDOW:]:
    messages += [{"role": "user",      "content": turn["query"]},
                 {"role": "assistant", "content": turn["answer"]}]
messages.append({"role": "user", "content": current_query})
```

This enables natural cross-turn references:

```
User: "What is the optimal price?"
User: "And if price is 28?"  <- planner understands the context
```

### `agents/workflow.py`

- `build_graph(checkpointer=None)` accepts an optional `SqliteSaver`.
- `synthesizer_node` returns `{"answer": ..., "history": [new_turn]}`.
  LangGraph applies `operator.add` and the new turn is persisted under the session `thread_id`.

### Turn flow

```
User writes query
     |
     v
app.py: start_run() + build config {thread_id, observer}
     |
     v
graph.invoke()
  +-- planner_node    -> injects history[-3:] into LLM prompt
  +-- tool_node       -> executes optimization / simulation / knowledge
  +-- synthesizer_node -> generates answer + returns {history: [new_turn]}
     |
     v
SqliteSaver persists complete state (accumulated history)
     |
     v
register_turn() -> upsert in agent_sessions
     |
     v
observer.end_run() -> writes logs/agent_runs.jsonl
```

### Session management commands

```
session new              new session (new thread_id)
session list             list saved sessions
session resume <id>      resume by full session_id
session resume <#>       resume by index from 'session list'
session info             details of active session
session delete <id>      remove session from registry
dashboard                CLI metrics + dashboard.html
exit                     quit
```

The `thread_id` is passed in the LangGraph config:

```python
cfg["configurable"]["thread_id"] = session_id
result = graph.invoke({"query": raw, "run_id": run_id}, config=cfg)
```

### Example multi-turn session

```
$ python app.py

  * New session: 3f8a2c1d-...

Ask a business question: What price maximises profit?
  The optimization analysis suggests ~EUR 48.64, expected profit ~EUR 2,139 ...

Ask a business question: What if price is 20?
  At EUR 20.00 the simulation shows expected profit of ~EUR 951, demand ~95 units ...

Ask a business question: session list
  #   Session ID          Turns  Last active           Title
  1   3f8a2c1d-...        2      2025-07-16 10:22:01   What price maximises pro

Ask a business question: session info
  Session ID   : 3f8a2c1d-...
  Title        : What price maximises profit?
  Created      : 2025-07-16T10:21:44+00:00
  Last active  : 2025-07-16T10:22:01+00:00
  Turn count   : 2

# --- After restart ---

Ask a business question: session resume 1
  Session resumed: 3f8a2c1d-... (2 turns)

Ask a business question: And what about price 28?
  Building on previous context: at EUR 28.00 expected profit is ~EUR 1,232 ...
```

---

## Dynamic Parameter Extraction

### Goal

Make parameter extraction from user queries fully **domain-agnostic**. Before this, the `ToolSelection` Pydantic schema had fixed fields `price: float | None` and `marketing: float | None`, coupling the planner to the retail domain. A generic `params` dict removes that coupling.

### The problem with hardcoded fields

```python
# BEFORE (coupled to retail domain)
class ToolSelection(BaseModel):
    tool: Literal["optimization", "simulation", "knowledge"]
    reasoning: str
    price: float | None = None        # hardcoded field
    marketing: float | None = None    # hardcoded field
```

Changing the domain to energy (`generation_capacity`, `bid_price`) or healthcare (`staff_level`, `bed_count`) would require modifying the Pydantic schema and tool code -- exactly what the spec-driven architecture was meant to avoid.

### The generic solution

```python
# AFTER (domain-agnostic)
class DecisionParam(BaseModel):
    variable: str    # variable name from spec
    value: float     # value extracted from the user query

class ToolSelection(BaseModel):
    tool: Literal["optimization", "simulation", "knowledge"]
    reasoning: str
    params: List[DecisionParam] = []   # e.g. [{"variable": "price", "value": 30.0}]
```

### Dynamic system prompt from spec

The system prompt is built at runtime by reading the spec's decision variable names:

```python
def _build_system_prompt() -> str:
    spec = get_spec()
    vars_desc = "\n".join(
        f"  - {v.name}: range [{v.min}-{v.max}] {v.unit}, default {v.default}"
        for v in spec.decision_variables
    )
    return _SYSTEM_PROMPT_TEMPLATE.format(
        domain=spec.domain,
        vars_description=vars_desc,
    )
```

The template instructs the LLM to extract values into `params` using the exact variable names from the spec:

```
If the user mentions a specific value for any decision variable
(e.g. "at 30", "if price is 28", "simulate with budget 5000"),
extract those values into the `params` list using the exact variable
names from the spec. Leave `params` empty to use spec defaults.
```

### `simulation_tool` with generic params

```python
def simulation_tool(state: Dict[str, Any]) -> Dict[str, Any]:
    spec = get_spec()
    extracted = {p["variable"]: p["value"] for p in (state.get("params") or [])}

    # For each decision variable: extracted value > spec default
    kwargs = {
        v.name: extracted.get(v.name, v.default)
        for v in spec.decision_variables
    }

    var_names = [v.name for v in spec.decision_variables]
    result = run_scenario(
        system_model,
        kwargs[var_names[0]],   # first variable -> price
        kwargs[var_names[1]],   # second variable -> marketing_spend
    )
    return result
```

### Domain change without code changes

| Task | Before | After |
|---|---|---|
| Change decision variables | Edit YAML + edit ToolSelection + edit simulation_tool | Edit YAML only |
| Add a new decision variable | Edit YAML + add field to schema | Edit YAML only |
| Change from retail to energy | Requires changes in planner, state, tools | Edit YAML only |

### Validated tests

| Query | Params extracted | Result |
|---|---|---|
| `Simulate profit at price 30` | `{"price": 30.0}` | demand ~78 u, profit ~EUR 1,559 |
| `What would happen if we set price at 20?` | `{"price": 20.0}` | demand ~95 u, profit ~EUR 951 |
| `Run the simulation with default parameters` | `{}` | default EUR 25 -> demand ~88 u, profit ~EUR 1,328 |
| `And what if marketing increases by 5000?` (multi-turn) | `{"marketing_spend": 15000}` | demand ~92 u, profit ~EUR 1,358; ROI +EUR 38/EUR 5,000 |

The last test demonstrates the interaction between multi-turn memory (context resolution: "increases by 5000" resolved as 10,000 + 5,000 = 15,000) and generic parameter extraction (mapped correctly to the spec variable name `marketing_spend`).

---

## Adapting to a New Domain

The spec-driven architecture makes domain adaptation straightforward. To model a different business scenario:

1. Edit `spec/organizational_model.yaml` -- define your variables, causal relationships, bounds and parameters
2. Register formula functions for new derived nodes in `system/system_model.py` (`_NODE_FORMULAS`)
3. Retrain the ML model if the input/output variables change (`models/train_demand_model.py`)
4. Rebuild the knowledge index with domain-specific documents (`knowledge/build_index.py`)

No changes to the agent, planner, workflow, or simulation engine are required.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Spec-driven YAML over hardcoded parameters | Domain model is explicit, auditable, and changeable without touching code |
| LLM selects tools via structured output (Pydantic) | Eliminates fragile string parsing; tool selection is always a valid typed value |
| Generic `params: Dict[str, float]` in `ToolSelection` | Variable extraction from queries is fully domain-agnostic; switching domains requires only editing the spec YAML |
| LLM orchestrates, does not compute | Computations are deterministic and testable; LLM adds language understanding and synthesis |
| Dynamic system prompt generated from spec | Planner describes the correct variable names to the LLM without manual updates when the domain changes |
| DAG-driven topological evaluation | Adding new causal variables requires only formula registration, not refactoring `evaluate()` |
| Lazy FAISS loading | Import never fails due to missing index; failure is explicit and informative |
| Synthesizer node separate from tool node | Raw analytical output and natural language presentation are decoupled concerns |
| Monte Carlo over point estimates | Decisions are evaluated under uncertainty; risk (`downside_risk_pct`) is a first-class output |
| JSONL observability log | Every run is persisted as a structured record; metrics and dashboards are derived offline without affecting runtime |
| Confidence score derived from tool output | A single 0-1 score makes run quality comparable across tool types without requiring LLM self-evaluation |
| Observer injected via LangGraph configurable | Observability is decoupled from business logic; nodes remain testable in isolation without an observer |
| SQLite for session persistence | Zero-infrastructure persistence; portable, inspectable, and sufficient for prototype scale |
