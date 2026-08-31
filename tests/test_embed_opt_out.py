#!/usr/bin/env python3
"""Regression suite for the ``embed: false`` frontmatter opt-out — task #45.

Location alone used to decide whether a Markdown file is a note: anything under a PARA
root was one. ``note_view.embed_excluded`` is the escape hatch, so supporting material can
live *beside* the note it belongs to — project scratch, a colocated README, a draft.

The polarity is the whole design, and it is what this suite mostly pins. Embedding is the
**default** and the parser **fails open**: only an explicit ``false``/``no``/``off``
excludes, and anything else — a missing key, a typo, an unparseable value, a key that only
looks like frontmatter — means *embed*. The reason is asymmetric cost. Wrongly embedding
puts a stray hit in a search result, where the mistake is visible and one line fixes it;
wrongly excluding makes a real note **silently** unfindable, indistinguishable from a note
that was never written and discovered on the day it does not come back.

So every test below that asserts ``False`` is guarding the expensive direction. Read them
that way: they are not about parsing YAML, they are about which way this fails.

Pure stdlib; imports the script under test directly. Dev-only, never emitted.

    python3 tests/test_embed_opt_out.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import note_view as nv  # noqa: E402


class Excludes(unittest.TestCase):
    """The narrow set of inputs that really do opt out."""

    def test_the_plain_key(self):
        self.assertTrue(nv.embed_excluded("---\nembed: false\n---\n\n# F\n"))

    def test_no_and_off_are_accepted_too(self):
        # The three spellings a human actually writes for "off" in YAML frontmatter.
        for value in ("no", "off"):
            with self.subTest(value=value):
                self.assertTrue(nv.embed_excluded(f"---\nembed: {value}\n---\n\n# F\n"))

    def test_case_and_quoting_do_not_matter(self):
        for value in ("False", "FALSE", "'false'", '"false"', "No", "OFF"):
            with self.subTest(value=value):
                self.assertTrue(nv.embed_excluded(f"---\nembed: {value}\n---\n\n# F\n"))

    def test_the_key_can_sit_anywhere_in_the_frontmatter(self):
        text = "---\ntags: [t]\nembed: false\naliases: [x]\n---\n\n# F\n"
        self.assertTrue(nv.embed_excluded(text))

    def test_trailing_whitespace_and_crlf_survive(self):
        self.assertTrue(nv.embed_excluded("---\r\nembed: false  \r\n---\r\n\r\n# F\r\n"))


class FailsOpen(unittest.TestCase):
    """Everything else embeds. Each of these, read the other way, is an invisible note."""

    def test_no_frontmatter_at_all(self):
        self.assertFalse(nv.embed_excluded("# Just a note\n\nProse.\n"))

    def test_no_embed_key(self):
        self.assertFalse(nv.embed_excluded("---\ntags: [t]\n---\n\n# N\n"))

    def test_embed_true_embeds(self):
        self.assertFalse(nv.embed_excluded("---\nembed: true\n---\n\n# N\n"))

    def test_an_unparseable_value_embeds(self):
        # A typo must not silently exclude. "fasle" is the realistic one.
        for value in ("fasle", "0", "nope", "", "maybe"):
            with self.subTest(value=value):
                self.assertFalse(nv.embed_excluded(f"---\nembed: {value}\n---\n\n# N\n"))

    def test_the_key_after_the_frontmatter_ends_is_not_frontmatter(self):
        # Prose that merely mentions the key — including this very feature's own
        # documentation — must not exclude the note describing it.
        text = "---\ntags: [t]\n---\n\n# N\n\nSet `embed: false` to opt out.\n"
        self.assertFalse(nv.embed_excluded(text))

    def test_unterminated_frontmatter_is_not_frontmatter(self):
        # No closing `---`: the file is malformed, so it is read as ordinary Markdown and
        # embedded. Excluding here would hide a note behind a typo three lines up.
        self.assertFalse(nv.embed_excluded("---\ntags: [t]\n\n# N\n\nProse.\n"))

    def test_a_similarly_named_key_does_not_count(self):
        for key in ("embedded: false", "embed_pdf: false", "no-embed: false"):
            with self.subTest(key=key):
                self.assertFalse(nv.embed_excluded(f"---\n{key}\n---\n\n# N\n"))

    def test_empty_file(self):
        self.assertFalse(nv.embed_excluded(""))


class Templates(unittest.TestCase):
    """The shipped starting points must actually be what they claim to be."""

    def test_the_not_a_note_template_carries_the_key(self):
        for rel in ("seeds/templates/not-a-note.md", "vault/templates/not-a-note.md"):
            with self.subTest(rel=rel):
                path = REPO_ROOT / rel
                self.assertTrue(path.is_file(), f"{rel} is missing")
                self.assertTrue(nv.embed_excluded(path.read_text(encoding="utf-8")),
                                f"{rel} does not actually opt out — copying it into a PARA "
                                f"root would embed the file it promises not to")

    def test_the_note_template_does_not(self):
        # The pair only means anything if the default one still embeds.
        path = REPO_ROOT / "seeds" / "templates" / "new-note.md"
        self.assertFalse(nv.embed_excluded(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
