#!/usr/bin/env python3
"""Verify scenario 03 — add_glossary_term defined a committed term with its alias."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import brain_from_argv, load, is_tracked, Checker  # noqa: E402


def main() -> int:
    brain = brain_from_argv()
    glossary_new = load(brain, "glossary_new")
    c = Checker("03 glossary")

    slug = glossary_new.slugify("ablation study")
    path = brain / "vault" / "glossary" / f"{slug}.md"
    if not c.check(path.exists(), f"glossary note {slug}.md exists under vault/glossary/"):
        return c.done()

    text = path.read_text(encoding="utf-8")
    c.check("contribution" in text.lower(), "the definition line is present")
    c.check("ablation" in text, "the alias 'ablation' is present")
    c.check(is_tracked(brain, path), "glossary note is committed (git-tracked)")
    c.manual("the reply said the term was defined (e.g. 'defined ablation-study in the glossary')")
    return c.done()


if __name__ == "__main__":
    raise SystemExit(main())
