#!/usr/bin/env python3
"""Write a chunked source's ``.embed.json`` sidecar — a *list* of chunk vectors.

A note is one row → one vector, and `embed_staged.py` writes it a single-vector
sidecar. A PDF (or any long source) is **many** passages → many vectors, so it gets
a sidecar holding a **list** of chunks, each `{chunk_id, page, char_start, char_end,
text, vector}` (see docs/pdf-ingestion.md §4, task #7 M2). The note path is untouched;
this is the additive "bolt-on" writer.

**It takes already-extracted text, not a PDF.** The caller runs `pdf_extract.extract`
(which needs the optional `pypdf`) and hands the text + page map here. Keeping this
module pypdf-free is what lets it — and its committed fixture — run in CI on the
deterministic `test` backend with no optional dependency installed.

Each chunk is embedded with `task="document"` (it is stored/indexed text, exactly
like a note), and the sidecar mirrors the note sidecar's metadata: `type` stamps the
backend, `content_hash` fingerprints the source substance for the re-embed no-op gate,
and `embedded_at` is added only for non-deterministic backends so `test` sidecars stay
byte-stable.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunker import PageSpan, chunk_text  # noqa: E402
from embedder import backend_id, embed, is_deterministic  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# Defaults for the token-window chunker (docs/pdf-ingestion.md §1.4). Config wiring
# (the [pdf] block in config/features.toml) lands with the add_pdf command at M5.
DEFAULT_CHUNK_TOKENS = 512
DEFAULT_CHUNK_OVERLAP = 0.15


def sidecar_path(source_file: str) -> Path:
    """Derived sidecar for a chunked source: ``<dir>/.<name>.embed.json``.

    The **full filename** (extension included) goes in the name — `report.pdf` →
    `.report.pdf.embed.json` — so a PDF sidecar never collides with a same-stem note's
    `.report.embed.json`, and the source path is recoverable from the sidecar name. It
    is still matched by the vault sidecar git-ignore, so it is derived + never committed.
    """
    p = Path(source_file)
    return REPO_ROOT / p.parent / f".{p.name}.embed.json"


def _content_hash(text: str) -> str:
    """`sha256:<hex>` of the extracted text — the source's embedded substance.

    A byte-stable fingerprint (like note_view.content_hash for notes) answering "did the
    source change since we last embedded?" The PDF's substance is its extracted text, so
    that is what we hash — no Markdown canonicalization, which is a note-only concern.
    """
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def build_chunks(
    text: str,
    page_spans: list[PageSpan] | None,
    *,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    chunk_overlap: float = DEFAULT_CHUNK_OVERLAP,
) -> list[dict]:
    """Chunk ``text`` and embed each passage — the ordered list of chunk records."""
    records = []
    for c in chunk_text(text, page_spans, chunk_tokens=chunk_tokens, overlap=chunk_overlap):
        records.append({
            "chunk_id": c.chunk_id,
            "page": c.page,
            "char_start": c.char_start,
            "char_end": c.char_end,
            "text": c.text,
            "vector": embed(c.text, task="document"),
        })
    return records


def sidecar_payload(
    source_file: str,
    text: str,
    page_spans: list[PageSpan] | None,
    *,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    chunk_overlap: float = DEFAULT_CHUNK_OVERLAP,
) -> dict:
    """The full sidecar dict for a chunked source (see module docstring)."""
    payload = {
        "source_file": source_file,
        "type": backend_id(),
        "content_hash": _content_hash(text),
        "chunking": {"chunk_tokens": chunk_tokens, "chunk_overlap": chunk_overlap},
        "chunks": build_chunks(text, page_spans, chunk_tokens=chunk_tokens,
                               chunk_overlap=chunk_overlap),
    }
    if not is_deterministic():
        payload["embedded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return payload


def sidecar_bytes(source_file: str, text: str, page_spans: list[PageSpan] | None,
                  **kw) -> str:
    """Render the sidecar JSON exactly as written to disk (byte-stable on `test`)."""
    return json.dumps(sidecar_payload(source_file, text, page_spans, **kw), indent=2) + "\n"


def write_chunk_sidecar(
    source_file: str,
    text: str,
    page_spans: list[PageSpan] | None,
    *,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    chunk_overlap: float = DEFAULT_CHUNK_OVERLAP,
    force: bool = False,
) -> tuple[Path, bool]:
    """Write the chunked source's sidecar; return ``(path, wrote)``.

    No-op gate (mirrors `embed_staged.write_sidecar`): skip the re-embed when an existing
    sidecar was produced by the active backend, over the same substance, with the same
    chunking parameters — nothing could have changed. ``force`` rewrites regardless.
    """
    dest = sidecar_path(source_file)
    if not force and dest.exists():
        try:
            prev = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = {}
        same_chunking = prev.get("chunking") == {"chunk_tokens": chunk_tokens,
                                                 "chunk_overlap": chunk_overlap}
        if (prev.get("type") == backend_id()
                and prev.get("content_hash") == _content_hash(text)
                and same_chunking):
            return dest, False
    dest.write_text(
        sidecar_bytes(source_file, text, page_spans,
                      chunk_tokens=chunk_tokens, chunk_overlap=chunk_overlap),
        encoding="utf-8",
    )
    return dest, True
