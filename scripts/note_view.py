#!/usr/bin/env python3
"""Canonical *substance* view of a note — the one input the embedder sees.

The core invariant of auto-linking (docs/auto-linking.md §1): **the embedding is
computed over a note's substance — its body — never over the metadata about it.**
Frontmatter is metadata (tags, and later the auto-derived ``related_auto:`` /
``content_hash`` blocks); embedding it would let the system's own output feed back
into the vector. Stripping frontmatter from the embed input breaks that loop at
the source.

``canonical_body`` also pins the byte-level details so the view is **identical on
any machine** (§4.1) — a prerequisite for the cross-machine-stable change hash
that will gate re-embedding:

- take the body only — everything after a leading ``---`` … ``---`` frontmatter
  fence (no frontmatter → the whole text is the body);
- normalize line endings to ``\n`` so a CRLF checkout matches an LF one;
- drop blank lines hugging the fences and pin a single trailing ``\n`` (an empty
  body → ``""``), so incidental editor whitespace doesn't move the view.
"""
from __future__ import annotations


def _strip_frontmatter(text: str) -> str:
    """Return ``text`` with a leading YAML frontmatter block removed.

    A frontmatter block is a first line of exactly ``---`` up to the next line of
    exactly ``---``. Anything else (no leading fence, or no closing fence) is
    treated as having no frontmatter — the whole text is the body.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return "".join(lines[i + 1:])
    return text  # unterminated fence — not real frontmatter


def canonical_body(text: str) -> str:
    """Return the canonical substance view of a note (see module docstring)."""
    body = _strip_frontmatter(text)
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = body.strip("\n")
    return body + "\n" if body else ""
