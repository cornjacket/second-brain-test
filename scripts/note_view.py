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
- **strip wikilink markup** — ``[[term]]`` → ``term``, ``[[slug|surface]]`` → ``surface``.
  Markup is not substance: the brackets mean nothing a reader doesn't already get from the
  words, so they must not move the vector. This is also what makes the content hash able to
  distinguish *the prose was edited* from *a link was inserted* — auto-linking a term across
  the vault then costs **zero** re-embeds, because the canonical view does not change at all;
- normalize line endings to ``\n`` so a CRLF checkout matches an LF one;
- drop blank lines hugging the fences and pin a single trailing ``\n`` (an empty
  body → ``""``), so incidental editor whitespace doesn't move the view.
"""
from __future__ import annotations

import hashlib
import re

# `[[target]]` / `[[target|surface]]` / `![[embed]]` -> the text a human actually reads.
# Non-greedy, and `|`/brackets excluded from the target so adjacent links don't merge.
_WIKILINK = re.compile(r"!?\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")


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


def strip_wikilinks(body: str) -> str:
    """`[[term]]` -> `term`, `[[slug|surface]]` -> `surface`. Link *markup* is not substance.

    Two reasons this belongs in the canonical view, not in a caller:

    1. **A link carries no meaning the prose doesn't already carry.** `[[ablation]]` and
       `ablation` say the same thing, so the brackets would shift the vector for nothing.
    2. **It is what lets the content hash tell an *edit* from a *link insertion*.** Auto-linking
       a term across the vault rewrites bodies; without this, every one of those notes re-embeds
       for a change that means nothing. With it, the canonical view is byte-identical, the hash
       matches, and the existing no-op gate in ``embed_staged`` skips the embed entirely — while
       a genuine edit to the prose still changes the hash and still re-embeds.

    It also closes the module's own invariant properly: the embedding must never be fed the
    system's *own output*, and an auto-inserted wikilink is exactly that. The loop was shut for
    frontmatter (``related_auto:``) and left open through the body.
    """
    return _WIKILINK.sub(lambda m: (m.group(2) or m.group(1)).strip(), body)


def canonical_body(text: str) -> str:
    """Return the canonical substance view of a note (see module docstring)."""
    body = _strip_frontmatter(text)
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = strip_wikilinks(body)
    body = body.strip("\n")
    return body + "\n" if body else ""


def frontmatter_tags(text: str) -> list[str]:
    """Return the note's frontmatter ``tags:`` as a list (``[]`` if absent).

    Used to fold a note's tags into the **lexical** (FTS5) index alongside its body — the
    complement of ``canonical_body`` (which drops frontmatter for the *embedding*). A tiny,
    tolerant parser (no YAML dependency) covering the flat shapes the vault uses:

    - inline list — ``tags: [a, b, c]``
    - block list — ``tags:`` then ``  - a`` lines
    - scalar — ``tags: a``
    """
    lines = text.splitlines()
    if not lines or lines[0].rstrip("\r\n") != "---":
        return []
    fm: list[str] = []
    for line in lines[1:]:
        if line.rstrip("\r\n") == "---":
            break
        fm.append(line)
    for i, line in enumerate(fm):
        stripped = line.strip()
        if not stripped.startswith("tags:"):
            continue
        rest = stripped[len("tags:"):].strip()
        if rest.startswith("[") and rest.endswith("]"):
            return [t.strip().strip("'\"") for t in rest[1:-1].split(",") if t.strip()]
        if rest:
            return [rest.strip("'\"")]
        tags = []
        for follow in fm[i + 1:]:
            s = follow.strip()
            if s.startswith("- "):
                tags.append(s[2:].strip().strip("'\""))
            elif s:
                break  # next frontmatter key ends the block list
        return tags
    return []


def content_hash(text: str) -> str:
    """A byte-stable fingerprint of a note's substance — its canonical body.

    Returns ``sha256:<hex>``. Unlike the neural embedding vector (which differs run to
    run and machine to machine), this hash is **identical everywhere** for the same body,
    so it answers one question cheaply: *did the substance change since we last embedded?*
    That lets the embed step skip notes whose body is unchanged — no wasted re-embed, and
    no churn from a frontmatter-only edit like an auto-linker adding ``related_auto:``
    (frontmatter is excluded from the canonical body). See docs/auto-linking.md §4.
    """
    digest = hashlib.sha256(canonical_body(text).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
