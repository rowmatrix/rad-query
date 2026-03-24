"""
retriever.py — Retrieve relevant chunks and synthesize a cited answer.

The answer generator is intentionally thin: it formats retrieved context
into a prompt and calls whichever LLM backend is configured.

Supported backends (set RAD_RAG_LLM_BACKEND env var):
  - "openai"   : OpenAI Chat Completions (requires OPENAI_API_KEY)
  - "anthropic": Anthropic Claude (requires ANTHROPIC_API_KEY)
  - "local"    : Returns raw retrieved context — useful for testing without
                 an API key.
"""

from __future__ import annotations

import logging
import os
from typing import Sequence

from rad_rag.embedder import query as vector_query

logger = logging.getLogger(__name__)

LLM_BACKEND = os.getenv("RAD_RAG_LLM_BACKEND", "local")
OPENAI_MODEL = os.getenv("RAD_RAG_OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_MODEL = os.getenv("RAD_RAG_ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a radiation effects and EEE components specialist.
Answer the user's question using ONLY the provided context from radiation test reports.
For every claim, cite the source document and page number in brackets, e.g. [report.pdf, p.12].
If the context is insufficient, say so clearly — do not speculate beyond the data."""

CONTEXT_TEMPLATE = """--- Context ---
{context}
--- End Context ---

Question: {question}
Answer (with citations):"""


def _format_context(hits: Sequence[dict]) -> str:
    parts = []
    for i, hit in enumerate(hits, start=1):
        parts.append(
            f"[{i}] Source: {hit['source']}, Page: {hit['page']}\n{hit['text']}"
        )
    return "\n\n".join(parts)


def _call_openai(prompt: str) -> str:
    from openai import OpenAI  # noqa: PLC0415

    client = OpenAI()
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def _call_anthropic(prompt: str) -> str:
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _call_local(hits: Sequence[dict]) -> str:
    """No-LLM fallback: return formatted retrieved context."""
    lines = ["[local mode — no LLM synthesis]\n"]
    for i, hit in enumerate(hits, start=1):
        lines.append(
            f"Result {i} | {hit['source']} p.{hit['page']} "
            f"(dist={hit['distance']})\n{hit['text']}\n"
        )
    return "\n".join(lines)


def answer(
    question: str,
    n_results: int = 5,
    collection=None,
) -> dict:
    """Retrieve relevant chunks and generate a cited answer.

    Args:
        question: Natural language query.
        n_results: Number of chunks to retrieve from the vector store.
        collection: Open ChromaDB collection (created with defaults if None).

    Returns:
        {
            "question": str,
            "answer": str,
            "sources": [{"source": str, "page": int, "distance": float}, ...]
        }
    """
    hits = vector_query(question, n_results=n_results, collection=collection)

    if not hits:
        return {
            "question": question,
            "answer": "No relevant documents found in the corpus.",
            "sources": [],
        }

    backend = LLM_BACKEND.lower()

    if backend == "local":
        answer_text = _call_local(hits)
    else:
        context = _format_context(hits)
        prompt = CONTEXT_TEMPLATE.format(context=context, question=question)

        if backend == "openai":
            answer_text = _call_openai(prompt)
        elif backend == "anthropic":
            answer_text = _call_anthropic(prompt)
        else:
            raise ValueError(
                f"Unknown LLM backend: {backend!r}. "
                "Set RAD_RAG_LLM_BACKEND to 'openai', 'anthropic', or 'local'."
            )

    sources = [
        {"source": h["source"], "page": h["page"], "distance": h["distance"]}
        for h in hits
    ]

    return {"question": question, "answer": answer_text, "sources": sources}
