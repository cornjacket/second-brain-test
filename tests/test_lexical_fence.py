#!/usr/bin/env python3
"""Regression suite for the `lexical-only` fence — task #55.

Two fences, two different exclusions, and the distinction is the point:

  ``no-embed``      out of the vector AND out of keyword search — decoration, which has no
                    meaning to retrieve by in either half.
  ``lexical-only``  out of the vector, KEPT in keyword search — reference data. An ID or a
                    phone number is a *token*, not a meaning: useless to an embedding, which
                    ranks by similarity, and exactly what BM25 is built for.

The safety argument is narrowness. ``lexical_body`` differs from ``canonical_body`` in exactly
one way; #39's lesson was that the embedding, the content hash and the lexical index drift
apart the moment they are computed from projections that differ in more than one place.

Pure stdlib. Dev-only, never emitted.

    python3 tests/test_lexical_fence.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import note_view as nv  # noqa: E402

NB, NE = nv.NO_EMBED_BEGIN, nv.NO_EMBED_END
LB, LE = nv.LEXICAL_ONLY_BEGIN, nv.LEXICAL_ONLY_END


def note(body: str) -> str:
    return f"---\ntags: [t]\n---\n\n# N\n\n{body}\n"


class TwoProjections(unittest.TestCase):
    def test_lexical_only_leaves_the_vector_and_stays_in_the_index(self):
        t = note(f"prose\n\n{LB}\nREG-066388\n{LE}")
        self.assertNotIn("REG-066388", nv.canonical_body(t))
        self.assertIn("REG-066388", nv.lexical_body(t))

    def test_no_embed_leaves_BOTH(self):
        # The existing fence must not change meaning: art is not lexically useful either.
        t = note(f"prose\n\n{NB}\nASCII ART\n{NE}")
        self.assertNotIn("ASCII ART", nv.canonical_body(t))
        self.assertNotIn("ASCII ART", nv.lexical_body(t))

    def test_the_markers_never_reach_the_index(self):
        # Left in, every fenced note would match a search for "second-brain" or "lexical-only".
        t = note(f"{LB}\nREG-1\n{LE}")
        self.assertNotIn("second-brain:", nv.lexical_body(t))
        self.assertNotIn("lexical-only", nv.lexical_body(t))

    def test_the_two_projections_differ_ONLY_on_lexical_only(self):
        # The whole safety argument, asserted rather than promised: with no lexical-only
        # region present, the two views are byte-identical.
        for body in ("plain prose", f"art\n{NB}\nX\n{NE}", "a [[link]] and ![alt](x.svg)",
                     "# heading\n\n- a list\n- of things"):
            with self.subTest(body=body):
                t = note(body)
                self.assertEqual(nv.canonical_body(t), nv.lexical_body(t))

    def test_editing_inside_a_lexical_fence_does_not_re_embed(self):
        # The reason the fence exists: the content hash is taken over the canonical view, so a
        # changed phone number leaves the vector untouched. The lexical row still refreshes,
        # because index_fts runs on every upsert regardless of the hash.
        a = note(f"prose\n\n{LB}\n- [ ] TB test\ncall 408-453-6767\n{LE}")
        b = note(f"prose\n\n{LB}\n- [x] TB test\ncall 408-453-6749\n{LE}")
        self.assertEqual(nv.content_hash(a), nv.content_hash(b))
        self.assertNotEqual(nv.lexical_body(a), nv.lexical_body(b))

    def test_a_wikilinked_term_is_searchable_in_both(self):
        t = note("See [[ablation]] and [[study|the study]].")
        for view in (nv.canonical_body(t), nv.lexical_body(t)):
            self.assertIn("ablation", view)
            self.assertIn("the study", view)
            self.assertNotIn("[[", view)


class FenceValidation(unittest.TestCase):
    """A malformed fence excludes NOTHING, and says so nowhere. That is what this catches."""

    def test_a_well_formed_note_has_no_errors(self):
        self.assertEqual(nv.fence_errors(note(f"a\n{NB}\nart\n{NE}\nb\n{LB}\nid\n{LE}\nc")), [])

    def test_no_fences_at_all_is_valid(self):
        self.assertEqual(nv.fence_errors(note("just prose")), [])

    def test_an_unpaired_marker_is_reported_for_either_fence(self):
        for begin, name in ((NB, "no-embed"), (LB, "lexical-only")):
            with self.subTest(name=name):
                errs = nv.fence_errors(note(f"{begin}\nx"))
                self.assertTrue(errs)
                self.assertIn(name, errs[0])

    def test_a_stray_END_is_also_unpaired(self):
        self.assertTrue(nv.fence_errors(note(f"x\n{LE}")))

    def test_nesting_is_refused(self):
        # One layer only. An inner fence could only repeat or contradict the outer one, and
        # forbidding it is what makes validity a single pass over the markers.
        errs = nv.fence_errors(note(f"{NB}\n{LB}\nx\n{LE}\n{NE}"))
        self.assertTrue(errs)
        self.assertIn("nest", errs[0])

    def test_same_fence_nested_in_itself_is_refused(self):
        self.assertTrue(nv.fence_errors(note(f"{LB}\n{LB}\nx\n{LE}\n{LE}")))

    def test_interleaving_is_refused_even_though_the_counts_balance(self):
        # begin-A, begin-B, end-A, end-B: every marker has a partner by count, and the region
        # is still meaningless. A count-based check would call this fine.
        self.assertTrue(nv.fence_errors(note(f"{NB}\n{LB}\nx\n{NE}\n{LE}")))

    def test_two_sequential_fences_are_fine(self):
        self.assertEqual(nv.fence_errors(note(f"{NB}\na\n{NE}\n\n{LB}\nb\n{LE}")), [])

    def test_several_blocks_of_one_kind_are_fine(self):
        self.assertEqual(nv.fence_errors(note(f"{LB}\na\n{LE}\nx\n{LB}\nb\n{LE}")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
