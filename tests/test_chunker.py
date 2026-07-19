#!/usr/bin/env python3
"""Tests for chunker — the pure, deterministic text->passages splitter.

No PDF and no embedding model: chunker is stdlib-only, so these run everywhere
(including CI). We pin small chunk sizes over a known word grid so every char span,
overlap, and page assignment is asserted exactly, not approximately.

    python3 tests/test_chunker.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import chunker  # noqa: E402

# Ten two-char words "w0".."w9" on a single-space grid: word k spans [3k, 3k+2).
WORDS = " ".join(f"w{k}" for k in range(10))


class ChunkTest(unittest.TestCase):
    def test_empty_and_whitespace_yield_no_chunks(self):
        self.assertEqual(chunker.chunk_text(""), [])
        self.assertEqual(chunker.chunk_text("   \n\t  "), [])

    def test_short_text_is_a_single_chunk(self):
        chunks = chunker.chunk_text("a b c", chunk_tokens=512)
        self.assertEqual(len(chunks), 1)
        c = chunks[0]
        self.assertEqual((c.chunk_id, c.char_start, c.char_end), (0, 0, 5))
        self.assertEqual(c.text, "a b c")
        self.assertIsNone(c.page)

    def test_overlapping_windows_have_exact_spans(self):
        # chunk_tokens=4, overlap=0.25 -> step 3: windows [0:4], [3:7], [6:10].
        chunks = chunker.chunk_text(WORDS, chunk_tokens=4, overlap=0.25)
        spans = [(c.chunk_id, c.char_start, c.char_end, c.text) for c in chunks]
        self.assertEqual(spans, [
            (0, 0, 11, "w0 w1 w2 w3"),
            (1, 9, 20, "w3 w4 w5 w6"),
            (2, 18, 29, "w6 w7 w8 w9"),
        ])

    def test_text_is_exactly_the_source_slice(self):
        for c in chunker.chunk_text(WORDS, chunk_tokens=4, overlap=0.25):
            self.assertEqual(c.text, WORDS[c.char_start:c.char_end])

    def test_adjacent_chunks_overlap_by_one_token(self):
        chunks = chunker.chunk_text(WORDS, chunk_tokens=4, overlap=0.25)
        # The last word of each chunk reappears as the first word of the next.
        self.assertTrue(chunks[0].text.endswith("w3") and chunks[1].text.startswith("w3"))
        self.assertTrue(chunks[1].text.endswith("w6") and chunks[2].text.startswith("w6"))

    def test_no_overlap_tiles_without_gaps(self):
        chunks = chunker.chunk_text(WORDS, chunk_tokens=5, overlap=0.0)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].text, "w0 w1 w2 w3 w4")
        self.assertEqual(chunks[1].text, "w5 w6 w7 w8 w9")

    def test_page_map_tags_each_chunk_by_its_start(self):
        # page 1 owns chars [0,12) (w0..w3), page 2 owns [12,29) (w4..w9).
        spans = [(1, 0, 12), (2, 12, 29)]
        chunks = chunker.chunk_text(WORDS, spans, chunk_tokens=4, overlap=0.25)
        self.assertEqual([c.page for c in chunks], [1, 1, 2])

    def test_char_in_page_gap_falls_back_to_last_started_page(self):
        # A gap between page 1 (ends 5) and page 2 (starts 20): a start at 9 -> page 1.
        spans = [(1, 0, 5), (2, 20, 29)]
        chunks = chunker.chunk_text(WORDS, spans, chunk_tokens=4, overlap=0.25)
        self.assertEqual(chunks[1].page, 1)  # starts at char 9, in the gap

    def test_invalid_params_raise(self):
        with self.assertRaises(ValueError):
            chunker.chunk_text("a b", chunk_tokens=0)
        with self.assertRaises(ValueError):
            chunker.chunk_text("a b", overlap=1.0)
        with self.assertRaises(ValueError):
            chunker.chunk_text("a b", overlap=-0.1)


if __name__ == "__main__":
    unittest.main()
