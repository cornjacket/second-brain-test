#!/usr/bin/env python3
"""Regression suite for colocated assets and nested notes — the `add_asset` work.

Three separable claims, and each fails in its own way:

* **Path validation.** `subpath` and an asset `filename` both turn caller-supplied text into a
  filesystem path, so both are strict allow-lists rather than denylists of bad characters.
* **Filename uniqueness.** Obsidian resolves `[[wikilinks]]` by basename. That was globally
  unique by accident — notes sat in a flat root and a directory cannot hold two files of one
  name — and subfolders remove the accident silently, because two nested notes with the same
  name are two valid, different paths.
* **Vector hygiene.** An asset's *filename* is a path, not meaning. If it reaches the embed
  input, notes start resembling each other by how their files are named.

Pure stdlib; imports the scripts under test directly. Dev-only, never emitted.

    python3 tests/test_asset_colocation.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_unique_names as un  # noqa: E402
try:
    import mcp_server as mcp  # noqa: E402
except ImportError:  # the mcp SDK is an optional dep
    mcp = None
import note_view as nv  # noqa: E402


class AssetLinksLeaveTheVector(unittest.TestCase):
    """The filename is a path; the alt text is the only part a human wrote to mean something."""

    def view(self, body: str) -> str:
        return nv.canonical_body(f"---\ntags: [t]\n---\n\n# N\n\n{body}\n")

    def test_a_markdown_image_keeps_its_alt_and_loses_its_filename(self):
        v = self.view("![a tiling of the plane](tile-pattern.svg)")
        self.assertIn("a tiling of the plane", v)
        self.assertNotIn("tile-pattern.svg", v)

    def test_an_obsidian_embed_loses_the_filename_entirely(self):
        # `![[x.svg]]` carries no alt text, so there is nothing to keep. Before this existed
        # the wikilink stripper turned it into the bare string "tile-pattern.svg".
        self.assertNotIn("tile-pattern", self.view("![[tile-pattern.svg]]"))

    def test_an_obsidian_embed_keeps_its_alias(self):
        self.assertIn("the tiling", self.view("![[tile-pattern.svg|the tiling]]"))
        self.assertNotIn("tile-pattern", self.view("![[tile-pattern.svg|the tiling]]"))

    def test_a_plain_link_to_a_data_file_keeps_its_text(self):
        v = self.view("See [the source rows](measurements.csv).")
        self.assertIn("the source rows", v)
        self.assertNotIn("measurements.csv", v)

    def test_a_link_to_another_NOTE_is_untouched(self):
        # .md is not an asset. This is the existing wikilink behaviour and must not change.
        self.assertIn("algebra", self.view("See [[algebra]]."))
        self.assertIn("the algebra note", self.view("See [the algebra note](algebra.md)."))

    def test_a_url_is_untouched(self):
        # An external link is not an asset in this vault; rewriting it would silently edit
        # what the embedder reads about a source the note actually cites.
        v = self.view("See [docs](https://example.com/a.html).")
        self.assertIn("https://example.com/a.html", v)

    def test_prose_containing_a_dotted_word_is_not_mangled(self):
        self.assertIn("version 1.2 of the spec", self.view("We use version 1.2 of the spec."))


@unittest.skipIf(__import__('sys').modules.get('mcp_server') is None,
                 'the optional mcp SDK is absent')
class ComposeFilename(unittest.TestCase):
    """`title` is the H1; structure is passed as structure (task #53).

    The bug this closes: `--` encodes "scoped to its folder", `_slugify` collapses any run of
    non-alphanumerics to one hyphen, so a caller asked to express structure through a display
    string could not — and the failure only became visible after the commit and the push.
    """

    def compose(self, *a, **k):
        return mcp.compose_note_filename(*a, **k)

    def test_entry_takes_the_name_from_the_folder(self):
        self.assertEqual(
            self.compose("Chapter 1", "algebra-1/algebra-1--chapter-1", entry=True),
            "algebra-1--chapter-1")

    def test_entry_ignores_the_title_entirely(self):
        # The point of decoupling: the H1 can read "Chapter 1" on a file that must be called
        # algebra-1--chapter-1.md. Titling it "Algebra 1--Chapter 1" was a bad heading AND
        # did not work.
        for title in ("Chapter 1", "Anything At All", "x"):
            self.assertEqual(self.compose(title, "a/b--c", entry=True), "b--c")

    def test_descriptor_scopes_under_the_folder_and_the_join_survives(self):
        self.assertEqual(
            self.compose("Worked Solutions", "algebra-1/algebra-1--chapter-1",
                         descriptor="worked-solutions"),
            "algebra-1--chapter-1--worked-solutions")

    def test_descriptor_is_slugified_but_the_join_is_added_after(self):
        # Slugifying the JOINED string would collapse the `--` — the original bug, one level in.
        self.assertEqual(self.compose("T", "a/b--c", descriptor="Worked Solutions"),
                         "b--c--worked-solutions")

    def test_entry_and_descriptor_together_are_an_error(self):
        with self.assertRaises(ValueError):
            self.compose("T", "a/b", entry=True, descriptor="x")

    def test_either_without_subpath_is_an_error(self):
        # Rejecting beats silently ignoring: a caller that passed entry=True believes the
        # filename came from the folder, and would never check.
        for kw in ({"entry": True}, {"descriptor": "x"}):
            with self.assertRaises(ValueError):
                self.compose("T", "", **kw)

    def test_neither_is_the_old_behaviour_exactly(self):
        # The regression guard for every flat note already in a vault.
        self.assertEqual(self.compose("Vector Search", ""), "vector-search")
        self.assertEqual(self.compose("Vector Search", "a/b"), "vector-search")

    def test_no_title_can_produce_a_double_dash(self):
        # The premise of the whole redesign, pinned so nobody "fixes" the slugifier instead.
        for title in ("A--B", "A  B", "A -- B", "A._-B"):
            self.assertNotIn("--", self.compose(title, ""))


@unittest.skipIf(__import__('sys').modules.get('mcp_server') is None,
                 'the optional mcp SDK is absent')
class Guardrail(unittest.TestCase):
    """A name that does not fit its folder is refused BEFORE the write — there is no undo."""

    def check(self, stem, subpath):
        mcp.check_scoped_name(stem, "projects", subpath, "T")

    def test_the_entry_note_name_is_accepted(self):
        self.check("algebra-1--chapter-1", "algebra-1/algebra-1--chapter-1")

    def test_a_scoped_child_is_accepted(self):
        self.check("algebra-1--chapter-1--worked-solutions", "algebra-1/algebra-1--chapter-1")

    def test_a_bare_slugified_title_is_refused(self):
        # Exactly what the failed call produced: chapter-1.md inside algebra-1--chapter-1/.
        with self.assertRaises(ValueError):
            self.check("chapter-1", "algebra-1/algebra-1--chapter-1")

    def test_a_near_miss_prefix_is_refused(self):
        # Single dash where the join must be double — the collapse, caught at the call.
        with self.assertRaises(ValueError):
            self.check("algebra-1-chapter-1", "algebra-1/algebra-1--chapter-1")

    def test_the_error_names_the_arguments_that_would_work(self):
        with self.assertRaises(ValueError) as cm:
            self.check("chapter-1", "algebra-1/algebra-1--chapter-1")
        msg = str(cm.exception)
        self.assertIn("algebra-1--chapter-1.md", msg)
        self.assertIn("entry=True", msg)

    def test_no_subpath_means_no_constraint(self):
        self.check("anything-at-all", "")


class UniqueNames(unittest.TestCase):
    """Two notes of one name make every [[wikilink]] to that name ambiguous."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for para in un.PARA_ROOTS:
            (self.root / "vault" / para).mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)

    def write(self, rel: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("---\ntags: [t]\n---\n\n# N\n", encoding="utf-8")

    def test_a_flat_vault_with_distinct_names_is_clean(self):
        self.write("vault/projects/algebra.md")
        self.write("vault/resources/embeddings.md")
        self.assertEqual(un.duplicates(self.root), {})

    def test_two_nested_notes_of_the_same_name_collide(self):
        # The case subfolders introduce: two valid, different PATHS, one ambiguous NAME. Every
        # existing check passes on this, which is exactly why it needed a new one.
        self.write("vault/projects/algebra/chapter1/chapter1.md")
        self.write("vault/projects/geometry/chapter1/chapter1.md")
        self.assertEqual(sorted(un.duplicates(self.root)), ["chapter1.md"])

    def test_a_collision_ACROSS_para_roots_is_caught(self):
        # Four roots were always four namespaces — projects/x.md and resources/x.md could
        # always coexist. Global uniqueness was habit, not the filesystem.
        self.write("vault/projects/algebra.md")
        self.write("vault/resources/algebra.md")
        self.assertEqual(sorted(un.duplicates(self.root)), ["algebra.md"])

    def test_the_report_names_every_colliding_path(self):
        self.write("vault/projects/algebra/chapter1/chapter1.md")
        self.write("vault/archive/geometry/chapter1/chapter1.md")
        self.assertEqual(un.duplicates(self.root)["chapter1.md"],
                         ["vault/archive/geometry/chapter1/chapter1.md",
                          "vault/projects/algebra/chapter1/chapter1.md"])

    def test_templates_and_glossary_are_not_notes_and_do_not_collide(self):
        # vault/templates/ is devkit machinery and vault/glossary/ is a separate, deliberately
        # flat namespace. Neither is walked, so neither can trip the gate.
        self.write("vault/projects/new-note.md")
        (self.root / "vault" / "templates").mkdir(parents=True, exist_ok=True)
        (self.root / "vault" / "templates" / "new-note.md").write_text("x", encoding="utf-8")
        (self.root / "vault" / "glossary").mkdir(parents=True, exist_ok=True)
        (self.root / "vault" / "glossary" / "new-note.md").write_text("x", encoding="utf-8")
        self.assertEqual(un.duplicates(self.root), {})

    def test_the_DOCUMENTED_nested_naming_survives_two_projects(self):
        """The canonical example, followed twice. If it collides, the docs teach a trap.

        A bare `chapter-1/chapter-1.md` reads fine in isolation and fails the moment a second
        subject has a chapter 1 — which is the whole reason a child is named after its parent.
        """
        self.write("vault/projects/algebra/algebra.md")
        self.write("vault/projects/algebra/algebra-chapter-1/algebra-chapter-1.md")
        self.write("vault/projects/geometry/geometry.md")
        self.write("vault/projects/geometry/geometry-chapter-1/geometry-chapter-1.md")
        self.assertEqual(un.duplicates(self.root), {})

    def test_the_UNSCOPED_form_is_what_collides(self):
        """The negative of the test above — otherwise it proves only that four names differ."""
        self.write("vault/projects/algebra/chapter-1/chapter-1.md")
        self.write("vault/projects/geometry/chapter-1/chapter-1.md")
        self.assertEqual(sorted(un.duplicates(self.root)), ["chapter-1.md"])

    def test_an_asset_never_collides_with_a_note(self):
        # Assets are not walked: two tile.svg files in different project folders are fine,
        # because a relative image link resolves by PATH, not by name.
        self.write("vault/projects/algebra/algebra.md")
        self.write("vault/projects/geometry/geometry.md")
        (self.root / "vault/projects/algebra/tile.svg").write_text("<svg/>", encoding="utf-8")
        (self.root / "vault/projects/geometry/tile.svg").write_text("<svg/>", encoding="utf-8")
        self.assertEqual(un.duplicates(self.root), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
