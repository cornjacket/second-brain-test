#!/usr/bin/env python3
"""Tests for pdf_cache — the bolt-on PDF-chunk tables and their loader (task #7 M3).

Two things to prove:
  1. the loader builds the three parallel tables correctly — rowids aligned across all
     three, the vector leg (KNN) and the keyword leg (FTS5 MATCH) both find a chunk, and a
     single-source refresh replaces rather than duplicates;
  2. wiring it into hydrate_cache leaves the **note path byte-identical** — a vault with a
     PDF sidecar produces the same notes/notes_fts rows as one without.

Deterministic `test` backend, no pypdf, no model. Reuses the committed M2 fixture as the
chunked-source input.

    python3 tests/test_pdf_cache.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["SECOND_BRAIN_EMBEDDER"] = "test"  # deterministic vectors

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import sqlite_vec  # noqa: E402
from db import connect  # noqa: E402
import embedder  # noqa: E402
import note_view  # noqa: E402
import pdf_cache  # noqa: E402

FIXTURE = json.loads((REPO_ROOT / "tests/fixtures/pdf/sample.embed.json").read_text())


def _rowids(db, table):
    return sorted(r for (r,) in db.execute(f"SELECT rowid FROM {table}"))


class LoaderTest(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        pdf_cache.ensure_tables(self.db)

    def tearDown(self):
        self.db.close()

    def test_load_all_populates_meta_with_every_field(self):
        n = pdf_cache.load_all(self.db, [FIXTURE])
        self.assertEqual(n, 2)
        rows = list(self.db.execute(
            "SELECT source_file, chunk_id, page, char_start, char_end, text "
            "FROM pdf_chunks_meta ORDER BY chunk_id"))
        self.assertEqual(len(rows), 2)
        self.assertEqual([r[1] for r in rows], [0, 1])       # chunk_id
        self.assertEqual([r[2] for r in rows], [1, 2])       # page
        self.assertEqual(rows[0][5], "alpha beta gamma delta")

    def test_rowids_align_across_all_three_tables(self):
        pdf_cache.load_all(self.db, [FIXTURE])
        self.assertEqual(_rowids(self.db, "pdf_chunks_meta"), [1, 2])
        self.assertEqual(_rowids(self.db, "pdf_chunks"),
                         _rowids(self.db, "pdf_chunks_meta"))
        self.assertEqual(_rowids(self.db, "pdf_chunks_fts"),
                         _rowids(self.db, "pdf_chunks_meta"))

    def test_vector_leg_knn_finds_the_chunk(self):
        pdf_cache.load_all(self.db, [FIXTURE])
        q = sqlite_vec.serialize_float32(FIXTURE["chunks"][1]["vector"])
        hits = list(self.db.execute(
            "SELECT rowid, distance FROM pdf_chunks WHERE embedding MATCH ? AND k = ? "
            "ORDER BY distance", (q, 2)))
        self.assertEqual(hits[0][0], 2)          # chunk 1 -> rowid 2 is nearest to itself
        self.assertAlmostEqual(hits[0][1], 0.0, places=5)

    def test_keyword_leg_fts_matches_only_text(self):
        pdf_cache.load_all(self.db, [FIXTURE])
        hits = [c for (c,) in self.db.execute(
            "SELECT chunk_id FROM pdf_chunks_fts WHERE pdf_chunks_fts MATCH 'zeta'")]
        self.assertEqual(hits, [1])              # 'zeta' is only in chunk 1's text

    def test_update_source_replaces_not_duplicates(self):
        pdf_cache.load_all(self.db, [FIXTURE])
        n = pdf_cache.update_source(self.db, FIXTURE)   # same source again
        self.assertEqual(n, 2)
        for table in ("pdf_chunks_meta", "pdf_chunks", "pdf_chunks_fts"):
            count = list(self.db.execute(f"SELECT COUNT(*) FROM {table}"))[0][0]
            self.assertEqual(count, 2, f"{table} should still have 2 rows, not 4")


class HydrateIntegrationTest(unittest.TestCase):
    """hydrate_cache with a PDF sidecar present vs absent — note path must not move."""

    def _build_vault(self, tmp: Path, with_pdf: bool) -> None:
        areas = tmp / "vault" / "areas"
        areas.mkdir(parents=True)
        note_md = areas / "note.md"
        note_md.write_text("---\ntags: [x]\n---\n\n# Note\n\nSpaced repetition helps memory.\n",
                           encoding="utf-8")
        vec = embedder.embed(note_view.canonical_body(note_md.read_text()))
        (areas / ".note.embed.json").write_text(
            json.dumps({"source_file": "vault/areas/note.md", "type": "test", "vector": vec}),
            encoding="utf-8")
        if with_pdf:
            res = tmp / "vault" / "resources"
            res.mkdir(parents=True)
            (res / ".sample.pdf.embed.json").write_text(json.dumps(FIXTURE), encoding="utf-8")

    def _hydrate(self, tmp: Path):
        import hydrate_cache as H
        H.REPO_ROOT, H.VAULT_DIR = tmp, tmp / "vault"
        H.CACHE_DIR, H.DB_PATH = tmp / "data", tmp / "data" / "brain.db"
        H.main()
        return connect(H.DB_PATH)

    def _notes(self, db):
        notes = [r for (r,) in db.execute("SELECT source_file FROM notes ORDER BY source_file")]
        fts = [r for (r,) in db.execute(
            "SELECT source_file FROM notes_fts WHERE notes_fts MATCH 'memory'")]
        return notes, fts

    def test_pdf_sidecar_loads_and_leaves_notes_untouched(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self._build_vault(Path(a), with_pdf=True)
            self._build_vault(Path(b), with_pdf=False)
            db_with = self._hydrate(Path(a))
            db_without = self._hydrate(Path(b))
            try:
                # the PDF chunks loaded...
                chunks = list(db_with.execute("SELECT COUNT(*) FROM pdf_chunks_meta"))[0][0]
                self.assertEqual(chunks, 2)
                # ...and the note path is identical with or without the PDF sidecar
                self.assertEqual(self._notes(db_with), self._notes(db_without))
                self.assertEqual(self._notes(db_with)[0], ["vault/areas/note.md"])
            finally:
                db_with.close()
                db_without.close()


if __name__ == "__main__":
    unittest.main()
