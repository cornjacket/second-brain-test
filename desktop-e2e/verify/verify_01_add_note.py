#!/usr/bin/env python3
"""Verify scenario 01 — add_note created a committed note with the right tags."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import brain_from_argv, load, find_note_by_title, is_tracked, Checker  # noqa: E402


def main() -> int:
    brain = brain_from_argv()
    note_view = load(brain, "note_view")
    c = Checker("01 add_note")

    note = find_note_by_title(brain, "resources", "Planning agents")
    if not c.check(note is not None, "note 'Planning agents' exists under vault/resources/"):
        return c.done()

    tags = note_view.frontmatter_tags(note.read_text(encoding="utf-8"))
    c.check("ai-agents" in tags and "planning" in tags,
            f"frontmatter tags include ai-agents + planning (got {tags})")
    c.check(is_tracked(brain, note), "note is committed (git-tracked, not just written)")
    c.manual("the reply said the note was created (e.g. 'created resources/planning-agents.md')")
    return c.done()


if __name__ == "__main__":
    raise SystemExit(main())
