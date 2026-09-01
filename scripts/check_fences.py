#!/usr/bin/env python3
"""Validate a note's exclusion fences before anything embeds or indexes it.

Two fences, two different exclusions:

  ``<!-- second-brain:no-embed:begin/end -->``      out of the vector AND out of keyword search
  ``<!-- second-brain:lexical-only:begin/end -->``  out of the vector, KEPT in keyword search

Both are checked for the same two rules:

1. **Every marker pairs.** An unpaired ``begin`` delimits nothing, so the region a human meant
   to fence is embedded anyway. That is the failure worth catching here, because it is
   **silent**: the note commits, renders correctly, and quietly carries into the index exactly
   what the marker was added to keep out.
2. **Fences never nest, and never interleave.** One layer only, of either kind. Nesting has no
   useful meaning — an inner fence can only repeat or contradict the outer one — and forbidding
   it is what makes validity checkable in a single pass over the markers.

Fenced content still renders in Obsidian either way; the markers are HTML comments.

    python3 scripts/check_fences.py                 # every note under the PARA roots
    python3 scripts/check_fences.py a.md b.md       # only these

Exit 0 when every fence is well formed, 1 otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from note_view import fence_errors  # noqa: E402

PARA_ROOTS = ("projects", "areas", "resources", "archive")


def notes(argv: list[str]) -> list[Path]:
    if argv:
        return [Path(a) if Path(a).is_absolute() else REPO_ROOT / a for a in argv]
    out: list[Path] = []
    for root in PARA_ROOTS:
        base = REPO_ROOT / "vault" / root
        if base.is_dir():
            out += sorted(base.rglob("*.md"))
    return out


def main(argv: list[str]) -> int:
    bad = 0
    for path in notes(argv):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue                     # a deleted note in a commit — nothing to validate
        problems = fence_errors(text)
        if problems:
            bad += 1
            rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
            print(f"second-brain: {rel}", file=sys.stderr)
            for problem in problems:
                print(f"    {problem}", file=sys.stderr)
    if bad:
        print(f"\n{bad} note(s) with malformed fences. Nothing was excluded from the index "
              f"where a marker did not pair — fix the markers and re-commit.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
