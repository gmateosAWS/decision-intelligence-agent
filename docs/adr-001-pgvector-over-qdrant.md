# ADR-001 — pgvector over Qdrant for vector search

**Status**: Accepted  
**Date**: 2026-04-23  
**Decider**: Gustavo Mateos

## Context

The agent needs a vector store for semantic search over knowledge documents. Two candidates were evaluated: **pgvector** (Postgres extension) and **Qdrant** (dedicated vector database).

The project already uses PostgreSQL 16 as its primary persistence layer (item 1.1). The knowledge index is built once offline (`knowledge/build_index.py`) and queried at inference time (`knowledge/retriever.py`). Approximate nearest-neighbour accuracy requirements are moderate (top-k recall for a few hundred to a few thousand documents).

## Decision

Use **pgvector** as the primary vector store, with FAISS as the offline fallback when `DATABASE_URL` is not set.

## Reasons

1. **Operational simplicity**: pgvector runs inside the existing Postgres container. Adding Qdrant would mean a second stateful service to provision, monitor, back up, and keep in sync.

2. **Consistency**: all persistent state (sessions, runs, specs, knowledge) lives in one database. Transactions, migrations, and backups are unified.

3. **Sufficient performance**: at the document volumes in scope for this project (hundreds to low thousands of chunks), an `ivfflat` cosine index over a `vector(1536)` column meets latency requirements. Qdrant's HNSW index is faster at millions of vectors — a threshold we are not near.

4. **Fallback symmetry**: the FAISS fallback mirrors the pgvector path. Both return the same ranked results for the same query. A dedicated Qdrant instance would require a separate fallback strategy.

5. **Tooling reuse**: SQLAlchemy, Alembic, and the existing `get_session()` context manager are already in place. The pgvector query is a single `ORDER BY embedding <=> CAST(:vec AS vector) LIMIT :k` raw SQL statement — no new client library needed.

## Trade-offs accepted

- **Scale ceiling**: pgvector with `ivfflat` starts to degrade (recall and latency) above ~1M vectors. If the knowledge base grows beyond that, migration to Qdrant (or `hnsw` index in pgvector ≥ 0.5) would be needed. This is not a concern for the current scope.
- **No built-in payload filtering**: pgvector relies on standard SQL `WHERE` clauses. Qdrant has richer native filter syntax. We use the `category` column for filtering — this is adequate for current needs.
- **Embedding updates**: re-indexing requires re-running `knowledge/build_index.py`. Qdrant offers more granular upsert APIs. Acceptable for a batch-built index.

## Migration path if needed

If the project reaches a scale where pgvector is insufficient:
1. Add `VECTOR_BACKEND=qdrant` to `.env` and the Qdrant SDK to `requirements.txt`.
2. Implement a `QdrantRetriever` behind the same interface as `retriever.py`.
3. Run a one-time migration script to push existing embeddings from Postgres to Qdrant.
4. Keep the `DATABASE_URL` fallback chain unchanged for environments without Qdrant.
