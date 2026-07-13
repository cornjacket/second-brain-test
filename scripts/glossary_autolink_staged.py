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
from features import glossary_autolink  # noqa: E402
import glossary_scan  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = "vault"
PARA_ROOTS = ("projects", "areas", "resources", "archive")


def staged_para_notes() -> list[str]:
    """Staged (added/copied/modified) Markdown notes under vault/<para-root>/…."""
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    notes = []
    for line in out.splitlines():
        parts = line.split("/")
        if (line.endswith(".md") and len(parts) >= 3
                and parts[0] == VAULT_DIR and parts[1] in PARA_ROOTS):
            notes.append(line)
    return notes


def main() -> int:
    if not glossary_autolink():
        return 0  # opt-in; default off → the commit path is unchanged
    terms = glossary_scan.glossary_terms()
    if not terms:
        return 0
    for note in staged_para_notes():
        linked = glossary_scan.link_note_file(REPO_ROOT / note, terms)
        if not linked:
            continue
        # Re-stage so the inserted links land in THIS commit (and embed with the note).
        subprocess.run(["git", "add", "--", note], cwd=REPO_ROOT, check=True)
        for surface, slug in linked:
            print(f"  glossary-link  {note}: '{surface}' -> [[{slug}]]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
