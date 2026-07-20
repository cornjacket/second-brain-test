#!/usr/bin/env python3
"""Tests for embed_pdf — the chunk-list sidecar writer (task #7 M2).

The whole point of M2 is that a chunked source's sidecar is **deterministic on the
`test` backend**, so we can pin it: the test regenerates the sidecar from a fixed
text + page map and byte-compares it to the committed fixture
(`tests/fixtures/pdf/sample.embed.json`). A format drift — a renamed field, a changed
default, a reordered key — breaks that byte-equality, which a generate-twice check
alone would miss. No pypdf and no model are involved; this runs anywhere CI does.

    python3 tests/test_embed_pdf.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Force the deterministic backend regardless of this brain's config, so the fixture
# is reproducible. embedder reads this env var live, so setting it before import is enough.
os.environ["SECOND_BRAIN_EMBEDDER"] = "test"

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import embed_pdf  # noqa: E402

# Fixed input, matching tests/fixtures/pdf/sample.embed.json. Eight one-token words on a
# single-space grid; a page break at char 23 puts chunk 0 on page 1 and chunk 1 on page 2.
SOURCE = "tests/fixtures/pdf/sample.pdf"
TEXT = "alpha beta gamma delta epsilon zeta eta theta"
PAGE_SPANS = [(1, 0, 23), (2, 23, 45)]
FIXTURE = REPO_ROOT / "tests/fixtures/pdf/sample.embed.json"


def _bytes():
    return embed_pdf.sidecar_bytes(SOURCE, TEXT, PAGE_SPANS, chunk_tokens=4, chunk_overlap=0.0)


class SidecarFormatTest(unittest.TestCase):
    def test_matches_committed_fixture_byte_for_byte(self):
        self.assertEqual(_bytes(), FIXTURE.read_text(encoding="utf-8"),
                         "sidecar drifted from tests/fixtures/pdf/sample.embed.json — "
                         "regenerate the fixture if this change is intended")

    def test_is_deterministic(self):
        self.assertEqual(_bytes(), _bytes())

    def test_top_level_shape(self):
        d = json.loads(_bytes())
        self.assertEqual(set(d), {"source_file", "type", "content_hash", "chunking", "chunks"})
        self.assertEqual(d["type"], "test")
        self.assertNotIn("embedded_at", d, "deterministic backend must omit embedded_at")
        self.assertEqual(d["chunking"], {"chunk_tokens": 4, "chunk_overlap": 0.0})

    def test_content_hash_is_sha256_of_the_source_text(self):
        d = json.loads(_bytes())
        self.assertEqual(d["content_hash"],
                         "sha256:" + hashlib.sha256(TEXT.encode()).hexdigest())

    def test_chunks_carry_every_field_and_slice_back_to_source(self):
        chunks = json.loads(_bytes())["chunks"]
        self.assertEqual(len(chunks), 2)
        self.assertEqual([c["chunk_id"] for c in chunks], [0, 1])
        self.assertEqual([c["page"] for c in chunks], [1, 2])
        for c in chunks:
            self.assertEqual(set(c), {"chunk_id", "page", "char_start", "char_end",
                                      "text", "vector"})
            self.assertEqual(c["text"], TEXT[c["char_start"]:c["char_end"]])
            self.assertEqual(len(c["vector"]), 768)


class WriteGateTest(unittest.TestCase):
    def test_writes_then_skips_unchanged_then_force_rewrites(self):
        with tempfile.TemporaryDirectory() as td:
            src = str(Path(td) / "sample.pdf")  # absolute -> sidecar lands beside it, not in the repo
            dest, wrote = embed_pdf.write_chunk_sidecar(src, TEXT, PAGE_SPANS,
                                                        chunk_tokens=4, chunk_overlap=0.0)
            self.assertTrue(wrote and dest.exists())

            _, wrote_again = embed_pdf.write_chunk_sidecar(src, TEXT, PAGE_SPANS,
                                                           chunk_tokens=4, chunk_overlap=0.0)
            self.assertFalse(wrote_again, "unchanged substance + params must be a no-op")

            _, forced = embed_pdf.write_chunk_sidecar(src, TEXT, PAGE_SPANS, chunk_tokens=4,
                                                      chunk_overlap=0.0, force=True)
            self.assertTrue(forced, "force must rewrite regardless of the no-op gate")

    def test_changed_chunking_params_re_embed(self):
        with tempfile.TemporaryDirectory() as td:
            src = str(Path(td) / "sample.pdf")
            embed_pdf.write_chunk_sidecar(src, TEXT, PAGE_SPANS, chunk_tokens=4, chunk_overlap=0.0)
            # Same text, different chunk size -> the gate must NOT skip.
            _, wrote = embed_pdf.write_chunk_sidecar(src, TEXT, PAGE_SPANS, chunk_tokens=3,
                                                     chunk_overlap=0.0)
            self.assertTrue(wrote, "a changed chunk size must invalidate the no-op gate")


if __name__ == "__main__":
    unittest.main()
