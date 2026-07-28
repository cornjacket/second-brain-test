#!/usr/bin/env python3
"""Splice a devkit-owned *marked block* into an otherwise user-owned text file.

A marked block is a region delimited by a BEGIN and an END marker::

    <preamble the user owns>
    <BEGIN marker>
    <body the devkit owns>
    <END marker>
    <appendix the user owns>

Several features need exactly this operation over **different** documents with
**different** markers — the ``--nudge`` reminder in global memory
(``<!-- second-brain:begin/end -->``), the auto-link ``related_auto:`` frontmatter
block, the README managed region — so the markers are **passed in as arguments**.
This module shares the *logic*, never the tags.

Five pure functions over the document text:

  ``has_block``    — is a complete block present?
  ``splice_block`` — set the body between the markers (append a fresh block if
                     absent); idempotent, so splicing an unchanged body returns
                     byte-identical text
  ``remove_block`` — strip the block and tidy the surrounding blank lines

  ``remove_all_blocks``  — strip **every** complete block, tolerating a stray marker
  ``unpaired_markers``   — is a marker left over that forms no complete block?

The first three are the **write** side (splicing a devkit-owned block into a user's
file). Exactly one marker without its partner is a malformed document there, so they
raise ``MarkedBlockError`` rather than guess where the missing boundary is.

The last two are the **read** side (projecting a user's document, e.g. the no-embed
region of ``note_view.canonical_body``), where the same stance would be wrong: a
projection must never throw on the malformed input it is asked to describe, or the
diagnostic that should explain the typo crashes on it instead. So they are *total* —
they strip what is unambiguous, leave a stray marker as literal text, and expose
``unpaired_markers`` so a caller can warn about it precisely.
"""
from __future__ import annotations


class MarkedBlockError(ValueError):
    """A document has exactly one of the two markers, so the block is unlocatable."""


def has_block(text: str, begin: str, end: str) -> bool:
    """True iff a complete ``begin`` … ``end`` block is present.

    Raises ``MarkedBlockError`` if exactly one of the two markers is present.
    """
    has_begin, has_end = begin in text, end in text
    if has_begin != has_end:
        missing = "end" if has_begin else "begin"
        raise MarkedBlockError(f"marked block has a {'begin' if has_begin else 'end'} "
                               f"marker but no {missing} marker")
    return has_begin


def splice_block(text: str, begin: str, end: str, new_body: str) -> str:
    """Return ``text`` with the body between ``begin`` and ``end`` set to ``new_body``.

    Present  → replace the body in place, leaving everything outside the markers
               byte-for-byte untouched (so re-splicing the same body is a no-op).
    Absent   → append a fresh block, separated from existing content by a blank
               line and terminated with a trailing newline.
    One marker only → ``MarkedBlockError``.
    """
    if has_block(text, begin, end):
        before, _, rest = text.partition(begin)
        _, _, after = rest.partition(end)
        return f"{before}{begin}\n{new_body}\n{end}{after}"
    prefix = text
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix:
        prefix += "\n"  # blank line before our block
    return f"{prefix}{begin}\n{new_body}\n{end}\n"


def remove_block(text: str, begin: str, end: str) -> str:
    """Return ``text`` with the ``begin`` … ``end`` block removed and the blank
    lines around it tidied. No block → unchanged. One marker only → ``MarkedBlockError``.
    """
    if not has_block(text, begin, end):
        return text
    before, _, rest = text.partition(begin)
    _, _, after = rest.partition(end)
    before = before.rstrip("\n")
    after = after.lstrip("\n")
    new = before + ("\n\n" if before and after else "") + after
    if new and not new.endswith("\n"):
        new += "\n"
    return new


def remove_all_blocks(text: str, begin: str, end: str) -> str:
    """Return ``text`` with **every** complete ``begin`` … ``end`` block removed.

    Differs from ``remove_block`` in two ways, both because this is the *read* side:

    - **Repeats.** One note can carry several excluded regions (two diagrams, say),
      so this loops instead of handling only the first.
    - **Never raises.** A ``begin`` with no following ``end`` delimits nothing, so
      there is no unambiguous region to remove: the marker is left in place as
      literal text and the scan stops. Callers that care ask ``unpaired_markers``.

    Blank lines around each removed block are tidied exactly as ``remove_block``
    does, so the result is a stable view rather than one that carries the removal's
    whitespace scar.
    """
    out, removed = text, False
    while True:
        i = out.find(begin)
        if i < 0:
            break
        j = out.find(end, i + len(begin))
        if j < 0:
            break  # unterminated — leave it alone (see docstring)
        before = out[:i].rstrip("\n")
        after = out[j + len(end):].lstrip("\n")
        out = before + ("\n\n" if before and after else "") + after
        removed = True
    if removed and out and not out.endswith("\n"):
        out += "\n"
    return out


def unpaired_markers(text: str, begin: str, end: str) -> bool:
    """True iff a marker survives ``remove_all_blocks`` — i.e. it pairs with nothing.

    The exact complement of what ``remove_all_blocks`` could strip, rather than a
    ``count(begin) != count(end)`` approximation (which calls a trailing ``end`` …
    ``begin`` pair balanced). This is what turns a typo'd marker from a silent no-op
    — the region stays in the embed input, the very bug the marker exists to prevent —
    into something a caller can name.
    """
    rest = remove_all_blocks(text, begin, end)
    return begin in rest or end in rest
