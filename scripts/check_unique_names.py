#!/usr/bin/env python3
"""Refuse a commit that would put two notes with the same filename in the vault.

Obsidian resolves ``[[wikilinks]]`` **by basename**, not by path. So two notes called
``chapter1.md`` in different folders make every ``[[chapter1]]`` in the vault ambiguous —
Obsidian picks one, silently, and the other becomes unreachable by link. Search results get
the same problem one step later: two rows whose titles are identical and whose paths differ
in a segment nobody reads.

**This used to be true by accident.** Notes sat directly in a PARA root, and a directory
cannot hold two files of the same name — so the filesystem handed over uniqueness *within*
each root, and habit did the rest across them. Nothing decided it and nothing checked it.
Subfolders remove the accident: ``projects/algebra/test-1.md`` and
``projects/geometry/test-1.md`` are different paths, so every existing check passes.

A property that holds because of how things happen to be arranged is not an invariant, and
the loss is quiet — no code ever asserted it, so nothing breaks when it goes. This script is
the mechanism that turns it into a real one.

**Fails the commit rather than warning.** A warning would be the wrong shape here: the damage
is silent link misrouting, discovered much later and attributed to Obsidian rather than to the
commit that caused it. The fix is always trivial and always local — rename one file, at the
moment you are already thinking about it.

Excludes ``vault/templates/`` (devkit-owned machinery, not notes) and the glossary (a separate
controlled-vocabulary namespace, deliberately flat and never nested).

    python3 scripts/check_unique_names.py            # the whole vault
    python3 scripts/check_unique_names.py a.md b.md  # only these, against the whole vault

Exit 0 when unique, 1 when not.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = REPO_ROOT / "vault"
PARA_ROOTS = ("projects", "areas", "resources", "archive")


def notes_by_name(root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """{basename: [repo-relative paths]} for every note under the PARA roots."""
    by_name: dict[str, list[str]] = defaultdict(list)
    for para in PARA_ROOTS:
        base = root / "vault" / para
        if not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            by_name[path.name].append(path.relative_to(root).as_posix())
    return by_name


def duplicates(root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """Only the names held by more than one note, paths sorted for a stable message."""
    return {name: sorted(paths)
            for name, paths in sorted(notes_by_name(root).items()) if len(paths) > 1}


def main(argv: list[str]) -> int:
    dupes = duplicates()
    if argv:
        # Scoped to the notes this commit touches, but compared against the WHOLE vault: a
        # collision is a property of a pair, and only one of the pair is usually in the commit.
        touched = {Path(a).name for a in argv}
        dupes = {n: p for n, p in dupes.items() if n in touched}
    if not dupes:
        return 0

    print("second-brain: duplicate note filenames — Obsidian resolves [[wikilinks]] by NAME, "
          "so these are ambiguous:", file=sys.stderr)
    for name, paths in dupes.items():
        print(f"  {name}", file=sys.stderr)
        for path in paths:
            print(f"      {path}", file=sys.stderr)
    print("Rename one of each pair. A folder-scoped name is the usual fix "
          "(e.g. algebra--chapter1.md rather than chapter1.md).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
