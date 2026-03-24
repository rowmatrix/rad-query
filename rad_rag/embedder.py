"""
embedder.py — Embed text chunks and manage a ChromaDB vector store.

Uses sentence-transformers (local, free) by default.
Swap EMBED_MODEL to an OpenAI model name and set OPENAI_API_KEY to
use the OpenAI embeddings API instead.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — override via environment variables
# ---------------------------------------------------------------------------
EMBED_MODEL = os.getenv("RAD_RAG_EMBED_MODEL", "all-MiniLM-L6-v2")
CHROMA_PERSIST_DIR = os.getenv("RAD_RAG_CHROMA_DIR", "data/processed/chroma")
COLLECTION_NAME = os.getenv("RAD_RAG_COLLECTION", "rad_reports")


def _get_embedding_function():
    """Return a ChromaDB-compatible embedding function.

    Tries sentence-transformers first; falls back to OpenAI if the env var
    OPENAI_API_KEY is set and sentence-transformers is unavailable.
    """
    try:
        from chromadb.utils.embedding_functions import (  # noqa: PLC0415
            SentenceTransformerEmbeddingFunction,
        )

        logger.info("Using sentence-transformers model: %s", EMBED_MODEL)
        return SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

    except ImportError:
        pass

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        from chromadb.utils.embedding_functions import (  # noqa: PLC0415
            OpenAIEmbeddingFunction,
        )

        logger.info("Using OpenAI embeddings model: %s", EMBED_MODEL)
        return OpenAIEmbeddingFunction(api_key=api_key, model_name=EMBED_MODEL)

    raise ImportError(
        "Install sentence-transformers or set OPENAI_API_KEY for embeddings."
    )


def get_collection(persist_dir: str | None = None, collection_name: str | None = None):
    """Open (or create) a persistent ChromaDB collection.

    Args:
        persist_dir: Directory for ChromaDB persistence. Defaults to CHROMA_PERSIST_DIR.
        collection_name: Collection name. Defaults to COLLECTION_NAME.

    Returns:
        chromadb.Collection
    """
    import chromadb  # noqa: PLC0415

    persist_dir = persist_dir or CHROMA_PERSIST_DIR
    collection_name = collection_name or COLLECTION_NAME

    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=persist_dir)
    ef = _get_embedding_function()
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def add_chunks(
    chunks: Sequence[dict],
    collection=None,
    batch_size: int = 100,
) -> None:
    """Embed and upsert a list of chunk dicts into ChromaDB.

    Chunk IDs are derived from source + page + chunk_index so re-running
    this function is idempotent (upsert semantics).

    Args:
        chunks: Output of chunker.chunk_pages().
        collection: An open ChromaDB collection. Created with default settings if None.
        batch_size: Number of chunks per upsert call.
    """
    if collection is None:
        collection = get_collection()

    ids, documents, metadatas = [], [], []
    for chunk in chunks:
        uid = f"{chunk['source']}::p{chunk['page']}::c{chunk['chunk_index']}"
        ids.append(uid)
        documents.append(chunk["text"])
        metadatas.append(
            {"source": chunk["source"], "page": chunk["page"]}
        )

    # Upsert in batches to avoid memory spikes with large corpora
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i : i + batch_size],
            documents=documents[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
        )
        logger.info(
            "Upserted batch %d/%d", min(i + batch_size, len(ids)), len(ids)
        )

    logger.info("Total chunks in collection: %d", collection.count())


def query(
    question: str,
    n_results: int = 5,
    collection=None,
) -> list[dict]:
    """Retrieve the top-k most relevant chunks for a query.

    Args:
        question: Natural language query (e.g. "TID tolerance of LM741 op-amp").
        n_results: Number of chunks to return.
        collection: Open ChromaDB collection. Created with defaults if None.

    Returns:
        List of result dicts sorted by relevance:
            {"text": str, "source": str, "page": int, "distance": float}
    """
    if collection is None:
        collection = get_collection()

    results = collection.query(
        query_texts=[question],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    for doc, meta, dist in zip(docs, metas, dists):
        hits.append(
            {
                "text": doc,
                "source": meta.get("source", "unknown"),
                "page": meta.get("page", 0),
                "distance": round(dist, 4),
            }
        )

    return hits
