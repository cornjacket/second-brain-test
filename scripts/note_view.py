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
- **strip no-embed blocks** — a region a human fenced off as decorative rather than
  meaningful (an ASCII roadmap, a box-drawn diagram). See ``strip_no_embed``;
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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from marked_block import remove_all_blocks, unpaired_markers  # noqa: E402

# `[[target]]` / `[[target|surface]]` / `![[embed]]` -> the text a human actually reads.
# Non-greedy, and `|`/brackets excluded from the target so adjacent links don't merge.
_WIKILINK = re.compile(r"!?\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")

# The no-embed markers. HTML comments, so Obsidian's reading view hides them entirely
# and the region between them (usually a fenced code block holding the art) renders as
# the normal code block the human wrote — the marker costs the reader nothing. Same
# `second-brain:<feature>:begin/end` shape as the other marked blocks in this brain.
NO_EMBED_BEGIN = "<!-- second-brain:no-embed:begin -->"
NO_EMBED_END = "<!-- second-brain:no-embed:end -->"

# nomic-embed-text's context is 2048 tokens; warn below it so there is room for the
# backend's task prefix and for the estimate to be a little low.
EMBED_TOKEN_BUDGET = 1800


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


def strip_no_embed(body: str) -> str:
    """Remove every ``no-embed`` block — the region a human marked as decorative.

    A note can carry visual, non-semantic content the *reader* wants and the *embedder*
    must never see: an ASCII roadmap, a box-drawn diagram, a hand-aligned table. Two
    distinct harms if it reaches the embed input:

    1. **It dilutes the vector.** Box-drawing runs and column padding carry no meaning,
       but they are still tokens, and they pull the note's single vector away from what
       the prose is actually about.
    2. **It can stop the note embedding at all.** Box-drawing characters are brutally
       token-dense — roughly one token *per character*, against ~4 characters per token
       for prose — so a note well inside the 300-line guideline can still overflow the
       embedder's context and fail outright. Line count is the wrong proxy for the embed
       budget; see ``estimate_tokens``.

    The fix is to **exclude** the region, not to raise the model's context: even where a
    bigger context fits the art, embedding it still degrades retrieval. The block is cut
    from this view only — the file on disk is untouched, so Obsidian, ``get_note`` and a
    human reader all still see the art exactly as written.

    Because this view is also what ``content_hash`` fingerprints, the exclusion is
    consistent by construction: **editing the art re-embeds nothing and flags nothing
    stale**, since the canonical view it produces is byte-identical either way.
    """
    return remove_all_blocks(body, NO_EMBED_BEGIN, NO_EMBED_END)


def has_unpaired_no_embed(text: str) -> bool:
    """True if a ``no-embed`` marker in ``text`` pairs with nothing (a typo'd block).

    Nothing is stripped in that case, so the region the human meant to exclude ends up
    embedded anyway. That is the silent failure worth naming: the note still commits,
    still embeds, still searches — it is simply carrying the art the marker was there to
    keep out. ``embed_staged`` warns on it at commit time, where the fix is one edit away.
    """
    return unpaired_markers(text, NO_EMBED_BEGIN, NO_EMBED_END)


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free estimate of how many tokens ``text`` will embed as.

    The embed budget is measured in **tokens, not lines** — that is the whole reason a
    148-line note with one ASCII diagram can fail to embed while a 290-line prose note
    sails through. Getting a true count would mean shipping the model's tokenizer; this
    approximates it well enough to warn, from the one property that actually separates
    the two cases:

    - ASCII prose tokenizes at roughly **4 characters per token** (a wordpiece average);
    - non-ASCII characters — box-drawing, block elements, arrows, the things ASCII art is
      built from — are rare enough in the vocabulary to cost about **one token each**.

    Deliberately biased to over-count art and under-count prose, because a false warning
    on a diagram is cheap and a missed one is a failed embed.
    """
    ascii_chars = sum(1 for ch in text if ch.isascii())
    return ascii_chars // 4 + (len(text) - ascii_chars)


def canonical_body(text: str) -> str:
    """Return the canonical substance view of a note (see module docstring)."""
    body = _strip_frontmatter(text)
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = strip_no_embed(body)
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
