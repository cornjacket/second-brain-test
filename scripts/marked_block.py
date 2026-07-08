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

Three pure functions over the document text:

  ``has_block``    — is a complete block present?
  ``splice_block`` — set the body between the markers (append a fresh block if
                     absent); idempotent, so splicing an unchanged body returns
                     byte-identical text
  ``remove_block`` — strip the block and tidy the surrounding blank lines

Exactly one marker without its partner is a malformed document: every function
raises ``MarkedBlockError`` rather than guess where the missing boundary is.
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
