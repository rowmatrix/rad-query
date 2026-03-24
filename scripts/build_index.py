#!/usr/bin/env python3
"""
build_index.py — Ingest PDFs from data/raw/ and populate the ChromaDB vector store.

Usage:
    python scripts/build_index.py
    python scripts/build_index.py --data-dir /path/to/pdfs --chunk-size 512 --overlap 64
"""

import argparse
import logging
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rad_rag.chunker import chunk_pages
from rad_rag.embedder import add_chunks, get_collection
from rad_rag.ingest import ingest_directory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build rad-rag vector index")
    parser.add_argument(
        "--data-dir",
        default="data/raw",
        help="Directory containing radiation test report PDFs (default: data/raw)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Target chunk size in characters (default: 512)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=64,
        help="Chunk overlap in characters (default: 64)",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        logger.error("Data directory not found: %s", data_dir)
        sys.exit(1)

    logger.info("Ingesting PDFs from %s", data_dir)
    pages = ingest_directory(data_dir)
    if not pages:
        logger.error("No pages extracted — check that data/raw/ contains PDFs.")
        sys.exit(1)

    logger.info("Chunking %d pages (size=%d, overlap=%d)", len(pages), args.chunk_size, args.overlap)
    chunks = chunk_pages(pages, chunk_size=args.chunk_size, chunk_overlap=args.overlap)
    logger.info("Created %d chunks", len(chunks))

    logger.info("Embedding and upserting into ChromaDB…")
    collection = get_collection()
    add_chunks(chunks, collection=collection)

    logger.info("Index build complete. Total chunks stored: %d", collection.count())


if __name__ == "__main__":
    main()
