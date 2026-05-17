# Technical Debt Register

Items knowingly implemented as transitional that MUST be revisited when their
blocking dependency lands. Each entry documents what is incomplete, what the
final form should be, and the migration path.

---

## 5.11 → 5.13: MemoryService `propose_state_update` / `commit_state_update` stubs

**Status:** Open. Created 2026-05-14.
**Blocker:** Item 5.13 (user-correction mutations — explicit slot override flow).
**Affected:** `core/protocols/memory.py`, `memory/service.py`

### Current state (v1)

`propose_state_update` and `commit_state_update` are v1 placeholder methods in the
`MemoryService` Protocol. They return empty `StateProposal` and `StateCommitResult`
objects without performing any actual state mutation.

```python
# TODO(5.13/MemoryService): propose/commit are stubs — full flow deferred to item 5.13.
# When 5.13 lands: propose_state_update reads current frozen state + incoming LLM
# evidence and returns a StateProposal listing which slots would change.
# commit_state_update applies approved mutations via MemoryCoordinator and persists.
```

### Target state (when 5.13 lands)

`propose_state_update` will:
1. Read the current frozen `ActiveAnalyticalState` snapshot
2. Apply incoming user-correction evidence from `StateProposal.pending_mutations`
3. Return a `StateProposal` listing slots-to-change with before/after values

`commit_state_update` will:
1. Validate `StateCommitDecision.approved_mutations` against the proposal
2. Apply approved mutations via the single-writer `MemoryCoordinator`
3. Persist to DB and return a `StateCommitResult` with the new version

### Migration path

1. Item 5.13 lands with the user-correction mutation flow
2. Implement `propose_state_update` on `LocalMemoryService` with full mutation logic
3. Implement `commit_state_update` applying approved mutations through `MemoryCoordinator`
4. Extend `POST /v1/sessions/{id}/state/corrections` endpoint (already planned in 5.13)
5. Remove the TODO comment from both methods

### Risk if not migrated

- Users cannot explicitly correct misidentified intent or stale slot values
- State errors propagate silently across turns until the session resets

---

## 10.2 → 10.3: Variant selection is traffic-based, not eval-gated

**Status:** Open. Created 2026-05-17.
**Blocker:** Item 10.3 (automated prompt evaluation framework — win-rate comparisons).
**Affected:** `prompts/routing.py`, `prompts/registry.py`, `api/routers/prompts.py`

### Current state (v1)

Variant promotion from CANDIDATE → CHAMPION is a manual operator action via
`PUT /v1/prompts/variants/{stage}/{label}/promote`. Routing assigns traffic
deterministically based on `rollout_percentage`; it does not consider measured
quality or win-rate against the champion.

```python
# TODO(10.3/routing): promote_to_champion() is a manual op now.
# When 10.3 lands: gating logic reads from the eval store (judge scores per variant)
# and auto-promotes when win-rate exceeds configurable threshold over N turns.
```

### Target state (when 10.3 lands)

A background evaluator (or periodic job) reads `agent_runs.judge_score` grouped by
`planner_variant_label` / `synthesizer_variant_label` / `judge_variant_label`,
computes win-rate vs. the CHAMPION, and auto-promotes or auto-deprecates based on
configurable thresholds. Operators receive a notification rather than having to
manually initiate promotion.

### Migration path

1. Item 10.3 lands with the automated evaluation framework
2. Add `win_rate`, `n_evaluated`, `champion_win_rate` columns to `prompt_variants`
   (via migration 010 or as part of 10.3's own migration)
3. Implement `auto_promote_if_winning(stage, threshold, min_n)` in `prompts/routing.py`
4. Wire auto-promotion to a background task in `api/main.py` lifespan
5. Expose auto-promotion config via `PUT /v1/prompts/variants/{stage}/policy`

### Risk if not migrated

- Without eval-gating, operators must manually monitor `agent_runs` and decide when to
  promote — error-prone and not scalable as the number of prompt stages grows
- A regressing candidate may stay in traffic indefinitely if no one watches the metrics

---

## 5.9 → futuro: Near-match suggestion for ungrounded tokens

**Status:** Open. Created 2026-05-17.
**Blocker:** Future item (not yet in roadmap v4) — fuzzy/semantic matching for vocabulary.
**Affected:** `system/grounded_tokens.py`

### Current state (v1)

`validate_strict()` and `check_observational()` perform exact case-insensitive
matching against the token set.  When a token is ungrounded, the clarification
message lists all valid tokens alphabetically without ranking by similarity.

```python
# TODO(futuro/GroundedTokens): near-match suggestion not implemented.
# When the future item lands: before raising UngroundedTokenError, run a
# Levenshtein / embedding similarity search against vocab.tokens and include
# the top-3 closest matches in the error message.
# Example: "Did you mean 'bed_capacity'?" when user typed 'beds_capacity'.
```

### Target state (when the future item lands)

`validate_strict()` will call a `suggest_nearest(token, vocab, k=3)` helper
that returns the k closest tokens by edit distance or cosine similarity.
The clarification message will include "Did you mean X, Y, Z?" to guide the user.

### Migration path

1. Add `suggest_nearest(token, vocab, k)` to `system/grounded_tokens.py`
2. Update `UngroundedTokenError.__init__` to accept optional `suggestions: list[str]`
3. Update `planner_node` clarification message to include suggestions
4. Add tests for suggestion quality (edit distance cases + alias cases)
5. Remove this debt entry

### Risk if not migrated

- Users who make small typos (e.g., `staffing_rate` instead of `staffing_ratio`)
  receive an alphabetical list of all tokens with no guidance
- Degraded UX compared to modern LLM-powered assistants

---

## 5.10 → 1.6: ObjectId fields in ActiveAnalyticalState

**Status:** Open. Created 2026-05-13.
**Blocker:** Item 1.6 ObjectBus (pending access to LlullGen reference codebase per ADR-003).
**Affected:** `memory/state/active.py`, `memory/coordinator/coordinator.py`

### Current state (v1)

The fields `active_simulation_run`, `active_optimization_run`, and `active_scenarios`
in `ActiveAnalyticalState` are typed as `str | None` / `list[str]`. They store
`agent_runs.run_id` strings as references.

```python
# TODO(1.6/ObjectBus): change type from `str | None` to `ObjectId | None`
# when ObjectBus lands. The current str holds an agent_runs.run_id reference;
# ObjectId will hold a typed reference to an ObjectBus entry that includes
# the full RunEnvelope with reservations, lineage, and lifecycle hooks.
active_simulation_run: str | None = None
active_optimization_run: str | None = None
active_scenarios: list[str] = Field(default_factory=list)
```

### Target state (when 1.6 lands)

These fields will be typed as `ObjectId | None` / `list[ObjectId]`, where `ObjectId`
is a typed reference into the three-level ObjectBus. Each `ObjectId` resolves to a
full `RunEnvelope` including reservations, lineage, and lifecycle hooks.

### Migration path

1. ObjectBus lands (item 1.6) with backfill capability
2. Backfill script reads existing `agent_runs` and creates ObjectBus entries
3. Schema migration: change `analytical_state.active_*_run` JSONB schema from
   plain `str` to typed `ObjectId` representation
4. Type annotation change in `memory/state/active.py`
5. MemoryService Protocol (5.11) interface does **NOT** change — only the backing

### Risk if not migrated

- No lineage from active state to ObjectBus reservations (cost tracking gap)
- No type safety: a stale `run_id` pointing to a deleted run can sit in state silently
- When multi-agent (5.3.a/b) lands, `ObjectId`s enable peer agents to consume objects;
  bare `run_id` strings do not
