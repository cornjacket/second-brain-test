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
from update_cache import TABLE_DDL  # noqa: E402  (shared cache schema)

import sqlite_vec  # noqa: E402

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

    # Rebuild in one transaction on the *existing* table so a concurrent reader (WAL)
    # keeps seeing the old rows until COMMIT, then the new set atomically — no
    # unlink()/empty-DB window. Explicit BEGIN/COMMIT (not the wrapper's commit()):
    # apsw autocommits each statement otherwise, which would expose the empty table
    # mid-rebuild. On any error we ROLLBACK, so the previous good rows survive.
    db.execute("BEGIN")
    try:
        db.execute("DELETE FROM notes")
        count = 0
        for sidecar in find_sidecars():
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            vec = payload["vector"]
            if len(vec) != EMBED_DIM:
                raise SystemExit(
                    f"{sidecar}: vector has {len(vec)} dims, expected {EMBED_DIM}"
                )
            db.execute(
                "INSERT INTO notes(source_file, embedding) VALUES (?, ?)",
                (payload["source_file"], sqlite_vec.serialize_float32(vec)),
            )
            count += 1
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")  # keep the old rows; never leave a half-built cache
        db.close()
        raise

    db.close()
    print(f"hydrated {count} note(s) -> {DB_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
