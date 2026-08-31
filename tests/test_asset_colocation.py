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
