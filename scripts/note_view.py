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

# The second fence. A `lexical-only` region leaves the **vector** (and the content hash, so
# editing it re-embeds nothing) but stays in the **lexical** index.
#
# `no-embed` is for content that carries no meaning at all — ASCII art, a box-drawn diagram —
# so keeping it out of keyword search too is right. Reference data is the opposite case: an
# ID, a phone number, an account name is a *token*, not a meaning. It is useless to an
# embedding, which is about similarity, and it is exactly what BM25 is good at. Same for a
# volatile checklist: its state changes constantly and carries no semantic change, but "TB
# test" is still a phrase worth finding.
#
# Named for the retrieval outcome — "findable by exact words, not by meaning" — rather than
# for the mechanism. `no-vector` was the alternative and reads too much like `no-embed`.
LEXICAL_ONLY_BEGIN = "<!-- second-brain:lexical-only:begin -->"
LEXICAL_ONLY_END = "<!-- second-brain:lexical-only:end -->"

# Both fences, for the validator. Order matters nowhere except in these messages.
FENCES = ((NO_EMBED_BEGIN, NO_EMBED_END, "no-embed"),
          (LEXICAL_ONLY_BEGIN, LEXICAL_ONLY_END, "lexical-only"))

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


# A link whose target names a file that is not a note: `![alt](tile.svg)`, `![[tile.svg]]`,
# `[the data](rows.csv)`. The extension test is what separates an ASSET reference from a link
# to another note — `.md` targets and URLs are left to the ordinary wikilink handling.
_MD_ASSET_LINK = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)\)")
_WIKI_ASSET_LINK = re.compile(r"!?\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")


def _is_asset_target(target: str) -> bool:
    """Does this link target name a non-Markdown file living in the vault?"""
    if "://" in target or target.startswith("#"):
        return False                       # a URL or an in-note anchor, not an asset
    name = target.split("/")[-1].split("#")[0]
    stem, dot, ext = name.rpartition(".")
    return bool(dot and stem and ext.isalnum() and ext.lower() != "md")


def strip_asset_links(body: str) -> str:
    """Drop asset *filenames* from the embed input, keeping any human description.

    A note displays its material with `![a tiling of the plane](tile-pattern.svg)`. The
    filename is a **path**, not meaning — the same category as the `[[ ]]` brackets this module
    already strips, and the reason assets are never embedded in the first place. Left in, every
    note that shows a diagram gets `tile-pattern.svg` in its vector, and notes come to resemble
    each other by how their files are named rather than by what they say.

    The alt text is kept, deliberately: a human wrote it to describe the picture, so it is the
    one part of the reference that carries meaning — often the only description of the diagram
    the embedder will ever see.
    """
    body = _MD_ASSET_LINK.sub(
        lambda m: m.group(1) if _is_asset_target(m.group(2)) else m.group(0), body)
    return _WIKI_ASSET_LINK.sub(
        lambda m: ((m.group(2) or "").strip() if _is_asset_target(m.group(1)) else m.group(0)),
        body)


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


def strip_lexical_only(body: str) -> str:
    """Remove every ``lexical-only`` block — kept out of the vector, kept in keyword search."""
    return remove_all_blocks(body, LEXICAL_ONLY_BEGIN, LEXICAL_ONLY_END)


def fence_errors(text: str) -> list[str]:
    """Everything wrong with this note's fences, as human-readable lines. Empty == valid.

    Two rules, and the second is what keeps this a single pass:

    1. **Every marker pairs.** An unpaired ``begin`` delimits nothing, so the region a human
       meant to exclude is embedded anyway — silent, because the note still commits.
    2. **Fences never nest.** One layer only, of either kind. Nesting has no useful meaning
       here (the inner fence could only repeat or contradict the outer), and forbidding it
       makes validity checkable by scanning markers in order and asserting they alternate.

    Deliberately returns messages rather than a bool: with two fence types, "invalid" is not
    actionable on its own — which marker, and where, is the whole content of the answer.
    """
    problems: list[str] = []
    for begin, end, name in FENCES:
        if unpaired_markers(text, begin, end):
            problems.append(f"a `{name}` marker pairs with nothing — the region it was meant "
                            f"to fence is NOT excluded, and nothing else will say so")

    # Nesting: walk every marker in document order; a begin while one is open, or an end that
    # closes the wrong fence, is an error. This also catches interleaving (`no-embed:begin`,
    # `lexical-only:begin`, `no-embed:end`), which pairs by count and is still meaningless.
    marks = sorted(
        [(offset, name, kind)
         for begin, end, name in FENCES
         for marker, kind in ((begin, "begin"), (end, "end"))
         for offset in _offsets(text, marker)])
    open_fence: str | None = None
    for _, name, kind in marks:
        if kind == "begin":
            if open_fence is not None:
                problems.append(f"a `{name}` fence opens inside an open `{open_fence}` fence — "
                                f"fences do not nest, use one layer only")
                break
            open_fence = name
        else:
            if open_fence != name:
                problems.append(f"a `{name}` fence closes where `{open_fence or 'nothing'}` "
                                f"was open — fences must not interleave")
                break
            open_fence = None
    return problems


def _offsets(text: str, needle: str) -> list[int]:
    """Every start offset of ``needle`` in ``text``."""
    out, i = [], text.find(needle)
    while i != -1:
        out.append(i)
        i = text.find(needle, i + len(needle))
    return out


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
    body = strip_lexical_only(body)
    # Before strip_wikilinks: it would turn `![[tile.svg]]` into the bare text `tile.svg`,
    # which is the filename this step exists to remove.
    body = strip_asset_links(body)
    body = strip_wikilinks(body)
    body = body.strip("\n")
    return body + "\n" if body else ""


def lexical_body(text: str) -> str:
    """The view the **keyword** index sees: like the canonical view, but reference data stays.

    Differs from ``canonical_body`` in **exactly one** way: ``lexical-only`` blocks are kept.
    Everything else — frontmatter, line endings, ``no-embed`` blocks, asset filenames, wikilink
    brackets — is treated identically, and that narrowness is the whole safety argument. #39's
    lesson was that the embedding, the content hash and the lexical index disagree the moment
    they are computed from different projections; one deliberate difference is auditable, two
    is where drift starts.

    (Wikilink handling is shared, not a difference: ``strip_wikilinks`` removes the brackets
    and keeps the target text, so a linked term is already searchable in both halves.)

    ``no-embed`` is still stripped here: art has no meaning to retrieve by, in either half.

    This feeds FTS only. It never touches the vector or the hash, which is why editing inside
    a ``lexical-only`` fence re-indexes the note without re-embedding it — the lexical row is
    rewritten on every upsert, while the sidecar is skipped when the content hash is unchanged.
    """
    body = _strip_frontmatter(text)
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = strip_no_embed(body)
    # Keep what the fence surrounds, drop the fence: the marker is machinery, and left in it
    # would make every fenced note match a search for "second-brain" or "lexical-only".
    for marker in (LEXICAL_ONLY_BEGIN, LEXICAL_ONLY_END):
        body = body.replace(marker + "\n", "").replace(marker, "")
    body = strip_asset_links(body)
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


def embed_excluded(text: str) -> bool:
    """Is this file marked ``embed: false`` in its frontmatter — a file, not a note?

    Location decides embedding everywhere else in this system: a Markdown file under a PARA
    root *is* a note. That leaves no way to keep supporting material — a project README,
    working scratch, a draft — beside the note it belongs to without it becoming a searchable
    note of its own and diluting retrieval.

    **Opt-out, never opt-in, and the polarity is the whole design.** Embedding stays the
    default, so a file nobody tagged is embedded and *visible*: it turns up in results, where
    a wrong exclusion is obvious and one line fixes it. Under opt-in the same forgetfulness
    makes a real note **silently unsearchable** — indistinguishable from a note that does not
    exist, and discovered only on the day it is needed and does not come back.

    That is also why this parser **fails open**. Anything it does not confidently read as
    false — a missing key, a typo, a value it cannot parse — means *embed*. The cost of
    wrongly embedding is a stray search hit; the cost of wrongly skipping is an invisible
    note. Only an explicit ``false`` / ``no`` / ``off`` excludes.
    """
    lines = text.splitlines()
    if not lines or lines[0].rstrip("\r\n") != "---":
        return False
    for line in lines[1:]:
        if line.rstrip("\r\n") == "---":
            return False  # end of frontmatter, no embed: key
        stripped = line.strip()
        if not stripped.startswith("embed:"):
            continue
        value = stripped[len("embed:"):].strip().strip("'\"").lower()
        return value in ("false", "no", "off")
    return False  # unterminated frontmatter — not real frontmatter, so not excluded


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
