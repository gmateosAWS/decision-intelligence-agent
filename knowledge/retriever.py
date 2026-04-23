"""
knowledge/retriever.py
----------------------
Retrieve relevant knowledge chunks for a query.

Backend selection:
  DATABASE_URL set  → pgvector cosine similarity search
  DATABASE_URL unset → FAISS local index (original behaviour)

Public API (unchanged):
  retrieve_knowledge(query: str, k: int = 3) -> str
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_INDEX_PATH = "knowledge_index"

# FAISS singleton (only used when DATABASE_URL is not set)
_faiss_vectorstore = None


def retrieve_knowledge(query: str, k: int = 3) -> str:
    """
    Return the k most relevant knowledge chunks for *query*.

    Args:
        query: Search query text.
        k:     Number of documents to retrieve (default: 3).

    Returns:
        Concatenated text of the retrieved documents.
    """
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        return _retrieve_pgvector(query, k)
    return _retrieve_faiss(query, k)


# ---------------------------------------------------------------------------
# pgvector backend
# ---------------------------------------------------------------------------


def _retrieve_pgvector(query: str, k: int) -> str:
    try:
        from langchain_openai import OpenAIEmbeddings
        from sqlalchemy import text

        from db.engine import get_session

        embedding_model = OpenAIEmbeddings()
        query_vector = embedding_model.embed_query(query)

        # pgvector cosine distance operator: <=>
        vector_literal = "[" + ",".join(str(v) for v in query_vector) + "]"

        with get_session() as session:
            rows = session.execute(
                text(
                    "SELECT content, category "
                    "FROM knowledge_documents "
                    "ORDER BY embedding <=> CAST(:vec AS vector) "
                    "LIMIT :k"
                ),
                {"vec": vector_literal, "k": k},
            ).fetchall()

        return "\n\n".join(
            f"[{row.category or 'general'}] {row.content}" for row in rows
        )
    except Exception as exc:
        logger.warning("pgvector retrieval failed (%s), falling back to FAISS", exc)
        return _retrieve_faiss(query, k)


# ---------------------------------------------------------------------------
# FAISS backend (original behaviour)
# ---------------------------------------------------------------------------


def _get_faiss_vectorstore():
    global _faiss_vectorstore  # noqa: PLW0603
    if _faiss_vectorstore is None:
        from langchain_community.vectorstores import FAISS
        from langchain_openai import OpenAIEmbeddings

        try:
            _faiss_vectorstore = FAISS.load_local(
                _INDEX_PATH,
                OpenAIEmbeddings(),
                allow_dangerous_deserialization=True,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Knowledge index not found at '{_INDEX_PATH}'. "
                "Run 'python knowledge/build_index.py' to create it."
            ) from exc
    return _faiss_vectorstore


def _retrieve_faiss(query: str, k: int) -> str:
    store = _get_faiss_vectorstore()
    docs = store.similarity_search(query, k=k)
    return "\n\n".join(
        f"[{doc.metadata.get('category', 'general')}] {doc.page_content}"
        for doc in docs
    )
