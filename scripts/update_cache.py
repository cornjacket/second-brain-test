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
from features import encryption  # noqa: E402  (which mode this brain is in)
from note_view import (  # noqa: E402
    canonical_body, embed_excluded, frontmatter_tags, lexical_body,
)

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


def _excluded(rel: str) -> bool:
    """Does this path carry ``embed: false``? A deleted file cannot, so a missing file is False."""
    path = REPO_ROOT / rel
    try:
        return embed_excluded(path.read_text(encoding="utf-8"))
    except OSError:
        return False


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
    # lexical_body, NOT canonical_body: a `lexical-only` region is kept out of the vector but
    # belongs here, which is the whole point of the second fence. hydrate_cache writes the same
    # table and must use the same projection — the two disagreeing is how art or IDs end up in
    # one index and not the other depending on which path last touched the row.
    db.execute("INSERT INTO notes_fts(source_file, body, tags) VALUES (?, ?, ?)",
               (note, lexical_body(text), " ".join(frontmatter_tags(text))))


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


class BlindError(RuntimeError):
    """The encrypted commit cannot be read — say so instead of reporting "nothing changed"."""


def _touched_blobs(ref: str) -> set[str]:
    """Blob file names this commit added or modified under ``enc/``."""
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff-tree", "--no-commit-id", "-r", "-M",
         "--name-status", ref],
        capture_output=True, text=True, check=True,
    ).stdout
    names: set[str] = set()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        status = parts[0][:1]
        if status == "D":
            continue                      # a deleted blob's path is unrecoverable — see below
        # A rename line is `R<score>\told\tnew`; the destination is the last field.
        rel = parts[-1]
        if rel.startswith("enc/") and rel.endswith(".md.enc"):
            names.add(Path(rel).name)
    return names


def encrypted_changes(ref: str) -> list[str]:
    """Notes to upsert on an **encrypted** brain, where the commit holds no note at all.

    With encryption on, a commit contains ``enc/<opaque>.md.enc`` and nothing else — the
    vault is git-ignored. Asked what PARA notes changed, git answers *none*, truthfully and
    uselessly, and the cache silently never updates: the note is embedded and committed but
    not searchable until someone runs ``hydrate_cache`` by hand (task #48). This is the same
    shape as the four selectors task #42 had to fix — **a component asking git a question a
    git-ignored vault cannot answer, and getting a plausible empty answer rather than an
    error.**

    Resolved **forwards**, not backwards. A blob's name is a keyed HMAC of the note's path,
    so the path cannot be recovered from the name — but every *live* note's name can simply
    be computed, and the intersection with the blobs this commit touched is the answer. That
    needs no decryption, and it is the same trick ``encrypt_vault.orphan_blobs`` uses.

    Deletions are deliberately **not** handled here. A deleted note's blob name cannot be
    mapped back to a path (the note is gone, so there is nothing to compute from), and
    decrypting the old blob out of git history to recover it would be a lot of machinery for
    a case ``prune_stale_rows`` already covers by asking a cheaper question: which cache rows
    have no note on disk?

    Raises ``BlindError`` if the keys cannot be derived. That distinction matters — returning
    ``[]`` here would be indistinguishable from "this commit changed nothing", which is the
    exact failure mode this function exists to remove.
    """
    try:
        import encrypt_vault as ev
        import passphrase as pp
        keys = ev.keys_from_keyfile(ev.load_keyfile(REPO_ROOT / "enc" / "keyfile.json"),
                                    pp.resolve(REPO_ROOT))
    except Exception as exc:                      # missing dep, no passphrase, bad keyfile
        raise BlindError(str(exc)) from exc

    touched = _touched_blobs(ref)
    if not touched:
        return []
    live = {}
    for root in PARA_ROOTS:
        base = REPO_ROOT / "vault" / root
        if base.is_dir():
            for path in base.rglob("*.md"):
                rel = path.relative_to(REPO_ROOT).as_posix()
                live[ev.blob_name(keys, rel)] = rel
    return sorted(rel for name, rel in live.items() if name in touched)


def prune_stale_rows(db) -> list[str]:
    """Cache rows whose note is no longer on disk. The deletion half, without any key.

    Works in both modes and needs neither git nor the passphrase: a row naming a file that
    does not exist can only be a note that was deleted or moved, and either way the row has
    to go or search will answer with a dead path.
    """
    try:
        rows = [r[0] for r in db.execute("SELECT source_file FROM notes")]
    except Exception:
        return []
    return sorted(rel for rel in rows if not (REPO_ROOT / rel).exists())


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
    # A commit that stops TRACKING a note has not deleted it. The two look identical to
    # `diff-tree` — both are `D` — and treating them the same is destructive here, because
    # `delete()` unlinks the sidecar: the vector is gone and the note must be re-embedded.
    #
    # This is not hypothetical. Enabling encryption untracks the whole vault in one commit
    # (`git rm --cached`), which reads as "every note deleted" and wiped every sidecar in
    # the brain — found by running the migration end-to-end, not by a test.
    #
    # The working tree is the authority on whether a note exists, in either mode. Checking
    # it also fixes the plaintext case where someone untracks a note by hand and keeps it.
    to_delete = [n for n in to_delete if not (REPO_ROOT / n).exists()]

    # A file marked `embed: false` is Markdown under a PARA root that is not a note, so it has
    # no sidecar and `upsert()` would abort the whole post-commit run on it. It moves to the
    # delete side rather than merely being dropped: adding the key to an already-indexed note
    # must *retract* the row, or the file keeps answering searches while its frontmatter says
    # it is not a note — an exclusion that appears to work and does not.
    excluded = [n for n in to_upsert if _excluded(n)]
    to_upsert = [n for n in to_upsert if n not in set(excluded)]
    to_delete += excluded
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
        # Which question to ask depends on the mode, because the two commits look nothing
        # alike: a plaintext commit contains the notes, an encrypted one contains only
        # opaque blobs. Asking git the plaintext question on an encrypted brain returns a
        # truthful, useless "nothing changed" — the #48 bug.
        blind = ""
        if encryption():
            try:
                to_upsert = encrypted_changes(args.from_commit)
            except BlindError as exc:
                to_upsert, blind = [], str(exc)
            to_delete = []
        else:
            to_upsert, to_delete = changed_in_commit(args.from_commit)

        # Rows for notes that are no longer on disk, in either mode. On a plaintext brain
        # changed_in_commit has usually named them already; this catches what it cannot see
        # — an encrypted deletion, or a note removed outside a commit.
        stale = [n for n in prune_stale_rows(db) if n not in set(to_delete)]
        to_delete = list(to_delete) + stale

        for note in to_delete:
            delete(db, note)
        for note in to_upsert:
            upsert(db, note)

        if blind:
            # Never exit 0 on a cache we could not update. The post-commit hook cannot fail
            # the commit, so this message is the only signal the user gets — and silence here
            # is precisely the failure being fixed.
            print(f"update_cache: encryption is on but the keys could not be derived "
                  f"({blind}) — this commit's notes are NOT in the search cache. Run "
                  f"'python3 scripts/doctor.py --repair'.", file=sys.stderr)
            db.commit()
            db.close()
            return 1
        if not (to_upsert or to_delete):
            print(f"update_cache: no PARA-note changes in {args.from_commit}")

    db.commit()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
