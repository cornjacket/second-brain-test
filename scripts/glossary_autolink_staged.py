#!/usr/bin/env python3
"""Pre-commit helper: link known glossary terms in staged notes (opt-in, task #19).

When ``glossary_autolink`` is enabled (``config/features.toml`` / the
``SECOND_BRAIN_GLOSSARY_AUTOLINK`` env var — off by default), this links the first unlinked
occurrence of each glossary term in every **staged** PARA note, then re-stages the note so the
links land in the same commit and the note embeds *with* them. It runs **before**
``embed_staged.py`` in the pre-commit hook.

Contained by design: it only ever touches the notes you are already committing (never a
whole-vault sweep — that stays in ``glossary_scan.py`` / ``glossary_new.py``), so a commit's
blast radius is just its own staged notes. Idempotent — an already-linked term is skipped, so
re-committing a note is a no-op. Silent and a no-op when the toggle is off, so the default
commit path is unchanged.

Pure stdlib; reuses the ``glossary_scan`` link engine so linking is identical everywhere.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import encryption, glossary_autolink  # noqa: E402
from note_selection import notes_for_commit  # noqa: E402
import glossary_scan  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = "vault"
PARA_ROOTS = ("projects", "areas", "resources", "archive")


def main() -> int:
    if not glossary_autolink():
        return 0  # opt-in; default off → the commit path is unchanged
    terms = glossary_scan.glossary_terms()
    if not terms:
        return 0
    # From note_selection, NOT `git diff --cached`: an encrypted brain git-ignores the
    # vault, so git stages no note and this loop would run zero times, silently.
    for note in notes_for_commit():
        linked = glossary_scan.link_note_file(REPO_ROOT / note, terms)
        if not linked:
            continue
        # Re-stage so the inserted links land in THIS commit (and embed with the note).
        # With encryption on the note itself is git-ignored — the blob carrying it is
        # staged by the encrypt step instead, so re-staging here would fail on an
        # ignored pathspec. The edit still reaches the commit, via the blob.
        if not encryption():
            subprocess.run(["git", "add", "--", note], cwd=REPO_ROOT, check=True)
        for surface, slug in linked:
            print(f"  glossary-link  {note}: '{surface}' -> [[{slug}]]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
