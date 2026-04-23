"""
tests/knowledge/test_retriever_pgvector.py
------------------------------------------
Integration test for pgvector-backed knowledge retrieval.

Requires a running PostgreSQL instance with the knowledge index built:
  python knowledge/build_index.py

Mark: @pytest.mark.integration
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_retrieve_relevant_docs():
    """
    retrieve_knowledge() returns a non-empty string containing at least
    one document when the pgvector index is populated.
    """
    from knowledge.retriever import retrieve_knowledge

    result = retrieve_knowledge("what is the optimal price?", k=2)

    assert isinstance(result, str)
    assert len(result) > 0, "Expected at least one document returned"
    # Documents are formatted as "[category] content"
    assert "[" in result, "Expected category prefix in result"
