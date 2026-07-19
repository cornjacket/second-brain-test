"""Split long text into overlapping passages ("chunks") for embedding.

Notes are short — one note becomes one vector. A PDF (or a very long note) spans
many topics, so embedding the whole thing into a single vector produces a blurry
average that ranks poorly against a query about one passage. The fix is to split
the text into passages and embed each one, so a search hit points at *the passage*,
not just "somewhere in this document" (see docs/pdf-ingestion.md).

This module is deliberately **source-type-agnostic**: it takes plain text (plus an
optional page map) and returns chunks, so a PDF extractor, a long Markdown note, or
any other long source can reuse it. It is **pure standard library** — no PDF parser,
no embedding model, no database — so it is fully deterministic and unit-testable.

**"Token" here means a whitespace-delimited word**, used as a dependency-free proxy
for the embedding model's tokens. Real model tokens differ (a word is often more
than one token), but chunk *granularity* is what matters for retrieval, and a
~512-word chunk stays well inside nomic-embed-text's 2048-token window. Each chunk
records its ``page`` and its character span (``char_start``/``char_end``) so a hit
can say "page 12" and the exact passage can be located in the source text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# A page's extent in the extracted text: (page_number, char_start, char_end), with
# char_end exclusive. This is the contract with scripts/pdf_extract.py, which emits
# spans of exactly this shape. char_start is the offset of the page's first char in
# the concatenated document text.
PageSpan = tuple[int, int, int]

_WORD = re.compile(r"\S+")  # a "token" is a run of non-whitespace characters


@dataclass(frozen=True)
class Chunk:
    """One passage of a source, ready to embed.

    ``page`` is the page the chunk *starts* on (``None`` when no page map is given,
    e.g. a long note). ``char_start``/``char_end`` are offsets into the source text
    (end exclusive), so ``text == source[char_start:char_end]``.
    """
    chunk_id: int
    page: int | None
    char_start: int
    char_end: int
    text: str


def _page_of(char: int, page_spans: list[PageSpan] | None) -> int | None:
    """Page number whose span contains ``char``; ``None`` if no map is given.

    Falls back to the last page that starts at or before ``char`` — a chunk boundary
    can land in the whitespace gap between two pages' text, and a token always starts
    inside some page, so "last page started" is the correct, robust answer.
    """
    if not page_spans:
        return None
    found = None
    for page, start, end in page_spans:
        if start <= char < end:
            return page
        if start <= char:
            found = page  # remember the latest page that has begun
    return found


def chunk_text(
    text: str,
    page_spans: list[PageSpan] | None = None,
    *,
    chunk_tokens: int = 512,
    overlap: float = 0.15,
) -> list[Chunk]:
    """Split ``text`` into overlapping ``chunk_tokens``-sized passages.

    Adjacent chunks share ``overlap`` (a fraction, e.g. 0.15 = 15%) of their tokens
    so a sentence straddling a boundary is not orphaned. ``page_spans`` (from
    scripts/pdf_extract.py) maps each chunk to a page; omit it for plain text. Empty
    or whitespace-only text yields no chunks.
    """
    if chunk_tokens < 1:
        raise ValueError(f"chunk_tokens must be >= 1, got {chunk_tokens}")
    if not (0.0 <= overlap < 1.0):
        raise ValueError(f"overlap must be in [0.0, 1.0), got {overlap}")

    tokens = [(m.start(), m.end()) for m in _WORD.finditer(text)]
    if not tokens:
        return []

    step = max(1, chunk_tokens - round(chunk_tokens * overlap))
    chunks: list[Chunk] = []
    i = 0
    while i < len(tokens):
        window = tokens[i:i + chunk_tokens]
        char_start = window[0][0]
        char_end = window[-1][1]
        chunks.append(Chunk(
            chunk_id=len(chunks),
            page=_page_of(char_start, page_spans),
            char_start=char_start,
            char_end=char_end,
            text=text[char_start:char_end],
        ))
        if i + chunk_tokens >= len(tokens):
            break  # this window reached the end; stop before emitting a tail duplicate
        i += step
    return chunks
