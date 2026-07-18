#!/usr/bin/env python3
"""Verify scenario 05 — search surfaced the right seed notes (human-observed).

Search ranking is non-deterministic (and backend-dependent), so this script asserts nothing
about order or scores. It confirms the seed notes the query should surface actually exist in the
brain, then leaves the ranking judgement to the human.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import brain_from_argv, Checker  # noqa: E402


def main() -> int:
    brain = brain_from_argv()
    c = Checker("05 search")
    # Not asserting the ranking — only that the expected targets exist to be found.
    resources = brain / "vault" / "resources"
    have = {p.stem for p in resources.glob("*.md")} if resources.is_dir() else set()
    c.check("sqlite-vec" in have or "embeddings" in have,
            "the vector-database seed notes (sqlite-vec / embeddings) exist to be surfaced")
    c.manual("the top hits included sqlite-vec and/or embeddings (right notes, ranking not asserted)")
    return c.done()


if __name__ == "__main__":
    raise SystemExit(main())
