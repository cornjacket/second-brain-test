#!/usr/bin/env python3
"""Hydrate the local SQLite ``vec0`` cache from ``.embed.json`` sidecars.

Bulk-scans every sidecar in the vault and **wipes-and-rebuilds** ``data/brain.db``,
the sqlite-vec virtual table the AI frontends query. The cache is derived state —
safe to delete and rebuild at any time.
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
    if DB_PATH.exists():
        DB_PATH.unlink()  # derived; rebuild from scratch each run

    db = connect(DB_PATH)
    db.execute(TABLE_DDL)  # shared schema (fresh file after unlink → table is created)

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

    db.commit()
    db.close()
    print(f"hydrated {count} note(s) -> {DB_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
