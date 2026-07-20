#!/usr/bin/env python3
"""Passage search over the PDF-chunk tables (task #7 M4).

Returns a *passage* — a specific chunk, with its page and a snippet — not just "this file
matched somewhere." It fuses two legs at the **chunk grain** with Reciprocal Rank Fusion,
the same fusion the note search uses (scripts/features.rrf_k), over chunk rowids:

- **meaning** — cosine-KNN over `pdf_chunks` (the vector leg);
- **keyword** — FTS5/BM25 over `pdf_chunks_fts` (the lexical leg; gated by `hybrid_search`).

Then it shapes the fused hits:

- ``result_mode="best_per_source"`` — one best passage per document, so a big PDF cannot
  flood the top-k (the default);
- ``result_mode="all_chunks"`` — every passage, in fused order;
- ``source_file=<path>`` — restrict to one document ("where in *this* PDF is X").

Standalone from search_vault by design: the note search path is **untouched**. The two are
unified into the one MCP/CLI search surface when the add_pdf command lands (task #7 M5/M6);
this module is not emitted into a brain until then.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402
from embedder import embed  # noqa: E402
from features import hybrid_search, rrf_k  # noqa: E402
from search_vault import _fts_match_query  # noqa: E402  (identical query tokenization)

import sqlite_vec  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "brain.db"

# Default shaping. Config wiring (the [pdf] block in config/features.toml) lands at M5.
DEFAULT_RESULT_MODE = "best_per_source"
_SNIPPET_WIDTH = 240


@dataclass(frozen=True)
class PassageHit:
    """One passage returned by search: which document, which chunk/page, a snippet, its score."""
    source_file: str
    chunk_id: int
    page: int | None
    snippet: str
    score: float


def _snippet(text: str) -> str:
    """One-line, width-bounded preview of a chunk's text."""
    s = " ".join(text.split())
    return s if len(s) <= _SNIPPET_WIDTH else s[:_SNIPPET_WIDTH].rstrip() + "…"


def _has_pdf_tables(db) -> bool:
    """True once any PDF has been ingested — else search is a clean no-op (returns [])."""
    rows = list(db.execute("SELECT name FROM sqlite_master WHERE name = 'pdf_chunks'"))
    return bool(rows)


def _vector_rowids(db, query: str, n: int) -> list[int]:
    """rowids of the top-``n`` vector (cosine-KNN) hits over pdf_chunks, nearest first."""
    qvec = embed(query, task="query")
    return [r for (r, _d) in db.execute(
        "SELECT rowid, distance FROM pdf_chunks WHERE embedding MATCH ? AND k = ? "
        "ORDER BY distance", (sqlite_vec.serialize_float32(qvec), n))]


def _lexical_rowids(db, query: str, n: int, source_file: str | None) -> list[int]:
    """rowids of the top-``n`` FTS5/BM25 hits, best first; degrades to [] on any FTS error.

    ``source_file`` filters on the (UNINDEXED but stored) column, so the keyword leg can be
    scoped to one document for the within-document mode.
    """
    match = _fts_match_query(query)
    if not match:
        return []
    sql = "SELECT rowid FROM pdf_chunks_fts WHERE pdf_chunks_fts MATCH ?"
    params: list = [match]
    if source_file is not None:
        sql += " AND source_file = ?"
        params.append(source_file)
    sql += " ORDER BY rank LIMIT ?"
    params.append(n)
    try:
        return [r for (r,) in db.execute(sql, tuple(params))]
    except Exception:
        return []


def _fuse(legs: list[list[int]], k_rrf: int) -> dict[int, float]:
    """RRF score per rowid: Σ 1/(k_rrf + rank) over the legs it appears in."""
    scores: dict[int, float] = {}
    for ranked in legs:
        for rank, rid in enumerate(ranked, 1):
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k_rrf + rank)
    return scores


def search_pdf(query: str, k: int = 5, *, result_mode: str | None = None,
               source_file: str | None = None) -> list[PassageHit]:
    """Fused chunk-grain passage search; see the module docstring for the shaping options."""
    if not DB_PATH.exists():
        raise SystemExit("cache missing; run scripts/hydrate_cache.py first")
    mode = result_mode or DEFAULT_RESULT_MODE

    db = connect(DB_PATH)
    try:
        if not _has_pdf_tables(db):
            return []  # no PDFs ingested yet
        # Within one document, widen the pool to cover all of its chunks so none is missed;
        # globally, fuse over a candidate pool a bit wider than k, then trim.
        if source_file is not None:
            pool = max(list(db.execute("SELECT COUNT(*) FROM pdf_chunks_meta"))[0][0], 1)
        else:
            pool = max(k, 20)

        legs = [_vector_rowids(db, query, pool)]
        if hybrid_search():
            legs.append(_lexical_rowids(db, query, pool, source_file))
        scores = _fuse(legs, rrf_k())
        ranked = sorted(scores, key=lambda r: scores[r], reverse=True)

        hits: list[PassageHit] = []
        seen_sources: set[str] = set()
        for rid in ranked:
            rows = list(db.execute(
                "SELECT source_file, chunk_id, page, text FROM pdf_chunks_meta WHERE rowid = ?",
                (rid,)))
            if not rows:
                continue
            src, chunk_id, page, text = rows[0]
            if source_file is not None and src != source_file:
                continue                      # within-document: drop other docs (vector leg is global)
            if mode == "best_per_source":
                if src in seen_sources:
                    continue                  # keep only each document's top passage
                seen_sources.add(src)
            hits.append(PassageHit(source_file=src, chunk_id=chunk_id, page=page,
                                   snippet=_snippet(text), score=scores[rid]))
            if len(hits) >= k:
                break
        return hits
    finally:
        db.close()


def get_passage(source_file: str, chunk_id: int) -> dict | None:
    """Fetch one passage's **full** text by (source_file, chunk_id); ``None`` if absent.

    Search returns a bounded snippet; this is the "read the whole passage" companion — the
    passage-fetch tool a Desktop client calls after a search hit to see the full chunk.
    """
    if not DB_PATH.exists():
        raise SystemExit("cache missing; run scripts/hydrate_cache.py first")
    db = connect(DB_PATH)
    try:
        if not _has_pdf_tables(db):
            return None
        rows = list(db.execute(
            "SELECT source_file, chunk_id, page, text FROM pdf_chunks_meta "
            "WHERE source_file = ? AND chunk_id = ?", (source_file, chunk_id)))
        if not rows:
            return None
        src, cid, page, text = rows[0]
        return {"source_file": src, "chunk_id": cid, "page": page, "text": text}
    finally:
        db.close()
