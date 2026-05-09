"""
tests/knowledge/test_retriever_pgvector.py
------------------------------------------
Integration test for pgvector-backed knowledge retrieval.

Requires:
  - A running PostgreSQL instance with the knowledge index built:
      python knowledge/build_index.py
  - OPENAI_API_KEY set (embedding the query requires an API call)
  - Network connectivity to api.openai.com

Mark: @pytest.mark.integration @pytest.mark.llm
"""

from __future__ import annotations

import os

import pytest


def _openai_reachable() -> bool:
    """Return True if the OpenAI embedding API is reachable."""
    try:
        from langchain_openai import OpenAIEmbeddings

        OpenAIEmbeddings().embed_query("ping")
        return True
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.llm
def test_retrieve_relevant_docs():
    """
    retrieve_knowledge() returns a non-empty string containing at least
    one document when the pgvector index is populated.
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    if not _openai_reachable():
        pytest.skip("OpenAI API not reachable (SSL/network issue) — skipping")

    from knowledge.retriever import retrieve_knowledge

    result = retrieve_knowledge("what is the optimal price?", k=2)

    assert isinstance(result, str)
    assert len(result) > 0, "Expected at least one document returned"
    # Documents are formatted as "[category] content"
    assert "[" in result, "Expected category prefix in result"
