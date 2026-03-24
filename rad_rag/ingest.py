"""
ingest.py — Load and parse radiation test report PDFs.

Supports pdfplumber (default) with a pymupdf fallback.
Each document is returned as a list of page dicts:
    {"source": str, "page": int, "text": str}
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


def iter_pages(pdf_path: str | Path) -> Iterator[dict]:
    """Yield one dict per page from a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Yields:
        {"source": filename, "page": 1-indexed page number, "text": extracted text}

    Raises:
        ImportError: If neither pdfplumber nor pymupdf is installed.
        FileNotFoundError: If the PDF does not exist.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    source = pdf_path.name

    # Try pdfplumber first; fall back to pymupdf (fitz)
    try:
        import pdfplumber  # noqa: PLC0415

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                yield {"source": source, "page": page_num, "text": text}
        return

    except ImportError:
        logger.debug("pdfplumber not available, trying pymupdf")

    try:
        import fitz  # pymupdf  # noqa: PLC0415

        doc = fitz.open(str(pdf_path))
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            yield {"source": source, "page": page_num, "text": text}
        doc.close()
        return

    except ImportError as exc:
        raise ImportError(
            "Install at least one PDF backend: pdfplumber or pymupdf"
        ) from exc


def ingest_directory(
    directory: str | Path,
    glob: str = "**/*.pdf",
) -> list[dict]:
    """Ingest all PDFs in a directory tree.

    Args:
        directory: Root directory to search.
        glob: Glob pattern relative to directory. Default finds PDFs recursively.

    Returns:
        Flat list of page dicts from all discovered PDFs.
    """
    directory = Path(directory)
    pages: list[dict] = []
    pdf_files = sorted(directory.glob(glob))

    if not pdf_files:
        logger.warning("No PDF files found in %s", directory)
        return pages

    for pdf_path in pdf_files:
        logger.info("Ingesting %s", pdf_path.name)
        try:
            pages.extend(iter_pages(pdf_path))
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to ingest %s: %s", pdf_path.name, exc)

    logger.info("Ingested %d pages from %d files", len(pages), len(pdf_files))
    return pages
