#!/usr/bin/env python3
"""Additive PDF-chunk cache tables + their loader (task #7 M3).

**Bolt-on.** The note tables (`notes`, `notes_fts`) are untouched; a chunked source
(one PDF) fans out to many rows across three parallel tables tied by a shared `rowid`
(docs/pdf-ingestion.md §4):

    pdf_chunks       (vec0)  embedding                                    ← the meaning leg
    pdf_chunks_meta  (table)  source_file, chunk_id, page, char_start,    ← the facts + text
                              char_end, text
    pdf_chunks_fts   (fts5)  source_file, chunk_id (UNINDEXED), text      ← the keyword leg

Chunk N is its vector in `pdf_chunks`, its facts in `pdf_chunks_meta`, and its searchable
text in `pdf_chunks_fts` — **all at the same rowid**, so a vector or keyword hit joins back
to page/text by rowid. `source_file` groups a document's chunks.

**Not emitted into a brain yet (task #7 M6).** `hydrate_cache.py` imports this defensively,
so a brain without it simply skips PDF loading and its note path stays byte-identical.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from embedder import EMBED_DIM  # noqa: E402

import sqlite_vec  # noqa: E402

# vec0 holds only the vector, keyed by rowid (the join key). The columns live in the
# plain meta table so they are cheap to read back and filter/group by source_file.
CHUNKS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS pdf_chunks USING vec0("
    f"embedding FLOAT[{EMBED_DIM}] distance_metric=cosine)"
)
META_DDL = (
    "CREATE TABLE IF NOT EXISTS pdf_chunks_meta("
    "rowid INTEGER PRIMARY KEY, source_file TEXT NOT NULL, chunk_id INTEGER NOT NULL, "
    "page INTEGER, char_start INTEGER NOT NULL, char_end INTEGER NOT NULL, text TEXT NOT NULL)"
)
# source_file + chunk_id are stored to identify/group a hit but UNINDEXED, so a query term
# never matches a path or an id and skews BM25 — only `text` is searched (same rule as notes_fts).
FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS pdf_chunks_fts USING fts5("
    "source_file UNINDEXED, chunk_id UNINDEXED, text)"
)


def ensure_tables(db) -> None:
    """Create the three tables if absent (IF NOT EXISTS — never dropped)."""
    db.execute(CHUNKS_DDL)
    db.execute(META_DDL)
    db.execute(FTS_DDL)


def clear(db) -> None:
    """Empty all three tables (full-rebuild reset, mirrors hydrate's DELETE FROM notes)."""
    db.execute("DELETE FROM pdf_chunks")
    db.execute("DELETE FROM pdf_chunks_meta")
    db.execute("DELETE FROM pdf_chunks_fts")


def _max_rowid(db) -> int:
    """Highest rowid currently in the chunk tables (0 if empty).

    We assign rowids explicitly rather than relying on ``lastrowid`` — the db wrapper
    spans sqlite3 and apsw, whose last-rowid APIs differ — so the same rowid can be
    inserted into all three tables in lockstep on either backend.
    """
    for (m,) in db.execute("SELECT COALESCE(MAX(rowid), 0) FROM pdf_chunks_meta"):
        return m
    return 0


def remove_source(db, source_file: str) -> None:
    """Delete every row for one source across all three tables (single-source refresh)."""
    rids = [r for (r,) in db.execute(
        "SELECT rowid FROM pdf_chunks_meta WHERE source_file = ?", (source_file,))]
    for rid in rids:
        db.execute("DELETE FROM pdf_chunks WHERE rowid = ?", (rid,))
    db.execute("DELETE FROM pdf_chunks_fts WHERE source_file = ?", (source_file,))
    db.execute("DELETE FROM pdf_chunks_meta WHERE source_file = ?", (source_file,))


def _insert(db, payload: dict) -> int:
    """Insert one chunked source's rows at fresh, aligned rowids. Returns chunk count."""
    src = payload["source_file"]
    rid = _max_rowid(db)
    for ch in payload["chunks"]:
        vec = ch["vector"]
        if len(vec) != EMBED_DIM:
            raise SystemExit(
                f"{src} chunk {ch['chunk_id']}: vector has {len(vec)} dims, expected {EMBED_DIM}"
            )
        rid += 1
        db.execute(
            "INSERT INTO pdf_chunks_meta(rowid, source_file, chunk_id, page, char_start, "
            "char_end, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rid, src, ch["chunk_id"], ch["page"], ch["char_start"], ch["char_end"], ch["text"]),
        )
        db.execute(
            "INSERT INTO pdf_chunks(rowid, embedding) VALUES (?, ?)",
            (rid, sqlite_vec.serialize_float32(vec)),
        )
        db.execute(
            "INSERT INTO pdf_chunks_fts(rowid, source_file, chunk_id, text) VALUES (?, ?, ?, ?)",
            (rid, src, ch["chunk_id"], ch["text"]),
        )
    return len(payload["chunks"])


def load_all(db, payloads: list[dict]) -> int:
    """Full rebuild: clear the three tables, then load every chunked source. Returns chunks."""
    clear(db)
    return sum(_insert(db, p) for p in payloads)


def update_source(db, payload: dict) -> int:
    """Single-source refresh: replace one source's chunks in place (used by add_pdf, M5)."""
    remove_source(db, payload["source_file"])
    return _insert(db, payload)
