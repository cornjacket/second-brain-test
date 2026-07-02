#!/usr/bin/env python3
"""Semantic search over the vault's ``vec0`` cache.

Embeds the query with the SAME backend that produced the note vectors, then runs
a cosine-distance KNN against ``data/brain.db``. Mismatched embedders yield
meaningless results, so the backend is shared via ``scripts/embedder.py``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402
from embedder import embed  # noqa: E402

import sqlite_vec  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "brain.db"


def main() -> int:
    ap = argparse.ArgumentParser(description="Semantic search over the vault.")
    ap.add_argument("query", help="natural-language search query")
    ap.add_argument("-k", "--top-k", type=int, default=5)
    args = ap.parse_args()

    if not DB_PATH.exists():
        raise SystemExit("cache missing; run scripts/hydrate_cache.py first")

    db = connect(DB_PATH)
    qvec = embed(args.query)
    rows = list(db.execute(
        "SELECT source_file, distance FROM notes "
        "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
        (sqlite_vec.serialize_float32(qvec), args.top_k),
    ))
    db.close()

    for source_file, distance in rows:
        print(f"{distance:.4f}  {source_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
