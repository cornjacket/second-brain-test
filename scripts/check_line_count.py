#!/usr/bin/env python3
"""Warn when a Markdown note exceeds the non-empty line threshold (Task 0002).

Counts **non-empty** lines (blank / whitespace-only lines don't count) in each
given Markdown file and prints a single emoji-led nudge to segment any file over
``THRESHOLD``. Excludes ``README.md`` and everything under ``tasks/``. Pure
stdlib, deterministic, zero model tokens.

The guard **never modifies** the offending file — it only surfaces a nudge; the
user drives any restructuring.

**This is a readability nudge, not an embed-budget check**, and the two are easy to
confuse because both fire on "the file is big". They measure different things and
neither substitutes for the other: the embed budget is counted in *tokens*, over
``canonical_body`` (so fenced regions cost nothing), and is enforced per-note by
``embed_staged.py`` and audited across the vault by ``doctor.py``. Line count is about
whether a *human* can still find their way around the file, so it counts what a human
scrolls past — the whole file, fences included.

Files carrying ``embed: false`` are skipped. They are deliberately not notes — a
textbook transcription or a paste buffer is *supposed* to be long, splitting it would
serve nothing, and the nudge was pure noise on every commit that touched one.

Exit status: ``1`` if any in-scope file is over threshold, else ``0``. The
pre-commit hook calls this in warn-only mode (ignoring the exit code) so it never
blocks a commit; the non-zero exit is for standalone / CI use.

Usage:
    python3 scripts/check_line_count.py <file.md> [<file.md> ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from note_view import embed_excluded  # noqa: E402

THRESHOLD = 300


def is_excluded(path: Path) -> bool:
    """README.md (any dir) and anything under a ``tasks/`` dir are never checked."""
    return path.name == "README.md" or "tasks" in path.parts


def non_empty_line_count(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                count += 1
    return count


def check(path_str: str) -> bool:
    """Return True (and print a nudge) if ``path_str`` violates the threshold."""
    path = Path(path_str)
    if path.suffix != ".md" or is_excluded(path) or not path.is_file():
        return False
    try:
        if embed_excluded(path.read_text(encoding="utf-8")):
            return False
    except OSError:
        return False
    count = non_empty_line_count(path)
    if count > THRESHOLD:
        print(
            f"📏 {path_str}: {count} non-empty lines (> {THRESHOLD}) — "
            "consider splitting this note into two or more files."
        )
        return True
    return False


def main(argv: list[str]) -> int:
    violations = sum(1 for arg in argv if check(arg))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
