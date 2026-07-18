#!/usr/bin/env python3
"""Verify scenario 02 — the near-miss note landed, and the brain's rule WOULD warn (task #32).

Deterministic: the note exists with the near-miss tag, and the brain's own tag_hygiene maps
`ai-agent` -> `ai-agents` against its vocabulary (proving the feature is correctly wired in this
brain). The one thing only a human can confirm — that the `TAG HINT` actually appeared in
Desktop's reply — is a MANUAL item; that round-trip is the whole reason this suite exists.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import brain_from_argv, load, find_note_by_title, Checker  # noqa: E402


def main() -> int:
    brain = brain_from_argv()
    note_view = load(brain, "note_view")
    th = load(brain, "tag_hygiene")
    c = Checker("02 near-miss")

    note = find_note_by_title(brain, "resources", "Reactive agents")
    if c.check(note is not None, "note 'Reactive agents' exists under vault/resources/"):
        tags = note_view.frontmatter_tags(note.read_text(encoding="utf-8"))
        c.check("ai-agent" in tags, f"note carries the near-miss tag ai-agent (got {tags})")

    # Independent proof the brain's data + rule would produce the warning: the same near-miss
    # check the write path runs (vocabulary minus near-universal tags).
    vault = brain / "vault"
    carriers, total = th.scan_notes(vault), th.note_total(vault)
    vocab = {t for t, ns in carriers.items()
             if not (total and len(ns) / total >= th.NEAR_UNIVERSAL)}
    hit = th.near_miss_of("ai-agent", vocab)
    c.check(hit == "ai-agents",
            f"brain's near-miss rule maps ai-agent -> ai-agents (got {hit!r})")

    c.manual("a line starting 'TAG HINT:' named ai-agents — the warning survived the Desktop "
             "round-trip (this is what G6's Python client cannot show)")
    return c.done()


if __name__ == "__main__":
    raise SystemExit(main())
