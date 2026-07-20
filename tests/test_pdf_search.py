#!/usr/bin/env python3
"""Tests for pdf_search — chunk-grain passage search (task #7 M4).

Two documents are loaded into a temp cache, then searched. On the deterministic `test`
backend a query equal to a chunk's text embeds to that chunk's exact vector (distance 0),
so the top hit is pinned and the shaping logic — fusion, best_per_source vs all_chunks, the
within-document scope — is asserted exactly. No pypdf, no model, no real semantics needed.

    python3 tests/test_pdf_search.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["SECOND_BRAIN_EMBEDDER"] = "test"

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from db import connect  # noqa: E402
import embedder  # noqa: E402
import pdf_cache  # noqa: E402
import pdf_search  # noqa: E402

A = "vault/resources/a.pdf"
B = "vault/resources/b.pdf"
DOC_A = [(0, 1, "alpha overview intro"), (1, 2, "beta zephyr details"), (2, 3, "gamma closing summary")]
DOC_B = [(0, 1, "delta separate document"), (1, 2, "epsilon zephyr appendix")]


def _payload(source, chunks):
    return {
        "source_file": source, "type": "test",
        "chunks": [{"chunk_id": cid, "page": pg, "char_start": 0, "char_end": len(t),
                    "text": t, "vector": embedder.embed(t, task="document")}
                   for cid, pg, t in chunks],
    }


class PassageSearchTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "brain.db"
        db = connect(db_path)
        pdf_cache.ensure_tables(db)
        pdf_cache.load_all(db, [_payload(A, DOC_A), _payload(B, DOC_B)])
        db.commit()  # sqlite3 needs it; apsw autocommits each statement
        db.close()
        self._orig = pdf_search.DB_PATH
        pdf_search.DB_PATH = db_path

    def tearDown(self):
        pdf_search.DB_PATH = self._orig
        self._tmp.cleanup()

    def test_best_per_source_is_the_default_and_one_hit_per_document(self):
        hits = pdf_search.search_pdf("beta zephyr details", k=5)  # exact text of A/chunk 1
        self.assertEqual(hits[0].source_file, A)
        self.assertEqual((hits[0].chunk_id, hits[0].page), (1, 2))
        self.assertEqual(hits[0].snippet, "beta zephyr details")
        # best_per_source: each document appears at most once
        self.assertEqual(len(hits), len({h.source_file for h in hits}))
        self.assertEqual({h.source_file for h in hits}, {A, B})

    def test_all_chunks_does_not_collapse_a_document(self):
        hits = pdf_search.search_pdf("beta zephyr details", k=5, result_mode="all_chunks")
        self.assertEqual(hits[0].source_file, A)
        self.assertEqual(len(hits), 5)                       # all five chunks come back
        self.assertEqual(sum(h.source_file == A for h in hits), 3)  # A not collapsed

    def test_within_document_restricts_to_one_pdf(self):
        hits = pdf_search.search_pdf("zephyr", k=5, result_mode="all_chunks", source_file=B)
        self.assertTrue(hits, "expected passages within document B")
        self.assertTrue(all(h.source_file == B for h in hits))
        self.assertIn(1, [h.chunk_id for h in hits])        # B/chunk 1 has 'zephyr'

    def test_keyword_leg_finds_a_shared_term_across_documents(self):
        hits = pdf_search.search_pdf("zephyr", k=5, result_mode="all_chunks")
        self.assertEqual({h.source_file for h in hits}, {A, B})  # 'zephyr' is in both docs

    def test_k_limits_the_result_count(self):
        hits = pdf_search.search_pdf("zephyr", k=1, result_mode="all_chunks")
        self.assertEqual(len(hits), 1)


class EmptyCacheTest(unittest.TestCase):
    def test_no_pdf_tables_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "brain.db"
            connect(db_path).close()                        # a db with no pdf tables at all
            orig, pdf_search.DB_PATH = pdf_search.DB_PATH, db_path
            try:
                self.assertEqual(pdf_search.search_pdf("anything", k=5), [])
            finally:
                pdf_search.DB_PATH = orig


if __name__ == "__main__":
    unittest.main()
