#!/usr/bin/env python3
"""Regression suite for the embed-excluded (``no-embed``) block — task #39.

The brain's own ``self_test.py`` asserts the two headline invariants (the art stays out
of the vector; editing it costs nothing). This is the **dev-only** tier that pins the
edges around them — multiple blocks, unterminated markers, the Obsidian-benign shape,
the token estimator — so the projection can be changed with something to break.

Pure stdlib; imports the scripts under test directly. Dev-only, never emitted.

    python3 tests/test_note_view.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import marked_block  # noqa: E402
import note_view as nv  # noqa: E402

BEGIN, END = nv.NO_EMBED_BEGIN, nv.NO_EMBED_END


def note(body: str) -> str:
    return f"---\ntags: [t]\n---\n\n# N\n\n{body}"


class StripNoEmbed(unittest.TestCase):
    def test_block_is_excluded_from_the_canonical_view(self):
        art = "┌────────┐\n│ roadmap │\n└────────┘"
        with_art = note(f"Prose.\n\n{BEGIN}\n```\n{art}\n```\n{END}\n")
        self.assertEqual(nv.canonical_body(with_art), nv.canonical_body(note("Prose.\n")))
        self.assertNotIn("roadmap", nv.canonical_body(with_art))

    def test_several_blocks_in_one_note_are_all_excluded(self):
        # A note may carry more than one diagram; handling only the first would embed
        # the rest — the bug the marker exists to prevent, just later in the file.
        body = f"A.\n\n{BEGIN}\nart-one\n{END}\n\nB.\n\n{BEGIN}\nart-two\n{END}\n\nC.\n"
        view = nv.canonical_body(note(body))
        self.assertNotIn("art-one", view)
        self.assertNotIn("art-two", view)
        for keep in ("A.", "B.", "C."):
            self.assertIn(keep, view)

    def test_prose_around_the_block_survives_intact(self):
        view = nv.canonical_body(note(f"Before.\n\n{BEGIN}\nart\n{END}\n\nAfter.\n"))
        self.assertEqual(view, "# N\n\nBefore.\n\nAfter.\n")

    def test_a_note_without_markers_is_byte_identical_to_before(self):
        # The feature must be inert for the notes already in a brain: any change to the
        # canonical view of an unmarked note would restamp every content hash and flag
        # the whole vault stale on upgrade.
        plain = note("Just prose, no markers at all.\n")
        self.assertEqual(nv.canonical_body(plain), "# N\n\nJust prose, no markers at all.\n")


class UnpairedMarkers(unittest.TestCase):
    def test_an_unterminated_block_strips_nothing_and_does_not_raise(self):
        # Fail open, loudly: a projection must not throw on the malformed input it is
        # asked to describe, or doctor crashes on the note it should be explaining.
        text = note(f"Prose.\n\n{BEGIN}\nart\n")
        self.assertIn("art", nv.canonical_body(text))
        self.assertTrue(nv.has_unpaired_no_embed(text))

    def test_a_lone_end_marker_is_reported(self):
        self.assertTrue(nv.has_unpaired_no_embed(note(f"Prose.\n\n{END}\n")))

    def test_a_well_formed_note_reports_nothing(self):
        self.assertFalse(nv.has_unpaired_no_embed(note(f"P.\n\n{BEGIN}\nart\n{END}\n")))
        self.assertFalse(nv.has_unpaired_no_embed(note("P.\n")))

    def test_a_trailing_stray_after_a_complete_block_is_still_reported(self):
        # count(begin) == count(end) here, which is why the check strips first and then
        # looks at what is left rather than counting markers.
        text = note(f"P.\n\n{BEGIN}\nart\n{END}\n\n{END}\n")
        self.assertTrue(nv.has_unpaired_no_embed(text))


class HashInvariance(unittest.TestCase):
    def test_editing_the_excluded_art_does_not_change_the_hash(self):
        # The point of stripping from the SAME view the hash reads: redrawing a diagram
        # must not re-embed the note, and must not trip doctor's stale-embedding check.
        one = note(f"P.\n\n{BEGIN}\n┌──┐\n{END}\n")
        two = note(f"P.\n\n{BEGIN}\n┌──────────────┐\n│ redrawn      │\n└──────────────┘\n{END}\n")
        self.assertEqual(nv.content_hash(one), nv.content_hash(two))

    def test_editing_the_prose_still_changes_the_hash(self):
        one = note(f"P.\n\n{BEGIN}\nart\n{END}\n")
        two = note(f"P. And more.\n\n{BEGIN}\nart\n{END}\n")
        self.assertNotEqual(nv.content_hash(one), nv.content_hash(two))

    def test_adding_a_marker_around_existing_art_does_change_the_hash(self):
        # Fencing art for the first time genuinely changes the embed input, so it SHOULD
        # re-embed — that is the user getting the cleaner vector they asked for.
        before = note("P.\n\n```\nart\n```\n")
        after = note(f"P.\n\n{BEGIN}\n```\nart\n```\n{END}\n")
        self.assertNotEqual(nv.content_hash(before), nv.content_hash(after))


class ObsidianBenign(unittest.TestCase):
    def test_the_markers_are_html_comments(self):
        # Obsidian's reading view hides HTML comments, so the human sees the fenced code
        # block exactly as written and pays nothing for the marker. Anything else here
        # (a fence info-string, a custom sigil) would render as visible junk.
        for marker in (BEGIN, END):
            self.assertTrue(marker.startswith("<!--") and marker.endswith("-->"))

    def test_the_markers_follow_the_house_marked_block_shape(self):
        self.assertIn("second-brain:no-embed:", BEGIN)
        self.assertTrue(BEGIN.endswith("begin -->") and END.endswith("end -->"))

    def test_the_markers_do_not_collide_with_the_other_marked_blocks(self):
        # register.py / install_skill.py splice `<!-- second-brain:begin -->` into global
        # memory; substring collision either way would make one block eat the other.
        other_begin, other_end = "<!-- second-brain:begin -->", "<!-- second-brain:end -->"
        for a, b in ((BEGIN, other_begin), (END, other_end)):
            self.assertNotIn(a, b)
            self.assertNotIn(b, a)


class RemoveAllBlocks(unittest.TestCase):
    def test_removal_is_idempotent(self):
        text = f"A\n\n{BEGIN}\nx\n{END}\n\nB\n"
        once = marked_block.remove_all_blocks(text, BEGIN, END)
        self.assertEqual(once, marked_block.remove_all_blocks(once, BEGIN, END))

    def test_text_without_a_block_is_returned_untouched(self):
        # Not even a trailing-newline fixup, or every unmarked note's view would shift.
        for text in ("no markers", "no markers\n", ""):
            self.assertEqual(marked_block.remove_all_blocks(text, BEGIN, END), text)

    def test_the_write_side_still_raises_on_a_half_marked_document(self):
        # remove_all_blocks is tolerant on purpose; splice_block must NOT become so.
        with self.assertRaises(marked_block.MarkedBlockError):
            marked_block.splice_block(f"A\n{BEGIN}\nx\n", BEGIN, END, "y")


class EstimateTokens(unittest.TestCase):
    def test_prose_estimates_at_about_four_characters_per_token(self):
        prose = "the quick brown fox jumps over the lazy dog " * 10
        self.assertAlmostEqual(nv.estimate_tokens(prose), len(prose) / 4, delta=2)

    def test_box_drawing_characters_cost_far_more_than_prose_per_character(self):
        # The whole reason line count is the wrong proxy: equal-length text, wildly
        # different embed cost.
        art = "─" * 400
        prose = "a" * 400
        self.assertGreater(nv.estimate_tokens(art), 3 * nv.estimate_tokens(prose))

    def test_a_short_note_with_a_big_diagram_can_blow_the_budget(self):
        # ~60 lines — nowhere near the 300-line guideline — yet over the embed budget.
        art = "\n".join("│" + "─" * 40 + "│" for _ in range(60))
        self.assertGreater(nv.estimate_tokens(art), nv.EMBED_TOKEN_BUDGET)
        self.assertLess(len(art.splitlines()), 300)

    def test_excluding_the_diagram_brings_the_note_back_under_budget(self):
        art = "\n".join("│" + "─" * 40 + "│" for _ in range(60))
        text = note(f"Short prose.\n\n{BEGIN}\n```\n{art}\n```\n{END}\n")
        self.assertLess(nv.estimate_tokens(nv.canonical_body(text)), nv.EMBED_TOKEN_BUDGET)


if __name__ == "__main__":
    unittest.main(verbosity=2)
