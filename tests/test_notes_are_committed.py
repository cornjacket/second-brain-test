#!/usr/bin/env python3
"""A brain without encryption commits its notes. That is the thing most worth pinning.

Every other test in this repo assumes it. Until now it was asserted in exactly **one**
place — `test_pdf_gitignore.py`, as a guard against the PDF rule over-reaching — and that
one assertion covers a single PARA root, no subdirectory, and asks `git check-ignore`
("would this be ignored?") rather than `git ls-files` ("is the content actually tracked?").

The failure it needs to catch is the worst one this brain can have: **an ignore rule that
quietly stops the notes being committed.** Nothing errors. The commit succeeds, the working
tree looks perfect, Obsidian is happy, search still works locally — and the remote slowly
fills with everything except your notes. You find out when you clone.

So the rules are exercised against a **real repository built from the brain's own shipped
`.gitignore`**, not against whatever repo happens to contain the test — a hermetic fixture
that behaves identically here, in the vendored copy, and in CI.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

PARA_ROOTS = ("projects", "areas", "resources", "archive")
NOTE = "---\ntags: [t]\n---\n\n# A Note\n\nBody.\n"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


class PlaintextBrainTest(unittest.TestCase):
    """The shipped ignore rules, applied to a brain-shaped repo with the toggle off."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.brain = Path(cls._tmp.name)
        shutil.copy2(REPO_ROOT / ".gitignore", cls.brain / ".gitignore")
        for name in PARA_ROOTS + ("glossary", "templates"):
            (cls.brain / "vault" / name).mkdir(parents=True)
        _git(cls.brain, "init", "-q")
        _git(cls.brain, "config", "user.email", "p@example.invalid")
        _git(cls.brain, "config", "user.name", "P")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def ignored(self, rel: str) -> bool:
        return _git(self.brain, "check-ignore", "-q", rel).returncode == 0

    def write(self, rel: str) -> str:
        dest = self.brain / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(NOTE, encoding="utf-8")
        return rel

    # --- case 1: every root, not just the one the PDF test happened to use ---------

    def test_a_note_in_every_para_root_is_committable(self):
        for name in PARA_ROOTS:
            with self.subTest(root=name):
                self.assertFalse(self.ignored(f"vault/{name}/a-note.md"))

    def test_a_glossary_term_is_committable(self):
        """The glossary is content too — it is a note per term, not a config file."""
        self.assertFalse(self.ignored("vault/glossary/a-term.md"))

    # --- case 2: depth ------------------------------------------------------------

    def test_a_note_in_a_subdirectory_is_committable(self):
        for rel in ("vault/projects/2026/deep.md",
                    "vault/projects/2026/q3/kitchen/deeper.md"):
            with self.subTest(rel=rel):
                self.assertFalse(self.ignored(rel))

    # --- case 3: tracked, not merely un-ignored ------------------------------------

    def test_notes_are_actually_tracked_after_git_add(self):
        """`check-ignore` says what *would* happen; this says what *did*.

        The distinction is the whole point: a rule can leave a note un-ignored and still
        have it never reach a commit, and only `ls-files` can tell the difference.
        """
        rels = [self.write(f"vault/{name}/tracked-{name}.md") for name in PARA_ROOTS]
        rels.append(self.write("vault/glossary/tracked-term.md"))
        rels.append(self.write("vault/projects/nested/tracked-deep.md"))
        _git(self.brain, "add", "-A")
        _git(self.brain, "commit", "-q", "-m", "notes")

        tracked = set(_git(self.brain, "ls-files").stdout.split())
        for rel in rels:
            with self.subTest(rel=rel):
                self.assertIn(rel, tracked, f"{rel} is not tracked — a plaintext brain "
                                            f"must commit its notes")

    def test_the_committed_note_still_contains_its_text(self):
        """Tracked but empty would satisfy `ls-files` and lose the note anyway."""
        rel = self.write("vault/areas/content-check.md")
        _git(self.brain, "add", "--", rel)
        _git(self.brain, "commit", "-q", "-m", "content")
        self.assertEqual(_git(self.brain, "show", f"HEAD:{rel}").stdout, NOTE)

    # --- case 4: none of the encrypted layout leaks into a plaintext brain ---------

    def test_a_plaintext_brain_has_no_encrypted_layout(self):
        self.assertFalse((REPO_ROOT / "enc").exists(),
                         "this brain has an enc/ directory but encryption is off")
        blobs = list(REPO_ROOT.rglob("*.md.enc"))
        self.assertEqual(blobs, [], f"encrypted blobs in a plaintext brain: {blobs}")

    def test_the_encryption_toggle_ships_off(self):
        from features import encryption
        import os
        if "SECOND_BRAIN_ENCRYPTION" in os.environ:
            self.skipTest("the env var overrides the shipped default")
        self.assertFalse(encryption(), "encryption must ship off — every brain that never "
                                       "opts in has to behave exactly as it did before")

    # --- what is deliberately NOT committed ---------------------------------------

    def test_derived_and_foreign_files_are_still_ignored(self):
        """The other half: this must not become 'commit everything under vault/'."""
        for rel in ("vault/resources/.a-note.embed.json",   # derived vector
                    "vault/resources/paper.pdf",            # binary
                    "vault/.obsidian/workspace.json"):      # editor state
            with self.subTest(rel=rel):
                self.assertTrue(self.ignored(rel), f"{rel} should be ignored")


if __name__ == "__main__":
    unittest.main()
