#!/usr/bin/env python3
"""Incrementally update the search cache — **one note at a time, no teardown**.

``hydrate_cache.py`` deletes and rebuilds ``data/brain.db`` wholesale, so during a
rebuild a concurrent query hits a missing/empty DB, and it costs O(all notes) for a
single-note change. This touches only the affected row(s) on the **existing** table
(created on demand, never torn down), so the brain stays query-able throughout.

Operations:
  ``--upsert <note.md> …``   DELETE+INSERT each note's row from its ``.embed.json``
                             sidecar (an in-place update; safe to run repeatedly).
  ``--delete <note.md> …``   Remove each note's row and its orphan (derived,
                             git-ignored) sidecar.
  ``--from-commit [REF]``     Apply the PARA-note changes in REF (default ``HEAD``):
                             upsert added/modified/renamed-in notes, delete removed
                             ones. This is what the **post-commit** hook runs.

    python3 scripts/update_cache.py --upsert vault/areas/foo.md
    python3 scripts/update_cache.py --delete vault/areas/foo.md
    python3 scripts/update_cache.py --from-commit HEAD

For a full/bulk rebuild (e.g. after ``embed_vault.py``), use ``hydrate_cache.py``.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402
from embedder import EMBED_DIM  # noqa: E402
from note_view import canonical_body, frontmatter_tags  # noqa: E402

import sqlite_vec  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "brain.db"
VAULT = "vault"
PARA_ROOTS = ("projects", "areas", "resources", "archive")

# The single source of truth for the cache schema (shared with hydrate_cache.py).
# IF NOT EXISTS so incremental ops work on a live DB without ever dropping it.
TABLE_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS notes USING vec0("
    f"source_file TEXT PRIMARY KEY, embedding FLOAT[{EMBED_DIM}] distance_metric=cosine)"
)
# The lexical companion to the vec0 table: a BM25-ranked FTS5 index over each note's
# body + tags, hydrated by the SAME flow (hooks/hydrate) into the SAME data/brain.db, so
# hybrid search (search_vault) fuses the two. source_file is UNINDEXED — stored so we can
# return/DELETE by it, not tokenized. See docs/retrieval-quality.md §2.
FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5("
    "source_file UNINDEXED, body, tags)"
)


def sidecar_for(note: str) -> Path:
    p = Path(note)
    return REPO_ROOT / p.parent / f".{p.stem}.embed.json"


def is_para_note(rel: str) -> bool:
    parts = rel.split("/")
    return (rel.endswith(".md") and len(parts) >= 3
            and parts[0] == VAULT and parts[1] in PARA_ROOTS)


def index_fts(db, note: str) -> None:
    """(Re)index one note's lexical row in notes_fts from its Markdown body + tags.

    Read from the vault note (the source of truth), not the sidecar — the sidecar is a pure
    derived-embedding artifact and carries no body text. If the note file is missing (a rare
    orphan), the vector row still stands; there is simply no lexical row to add.
    """
    db.execute("DELETE FROM notes_fts WHERE source_file = ?", (note,))
    path = REPO_ROOT / note
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    db.execute("INSERT INTO notes_fts(source_file, body, tags) VALUES (?, ?, ?)",
               (note, canonical_body(text), " ".join(frontmatter_tags(text))))


def upsert(db, note: str) -> None:
    """Insert-or-replace one note's vector (from its sidecar) and lexical row (no teardown)."""
    sidecar = sidecar_for(note)
    if not sidecar.exists():
        raise SystemExit(
            f"update_cache: no sidecar for {note} ({sidecar.name}) — embed it first"
        )
    vec = json.loads(sidecar.read_text(encoding="utf-8"))["vector"]
    if len(vec) != EMBED_DIM:
        raise SystemExit(f"update_cache: {sidecar} has {len(vec)} dims, expected {EMBED_DIM}")
    # DELETE+INSERT is the vec0 upsert; only this one row is ever affected.
    db.execute("DELETE FROM notes WHERE source_file = ?", (note,))
    db.execute("INSERT INTO notes(source_file, embedding) VALUES (?, ?)",
               (note, sqlite_vec.serialize_float32(vec)))
    index_fts(db, note)  # keep the lexical index in lockstep with the vector
    print(f"  upsert {note}")


def delete(db, note: str) -> None:
    """Remove one note's rows (vector + lexical) and its orphan (git-ignored) sidecar."""
    db.execute("DELETE FROM notes WHERE source_file = ?", (note,))
    db.execute("DELETE FROM notes_fts WHERE source_file = ?", (note,))
    sidecar = sidecar_for(note)
    if sidecar.exists():
        sidecar.unlink()
    print(f"  delete {note}")


def changed_in_commit(ref: str) -> tuple[list[str], list[str]]:
    """(to_upsert, to_delete) PARA notes changed in REF vs its parent."""
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff-tree", "--no-commit-id", "-r", "-M",
         "--name-status", ref],
        capture_output=True, text=True, check=True,
    ).stdout
    to_upsert: list[str] = []
    to_delete: list[str] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:      # rename: old -> new
            if is_para_note(parts[1]):
                to_delete.append(parts[1])
            if is_para_note(parts[2]):
                to_upsert.append(parts[2])
        elif status[:1] in ("A", "M", "C") and len(parts) >= 2:
            if is_para_note(parts[1]):
                to_upsert.append(parts[1])
        elif status[:1] == "D" and len(parts) >= 2:
            if is_para_note(parts[1]):
                to_delete.append(parts[1])
    return to_upsert, to_delete


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Incrementally update the search cache.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--upsert", nargs="+", metavar="NOTE")
    group.add_argument("--delete", nargs="+", metavar="NOTE")
    group.add_argument("--from-commit", nargs="?", const="HEAD", metavar="REF")
    args = ap.parse_args(argv)

    DB_PATH.parent.mkdir(exist_ok=True)
    db = connect(DB_PATH)
    db.execute(TABLE_DDL)  # ensure the schema exists; never drops the table
    db.execute(FTS_DDL)    # lexical companion table (hybrid search)

    if args.upsert:
        for note in args.upsert:
            upsert(db, note)
    elif args.delete:
        for note in args.delete:
            delete(db, note)
    else:
        to_upsert, to_delete = changed_in_commit(args.from_commit)
        for note in to_delete:
            delete(db, note)
        for note in to_upsert:
            upsert(db, note)
        if not (to_upsert or to_delete):
            print(f"update_cache: no PARA-note changes in {args.from_commit}")

    db.commit()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
