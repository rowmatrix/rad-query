"""
test_rad_rag.py — pytest unit tests for rad-rag core modules.

Tests are designed to run without any PDF files, external APIs, or
a running ChromaDB instance — everything is mocked or uses in-memory fixtures.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# chunker tests
# ---------------------------------------------------------------------------
from rad_rag.chunker import chunk_pages


class TestChunker:
    SAMPLE_PAGES = [
        {"source": "report_a.pdf", "page": 1, "text": "A" * 600},
        {"source": "report_a.pdf", "page": 2, "text": "B" * 300},
        {"source": "report_b.pdf", "page": 1, "text": "C" * 1000},
        {"source": "empty.pdf",    "page": 1, "text": ""},
    ]

    def test_basic_chunking_produces_chunks(self):
        chunks = chunk_pages(self.SAMPLE_PAGES, chunk_size=256, chunk_overlap=32)
        assert len(chunks) > 0

    def test_empty_page_skipped(self):
        chunks = chunk_pages(self.SAMPLE_PAGES, chunk_size=256, chunk_overlap=32)
        sources = [c["source"] for c in chunks]
        assert "empty.pdf" not in sources

    def test_chunk_length_bounded(self):
        chunks = chunk_pages(self.SAMPLE_PAGES, chunk_size=256, chunk_overlap=32)
        for chunk in chunks:
            # After stripping, a chunk should not exceed chunk_size
            assert len(chunk["text"]) <= 256

    def test_metadata_preserved(self):
        pages = [{"source": "test.pdf", "page": 3, "text": "X" * 300}]
        chunks = chunk_pages(pages, chunk_size=100, chunk_overlap=10)
        for chunk in chunks:
            assert chunk["source"] == "test.pdf"
            assert chunk["page"] == 3
            assert "chunk_index" in chunk

    def test_chunk_index_increments(self):
        pages = [{"source": "test.pdf", "page": 1, "text": "Y" * 500}]
        chunks = chunk_pages(pages, chunk_size=100, chunk_overlap=10)
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(indices)))

    def test_overlap_invalid_raises(self):
        with pytest.raises(ValueError, match="chunk_overlap"):
            chunk_pages(self.SAMPLE_PAGES, chunk_size=100, chunk_overlap=100)

    def test_single_short_page_yields_one_chunk(self):
        pages = [{"source": "short.pdf", "page": 1, "text": "Hello world"}]
        chunks = chunk_pages(pages, chunk_size=512, chunk_overlap=64)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "Hello world"

    def test_empty_corpus(self):
        assert chunk_pages([], chunk_size=512, chunk_overlap=64) == []

    def test_large_page_splits_into_multiple_chunks(self):
        pages = [{"source": "big.pdf", "page": 1, "text": "Z" * 2000}]
        chunks = chunk_pages(pages, chunk_size=512, chunk_overlap=64)
        assert len(chunks) > 1

    def test_all_chunk_texts_non_empty(self):
        chunks = chunk_pages(self.SAMPLE_PAGES, chunk_size=256, chunk_overlap=32)
        for chunk in chunks:
            assert chunk["text"].strip() != ""


# ---------------------------------------------------------------------------
# ingest tests (no real PDFs — test error paths)
# ---------------------------------------------------------------------------
from rad_rag.ingest import ingest_directory, iter_pages


class TestIngest:
    def test_iter_pages_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            list(iter_pages(tmp_path / "nonexistent.pdf"))

    def test_ingest_directory_empty_dir_returns_empty(self, tmp_path):
        result = ingest_directory(tmp_path)
        assert result == []

    def test_ingest_directory_nonpdf_files_ignored(self, tmp_path):
        (tmp_path / "notes.txt").write_text("some text")
        result = ingest_directory(tmp_path)
        assert result == []

    def test_ingest_directory_returns_list(self, tmp_path):
        result = ingest_directory(tmp_path)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# embedder tests (mock ChromaDB)
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock, patch

from rad_rag.embedder import add_chunks, query


class TestEmbedder:
    def _make_collection(self, existing_count: int = 0):
        col = MagicMock()
        col.count.return_value = existing_count
        col.query.return_value = {
            "documents": [["chunk text A", "chunk text B"]],
            "metadatas": [
                [{"source": "a.pdf", "page": 1}, {"source": "b.pdf", "page": 3}]
            ],
            "distances": [[0.12, 0.34]],
        }
        return col

    def test_add_chunks_calls_upsert(self):
        col = self._make_collection()
        chunks = [
            {"source": "x.pdf", "page": 1, "chunk_index": 0, "text": "some text"},
            {"source": "x.pdf", "page": 1, "chunk_index": 1, "text": "more text"},
        ]
        add_chunks(chunks, collection=col)
        col.upsert.assert_called()

    def test_add_chunks_empty_list(self):
        col = self._make_collection()
        add_chunks([], collection=col)
        col.upsert.assert_not_called()

    def test_query_returns_list_of_dicts(self):
        col = self._make_collection()
        results = query("TID tolerance of LM741", n_results=2, collection=col)
        assert isinstance(results, list)
        assert len(results) == 2

    def test_query_result_keys(self):
        col = self._make_collection()
        results = query("test question", n_results=2, collection=col)
        for r in results:
            assert "text" in r
            assert "source" in r
            assert "page" in r
            assert "distance" in r

    def test_query_distance_rounded(self):
        col = self._make_collection()
        results = query("test", n_results=2, collection=col)
        for r in results:
            assert isinstance(r["distance"], float)


# ---------------------------------------------------------------------------
# retriever tests (mock vector_query)
# ---------------------------------------------------------------------------
from rad_rag.retriever import answer


class TestRetriever:
    MOCK_HITS = [
        {"text": "The LM741 survived 50 krad TID.", "source": "nepp_lm741.pdf", "page": 4, "distance": 0.10},
        {"text": "Degradation observed above 30 krad.", "source": "nepp_lm741.pdf", "page": 5, "distance": 0.22},
    ]

    def test_answer_no_hits_returns_no_docs_message(self):
        with patch("rad_rag.retriever.vector_query", return_value=[]):
            result = answer("random question", n_results=5)
        assert "No relevant documents" in result["answer"]
        assert result["sources"] == []

    def test_answer_local_backend_returns_dict(self):
        with patch("rad_rag.retriever.vector_query", return_value=self.MOCK_HITS), \
             patch("rad_rag.retriever.LLM_BACKEND", "local"):
            result = answer("What is the TID tolerance of LM741?")
        assert "question" in result
        assert "answer" in result
        assert "sources" in result

    def test_answer_sources_match_hits(self):
        with patch("rad_rag.retriever.vector_query", return_value=self.MOCK_HITS), \
             patch("rad_rag.retriever.LLM_BACKEND", "local"):
            result = answer("TID LM741")
        assert len(result["sources"]) == len(self.MOCK_HITS)
        assert result["sources"][0]["source"] == "nepp_lm741.pdf"

    def test_answer_invalid_backend_raises(self):
        with patch("rad_rag.retriever.vector_query", return_value=self.MOCK_HITS), \
             patch("rad_rag.retriever.LLM_BACKEND", "bogus_backend"):
            with pytest.raises(ValueError, match="Unknown LLM backend"):
                answer("test")

    def test_answer_question_echoed(self):
        with patch("rad_rag.retriever.vector_query", return_value=self.MOCK_HITS), \
             patch("rad_rag.retriever.LLM_BACKEND", "local"):
            q = "SEE susceptibility of GaAs FETs"
            result = answer(q)
        assert result["question"] == q
