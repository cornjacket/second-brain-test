#!/usr/bin/env python3
"""Regression suite for in-place note editing — task #67.

Covers the two decisions an edit makes before it touches the disk, both in `scripts/note_edit.py`
rather than in `mcp_server.py`: CI cannot import that module (the MCP SDK is optional), so rules
left there run only in a by-hand tier, and a by-hand tier drifts.

The headline assertion is the hash one. `note_view.content_hash` is taken over the *canonical
view*, which strips `no-embed` and `lexical-only` regions — so it cannot see an edit inside a
fence. Used as an edit token it would let a client overwrite a checkbox someone ticked in
Obsidian and report success. That test is the reason this module exists at all.

Pure stdlib. Dev-only, never emitted.

    python3 tests/test_note_edit.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import note_edit as ne  # noqa: E402
import note_view as nv  # noqa: E402

LB, LE = nv.LEXICAL_ONLY_BEGIN, nv.LEXICAL_ONLY_END


class EditToken(unittest.TestCase):
    """The token must see every byte, because a fence is exactly where it would not."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, text: str) -> Path:
        p = self.root / "n.md"
        p.write_text(text, encoding="utf-8")
        return p

    def test_a_fenced_edit_changes_the_token(self):
        """The whole point. content_hash is blind here; the token must not be."""
        a = f"---\ntags: [t]\n---\n\n# N\n\nprose\n\n{LB}\n- [ ] TB test\n{LE}\n"
        b = a.replace("- [ ] TB test", "- [x] TB test")
        self.assertEqual(nv.content_hash(a), nv.content_hash(b),
                         "premise: the canonical view is deliberately blind to a fenced edit")
        self.assertNotEqual(ne.file_hash(self.write(a)), ne.file_hash(self.write(b)),
                            "the edit token must NOT be blind to it, or a client silently "
                            "reverts whatever was ticked in Obsidian after its read")

    def test_a_frontmatter_only_edit_changes_the_token(self):
        # canonical_body strips frontmatter too, so a tag edit is the same class of blind spot.
        a = "---\ntags: [one]\n---\n\n# N\n\nbody\n"
        b = "---\ntags: [one, two]\n---\n\n# N\n\nbody\n"
        self.assertEqual(nv.content_hash(a), nv.content_hash(b))
        self.assertNotEqual(ne.file_hash(self.write(a)), ne.file_hash(self.write(b)))

    def test_identical_bytes_give_an_identical_token(self):
        t = "---\ntags: [t]\n---\n\n# N\n\nbody\n"
        self.assertEqual(ne.file_hash(self.write(t)), ne.file_hash(self.write(t)))

    def test_the_token_is_labelled_with_its_algorithm(self):
        # Matches content_hash's shape, so neither can be mistaken for a bare digest.
        self.assertTrue(ne.file_hash(self.write("x")).startswith("sha256:"))


class AllowedTargets(unittest.TestCase):
    """An allow-list. A deny-list would admit every file type nobody thought of."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Path(self._tmp.name)
        for d in ("projects", "areas", "resources", "archive", "glossary", "templates"):
            (self.brain / "vault" / d).mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)

    def ok(self, rel: str) -> Path:
        return ne.resolve_editable(rel, self.brain)

    def refuses(self, rel: str, expect: str = "") -> str:
        with self.assertRaises(ne.NotEditable, msg=f"{rel} was ALLOWED") as cm:
            ne.resolve_editable(rel, self.brain)
        if expect:
            self.assertIn(expect, str(cm.exception).lower())
        return str(cm.exception)

    def test_a_note_in_each_para_root_is_editable(self):
        for root in ne.PARA_ROOTS:
            with self.subTest(root=root):
                self.assertEqual(self.ok(f"vault/{root}/n.md").name, "n.md")

    def test_a_nested_note_is_editable(self):
        # PARA roots are walked recursively, so colocated notes must be editable too.
        self.assertEqual(self.ok("vault/projects/algebra-1/algebra-1--chapter-1.md").name,
                         "algebra-1--chapter-1.md")

    def test_the_two_vault_root_files_are_editable(self):
        for name in ne.VAULT_ROOT_EDITABLE:
            with self.subTest(name=name):
                self.assertEqual(self.ok(f"vault/{name}").name, name)

    def test_another_vault_root_file_is_not(self):
        self.refuses("vault/scratch.md", "not an editable note")

    def test_the_glossary_is_refused_and_says_why(self):
        # It has its own writer that cascades links; a raw edit leaves that graph stale.
        self.assertIn("add_glossary_term", self.refuses("vault/glossary/ablation.md"))

    def test_templates_are_refused(self):
        self.refuses("vault/templates/new-note.md", "not a para root")

    def test_an_asset_is_refused(self):
        self.refuses("vault/projects/tile.svg", "only markdown")

    def test_a_sidecar_is_refused(self):
        # Derived, regenerated by the hook. Hand-editing one corrupts the vector silently.
        self.refuses("vault/projects/.n.embed.json", "only markdown")

    def test_a_dotfile_markdown_is_refused(self):
        self.refuses("vault/projects/.hidden.md", "sidecar")

    def test_outside_the_vault_is_refused(self):
        for rel in ("README.md", "../escape.md", "scripts/db.py"):
            with self.subTest(rel=rel):
                self.refuses(rel, "outside the vault")

    def test_a_traversal_that_lands_outside_is_refused(self):
        # Resolution happens BEFORE the check, so spelling cannot smuggle a target in.
        self.refuses("vault/projects/../../README.md", "outside the vault")

    def test_a_traversal_that_lands_INSIDE_is_allowed(self):
        # The check is on where the path lands, not on how it is written.
        self.assertEqual(self.ok("vault/areas/../projects/n.md").name, "n.md")

    def test_an_absolute_path_works(self):
        # Search hits return absolute paths, so they must be accepted as-is.
        p = self.brain / "vault" / "resources" / "n.md"
        self.assertEqual(self.ok(str(p)), p.resolve())

    def test_the_vault_root_itself_is_refused(self):
        self.refuses("vault", "outside the vault")


if __name__ == "__main__":
    unittest.main(verbosity=2)
