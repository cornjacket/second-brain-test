"""Extract text from a PDF, with a page map, for chunking.

Turns a PDF into (a) one concatenated text string and (b) a list of page spans
telling which character range came from which page. Feed the result straight to
scripts/chunker.py, which needs exactly that shape to tag each chunk with a page.

The parser is **pypdf**, an *optional* dependency shipped in ``requirements-pdf.txt``
(like ``requirements-mcp.txt`` for the Desktop interface) so the core brain and CI
stay stdlib-lean. ``import pdf_extract`` is always safe — pypdf is imported lazily,
inside the call — so a brain without pypdf can still load this module; only actually
extracting raises, with a clear "install requirements-pdf.txt" message.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from chunker import PageSpan

# Inserted between adjacent pages' text so tokens from different pages don't fuse
# across a page boundary. It is whitespace, so it never becomes part of a chunk
# (chunker's tokens are non-whitespace runs) and page spans exclude it.
_PAGE_SEP = "\n\n"


@dataclass
class ExtractedDoc:
    """The text of a PDF plus where each page lives in it.

    ``text`` is every page concatenated (separated by blank lines). ``page_spans``
    are ``(page_number, char_start, char_end)`` tuples, 1-based pages, end exclusive,
    covering each page's own text (not the separators) — the exact input chunker
    wants for page tagging.
    """
    text: str
    page_spans: list[PageSpan] = field(default_factory=list)


def _require_pypdf():
    try:
        import pypdf  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "PDF support needs pypdf, which is not installed. Install the optional "
            "dependency:\n\n    pip install -r requirements-pdf.txt\n"
        ) from exc
    return pypdf


def extract(path: str | Path) -> ExtractedDoc:
    """Read ``path`` and return its text with a per-page char map.

    Pages that yield no extractable text (e.g. scanned images) contribute an empty
    span and are kept in the numbering, so page numbers still line up with the file.
    """
    pypdf = _require_pypdf()
    reader = pypdf.PdfReader(str(path))

    parts: list[str] = []
    spans: list[PageSpan] = []
    cursor = 0
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        start = cursor
        parts.append(page_text)
        cursor += len(page_text)
        spans.append((page_number, start, cursor))
        parts.append(_PAGE_SEP)
        cursor += len(_PAGE_SEP)

    return ExtractedDoc(text="".join(parts), page_spans=spans)
