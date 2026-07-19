#!/usr/bin/env python3
"""Tests for pdf_extract — pypdf text extraction + a per-page char map.

pypdf is an *optional* dependency (requirements-pdf.txt), so this whole module skips
cleanly when it is absent — which is exactly the state of core CI (test backend, no
pypdf). When pypdf IS present we build a tiny multi-page PDF in a tempdir at run time
(the same self-contained-fixture style as test_tag_hygiene.py — nothing to commit or
emission-exclude), extract it, and confirm the text and page map are what chunker
expects.

    python3 tests/test_pdf_extract.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

try:
    import pypdf  # noqa: F401
    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False

if HAVE_PYPDF:
    import chunker  # noqa: E402
    import pdf_extract  # noqa: E402


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _make_pdf(pages: list[str]) -> bytes:
    """Build a minimal valid PDF, one text line per page string. Deterministic.

    A hand-written PDF (catalog -> pages -> per-page content stream -> font) with a
    correct xref table, so pypdf extracts the exact text back. Kept tiny on purpose;
    it exists only to give the extractor a real file to read.
    """
    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    n = len(pages)
    page_ids = [3 + 2 * i for i in range(n)]
    content_ids = [4 + 2 * i for i in range(n)]
    font_id = 3 + 2 * n
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    for i, text in enumerate(pages):
        objs.append((
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_ids[i]} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        ).encode())
        stream = f"BT /F1 12 Tf 72 720 Td ({_esc(text)}) Tj ET".encode()
        objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for idx, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    size = len(objs) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return bytes(out)


@unittest.skipUnless(HAVE_PYPDF, "pypdf not installed (optional dep, requirements-pdf.txt)")
class ExtractTest(unittest.TestCase):
    PAGES = [
        "The quick brown fox jumps over the lazy dog.",
        "Second page discussing zephyr canary retrieval tokens.",
    ]

    def _extract(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.pdf"
            path.write_bytes(_make_pdf(self.PAGES))
            return pdf_extract.extract(path)

    def test_returns_a_span_per_page(self):
        doc = self._extract()
        self.assertEqual(len(doc.page_spans), 2)
        self.assertEqual([p for p, _, _ in doc.page_spans], [1, 2])

    def test_each_span_slices_back_to_its_page_text(self):
        doc = self._extract()
        for (page, start, end), original in zip(doc.page_spans, self.PAGES):
            # pypdf may add trailing whitespace/newlines; the words must be present.
            self.assertIn("zephyr" if page == 2 else "fox", doc.text[start:end])

    def test_extracted_text_carries_both_pages(self):
        doc = self._extract()
        self.assertIn("brown fox", doc.text)
        self.assertIn("zephyr canary", doc.text)

    def test_chunker_tags_pages_from_the_extracted_map(self):
        doc = self._extract()
        chunks = chunker.chunk_text(doc.text, doc.page_spans, chunk_tokens=6, overlap=0.0)
        # First chunk starts on page 1; a later chunk must reach page 2.
        self.assertEqual(chunks[0].page, 1)
        self.assertIn(2, [c.page for c in chunks])


if __name__ == "__main__":
    unittest.main()
