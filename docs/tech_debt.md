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
