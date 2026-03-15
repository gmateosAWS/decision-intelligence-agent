"""
knowledge/retriever.py  ← CORREGIDO
─────────────────────────────────────
Cambios:
  1. Imports actualizados: langchain_openai, langchain_community
  2. Carga lazy del vectorstore (no a nivel de módulo).
     El import ya no falla si knowledge_index no existe todavía.
  3. Función retrieve_knowledge() con manejo de error explícito.
"""

from __future__ import annotations

from typing import Optional

from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

# ── Lazy-loaded singleton ──────────────────────────────────────────────────────
# El vectorstore se carga la primera vez que se invoca retrieve_knowledge().
# Esto permite importar el módulo sin que falle si el índice aún no existe.
_vectorstore: Optional[FAISS] = None
_INDEX_PATH = "knowledge_index"


def _get_vectorstore() -> FAISS:
    global _vectorstore
    if _vectorstore is None:
        try:
            _vectorstore = FAISS.load_local(
                _INDEX_PATH,
                OpenAIEmbeddings(),
                allow_dangerous_deserialization=True,
            )
        except Exception as e:
            raise RuntimeError(
                f"Knowledge index not found at '{_INDEX_PATH}'. "
                "Run 'python knowledge/build_index.py' to create it."
            ) from e
    return _vectorstore


def retrieve_knowledge(query: str, k: int = 3) -> str:
    """
    Busca los k documentos más relevantes para la query dada.

    Args:
        query: Pregunta o texto de búsqueda.
        k:     Número de documentos a recuperar (default: 3).

    Returns:
        Texto concatenado de los documentos recuperados.
    """
    store = _get_vectorstore()
    docs = store.similarity_search(query, k=k)
    return "\n\n".join(
        f"[{doc.metadata.get('category', 'general')}] {doc.page_content}"
        for doc in docs
    )
