#!/usr/bin/env python3
"""Tests for doctor's PDF parity (task #7 M6).

Emitting PDF support gave doctor a hazard: PDF chunk sidecars (`.x.pdf.embed.json`) match the
same `.*.embed.json` glob as note sidecars, so without classification doctor would read one as
an orphan, wrong-dim note. This asserts the fix — a PDF sidecar is never mis-flagged in the
note pass — and that a consistently-ingested PDF scans clean (the stale check, which needs
pypdf, runs when it is present).

    python3 tests/test_doctor_pdf.py
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
sys.path.insert(0, str(REPO_ROOT / "tests"))
import doctor
import embed_pdf
import embedder
import hydrate_cache as H
import note_view
from db import connect
from test_pdf_extract import _make_pdf

try:
    import pdf_extract
    import pypdf  # noqa: F401
    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False


def _build(tmp: Path, pdf_payload: dict, pdf_bytes: bytes) -> None:
    (tmp / "vault" / "areas").mkdir(parents=True, exist_ok=True)
    (tmp / "vault" / "resources").mkdir(parents=True, exist_ok=True)
    (tmp / "data").mkdir(exist_ok=True)
    note = tmp / "vault" / "areas" / "n.md"
    note.write_text("---\ntags: [x]\n---\n\n# N\n\nspaced repetition.\n", encoding="utf-8")
    (tmp / "vault" / "areas" / ".n.embed.json").write_text(json.dumps({
        "source_file": "vault/areas/n.md", "type": "test",
        "content_hash": note_view.content_hash(note.read_text()),
        "vector": embedder.embed(note_view.canonical_body(note.read_text()))}), encoding="utf-8")
    (tmp / "vault" / "resources" / "p.pdf").write_bytes(pdf_bytes)
    (tmp / "vault" / "resources" / ".p.pdf.embed.json").write_text(json.dumps(pdf_payload),
                                                                   encoding="utf-8")


def _scan(tmp: Path):
    db = connect(tmp / "data" / "brain.db")
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS notes USING vec0("
               "source_file TEXT PRIMARY KEY, embedding FLOAT[768] distance_metric=cosine)")
    db.close()
    for mod in (doctor, H):
        mod.REPO_ROOT, mod.VAULT_DIR, mod.DB_PATH = tmp, tmp / "vault", tmp / "data" / "brain.db"
    H.CACHE_DIR = tmp / "data"
    H.main()
    return doctor.scan()


class DoctorPdfTest(unittest.TestCase):
    def test_pdf_sidecar_is_not_misflagged_in_the_note_pass(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            payload = embed_pdf.sidecar_payload("vault/resources/p.pdf", "alpha zephyr beta gamma",
                                                [(1, 0, 23)], chunk_tokens=4, chunk_overlap=0.0)
            _build(tmp, payload, b"%PDF-1.4 not-a-real-pdf")
            st = _scan(tmp)
            # the note pass must not see the PDF sidecar at all
            self.assertEqual(st["orphan_sidecars"], set())
            self.assertEqual(st["bad_dim"], set())
            # and the PDF pass must find it consistent (loaded, right backend/dims)
            self.assertEqual(st["pdf"]["orphan"], set())
            self.assertEqual(st["pdf"]["bad_dim"], set())
            self.assertEqual(st["pdf"]["mixed"], set())
            self.assertEqual(st["pdf"]["missing_from_db"], set())

    @unittest.skipUnless(HAVE_PYPDF, "pypdf needed to re-extract for the stale check")
    def test_consistently_ingested_pdf_is_not_stale(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pdf_bytes = _make_pdf(["alpha zephyr overview", "beta gamma details"])
            (tmp / "vault" / "resources").mkdir(parents=True)
            pdf_tmp = tmp / "vault" / "resources" / "p.pdf"
            pdf_tmp.write_bytes(pdf_bytes)
            doc = pdf_extract.extract(pdf_tmp)         # hash the SAME text doctor will re-extract
            payload = embed_pdf.sidecar_payload("vault/resources/p.pdf", doc.text, doc.page_spans)
            _build(tmp, payload, pdf_bytes)
            st = _scan(tmp)
            self.assertEqual(st["pdf"]["stale"], set())
            self.assertEqual(st["pdf"]["unverifiable"], set())


if __name__ == "__main__":
    unittest.main()
