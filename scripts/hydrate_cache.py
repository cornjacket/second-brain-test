#!/usr/bin/env python3
"""Hydrate the local SQLite ``vec0`` cache from ``.embed.json`` sidecars.

Bulk-scans every sidecar in the vault and rebuilds ``data/brain.db``, the
sqlite-vec virtual table the AI frontends query. The cache is derived state —
safe to rebuild at any time.

The rebuild happens **in place, in a single transaction** (``DELETE FROM notes``
then re-INSERT every row, committed once) rather than by deleting the DB file. A
concurrent reader — notably the long-lived MCP server holding a connection open —
keeps seeing the *old* rows until the commit, then sees the full new set
atomically (WAL, OQ-5 layer 2). There is never a window where the DB is missing or
half-built: if any sidecar is bad the transaction rolls back and the old rows
survive.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402
from embedder import EMBED_DIM  # noqa: E402
from note_view import canonical_body, frontmatter_tags  # noqa: E402
from update_cache import FTS_DDL, TABLE_DDL  # noqa: E402  (shared cache schema)

import sqlite_vec  # noqa: E402

# Optional PDF-chunk loading (task #7). This module is NOT emitted into a brain until
# M6, so in a generated brain the import fails, chunk sidecars are skipped, and the note
# path is byte-identical. See docs/pdf-ingestion.md §4.
try:
    import pdf_cache  # noqa: E402
except ImportError:
    pdf_cache = None

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = REPO_ROOT / "vault"
CACHE_DIR = REPO_ROOT / "data"
DB_PATH = CACHE_DIR / "brain.db"


def find_sidecars() -> list[Path]:
    return sorted(VAULT_DIR.rglob(".*.embed.json"))


def main() -> int:
    CACHE_DIR.mkdir(exist_ok=True)

    db = connect(DB_PATH)
    db.execute(TABLE_DDL)  # shared schema; IF NOT EXISTS — the table is never dropped
    db.execute(FTS_DDL)    # lexical companion table (hybrid search)

    # Classify sidecars: a note carries a single "vector"; a chunked source (a PDF, task
    # #7) carries a "chunks" list. Without pdf_cache (a brain, until M6) the chunk list is
    # empty, so nothing below the note loop runs and the note path is byte-identical.
    note_payloads, chunk_payloads = [], []
    for sidecar in find_sidecars():
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        if pdf_cache is not None and "chunks" in payload:
            chunk_payloads.append(payload)
        else:
            note_payloads.append(payload)
    if pdf_cache is not None:
        pdf_cache.ensure_tables(db)  # additive; DDL outside the transaction like the note tables

    # Rebuild in one transaction on the *existing* tables so a concurrent reader (WAL)
    # keeps seeing the old rows until COMMIT, then the new set atomically — no
    # unlink()/empty-DB window. Explicit BEGIN/COMMIT (not the wrapper's commit()):
    # apsw autocommits each statement otherwise, which would expose the empty table
    # mid-rebuild. On any error we ROLLBACK, so the previous good rows survive.
    db.execute("BEGIN")
    try:
        db.execute("DELETE FROM notes")
        db.execute("DELETE FROM notes_fts")
        count = 0
        for payload in note_payloads:
            vec = payload["vector"]
            if len(vec) != EMBED_DIM:
                raise SystemExit(
                    f"{payload['source_file']}: vector has {len(vec)} dims, expected {EMBED_DIM}"
                )
            src = payload["source_file"]
            db.execute(
                "INSERT INTO notes(source_file, embedding) VALUES (?, ?)",
                (src, sqlite_vec.serialize_float32(vec)),
            )
            # Lexical row from the vault note (source of truth); skip if the note file is
            # gone (orphan sidecar) — the vector still indexes.
            note_path = REPO_ROOT / src
            if note_path.exists():
                note_text = note_path.read_text(encoding="utf-8")
                db.execute(
                    "INSERT INTO notes_fts(source_file, body, tags) VALUES (?, ?, ?)",
                    (src, canonical_body(note_text), " ".join(frontmatter_tags(note_text))),
                )
            count += 1
        chunk_count = pdf_cache.load_all(db, chunk_payloads) if pdf_cache is not None else 0
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")  # keep the old rows; never leave a half-built cache
        db.close()
        raise

    db.close()
    tail = f" + {chunk_count} pdf chunk(s)" if pdf_cache is not None and chunk_count else ""
    print(f"hydrated {count} note(s){tail} -> {DB_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
