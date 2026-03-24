"""
chunker.py — Split page text into overlapping chunks for embedding.

Chunks preserve metadata so every piece can be traced back to its
source document and page number — essential for citation in the UI.
"""

from __future__ import annotations

import re
from typing import Sequence


def _split_sentences(text: str) -> list[str]:
    """Rough sentence splitter that keeps abbreviations intact."""
    # Split on sentence-ending punctuation followed by whitespace + capital
    return re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())


def chunk_pages(
    pages: Sequence[dict],
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[dict]:
    """Split a list of page dicts into overlapping text chunks.

    Args:
        pages: Output of ingest.ingest_directory() or ingest.iter_pages().
        chunk_size: Target character length of each chunk.
        chunk_overlap: Number of characters shared between consecutive chunks.

    Returns:
        List of chunk dicts:
            {
                "source": str,       # original PDF filename
                "page": int,         # 1-indexed page of chunk start
                "chunk_index": int,  # 0-indexed position within the page
                "text": str,         # chunk text
            }
    """
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be less than chunk_size")

    chunks: list[dict] = []

    for page in pages:
        text = page["text"].strip()
        if not text:
            continue

        source = page["source"]
        page_num = page["page"]

        start = 0
        chunk_index = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    {
                        "source": source,
                        "page": page_num,
                        "chunk_index": chunk_index,
                        "text": chunk_text,
                    }
                )
            start += chunk_size - chunk_overlap
            chunk_index += 1

    return chunks
