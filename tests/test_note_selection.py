#!/usr/bin/env python3
"""The commit path must not go blind when the vault is git-ignored (task #42, step 2).

Three callers used to ask git ``diff --cached -- '*.md'`` for the notes to work on. That
answer is correct only while notes are tracked. Once encryption git-ignores the vault, git
stages no note and the query returns an **empty list** — not an error. Every caller then
does nothing, the hook still exits 0, and notes silently stop being embedded.

So the tests here are written the way that failure presents itself: **an empty result is
the bug**, and asserting "no exception" would pass on a completely broken selector. Each
one therefore asserts a specific note is *present* in the selection.

Both modes are covered on purpose. The encrypted mode is the new path, but the plaintext
mode is what must not regress — it is the behaviour every existing brain depends on, and
it is now produced by different code.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import note_selection as ns  # noqa: E402

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

NOTE = "---\ntags: [t]\n---\n\n# A Note\n\nBody.\n"
CHEAP = {"n": 1 << 10, "r": 8, "p": 1}
PASSPHRASE = "test passphrase"


def _git(brain: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=brain, capture_output=True, text=True)


class _BrainCase(unittest.TestCase):
    """A throwaway brain-shaped git repo: vault roots, one note, an initial commit."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Path(self._tmp.name)
        for root in ns.PARA_ROOTS + ("glossary",):
            (self.brain / "vault" / root).mkdir(parents=True)
        _git(self.brain, "init", "-q")
        _git(self.brain, "config", "user.email", "t@example.invalid")
        _git(self.brain, "config", "user.name", "T")
        self.note = "vault/projects/a-note.md"
        (self.brain / self.note).write_text(NOTE, encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def write(self, rel: str, text: str = NOTE) -> str:
        dest = self.brain / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        return rel


class PlaintextModeTest(_BrainCase):
    """Encryption off — the existing behaviour, which must not regress."""

    def setUp(self):
        super().setUp()
        os.environ["SECOND_BRAIN_ENCRYPTION"] = "0"
        self.addCleanup(os.environ.pop, "SECOND_BRAIN_ENCRYPTION", None)
        from features import _config
        _config.cache_clear()

    def test_a_staged_note_is_selected(self):
        _git(self.brain, "add", "--", self.note)
        self.assertIn(self.note, ns.notes_for_commit(root=self.brain))

    def test_an_unstaged_note_is_not(self):
        """The plaintext contract: this commit's notes, not the whole working tree."""
        self.assertEqual(ns.notes_for_commit(root=self.brain), [])

    def test_a_renamed_note_is_selected_at_its_NEW_path(self):
        """Task #47. Git calls a move `R`, which `--diff-filter=ACM` silently dropped.

        The note is byte-identical, so nothing here is `M`. If `R` leaves the filter again
        this returns [] — and an empty selection is exactly how the bug presented: the commit
        succeeds, nothing re-embeds, and the note quietly leaves the brain.
        """
        _git(self.brain, "add", "--", self.note)
        _git(self.brain, "commit", "-q", "-m", "the note")
        moved = "vault/archive/a-note.md"
        _git(self.brain, "mv", self.note, moved)
        selected = ns.notes_for_commit(root=self.brain)
        self.assertIn(moved, selected)
        self.assertNotIn(self.note, selected,
                         "the OLD path must not be selected — there is nothing there to embed")

    def test_a_plain_move_selects_the_same_as_git_mv(self):
        """There is no user-side workaround, which is why the selector had to change.

        `git mv` is shorthand for `mv` + `git rm` + `git add`; git records no difference and
        infers the rename at diff time. Staging it "the long way" produces an identical
        answer, so no wrapper script could have dodged this.
        """
        _git(self.brain, "add", "--", self.note)
        _git(self.brain, "commit", "-q", "-m", "the note")
        moved = "vault/resources/a-note.md"
        (self.brain / moved).parent.mkdir(parents=True, exist_ok=True)
        (self.brain / self.note).rename(self.brain / moved)
        _git(self.brain, "rm", "-q", "--cached", "--", self.note)
        _git(self.brain, "add", "--", moved)
        self.assertIn(moved, ns.notes_for_commit(root=self.brain))

    def test_a_moved_note_that_was_also_edited_is_still_selected(self):
        """Git scores this `R<score>` (or splits it) depending on similarity — either way
        the destination must come back, or an edit made during a move is lost."""
        _git(self.brain, "add", "--", self.note)
        _git(self.brain, "commit", "-q", "-m", "the note")
        moved = "vault/archive/a-note.md"
        _git(self.brain, "mv", self.note, moved)
        (self.brain / moved).write_text(NOTE + "\nAn edit made during the move.\n",
                                        encoding="utf-8")
        _git(self.brain, "add", "--", moved)
        self.assertIn(moved, ns.notes_for_commit(root=self.brain))

    def test_a_deleted_note_is_NOT_selected(self):
        """`D` stays out. Selecting it would send the embedder at a file that is gone —
        removal is `update_cache`'s job, not the embedder's."""
        _git(self.brain, "add", "--", self.note)
        _git(self.brain, "commit", "-q", "-m", "the note")
        _git(self.brain, "rm", "-q", "--", self.note)
        self.assertEqual(ns.notes_for_commit(root=self.brain), [])

    def test_a_note_moved_OUT_of_the_para_roots_is_not_selected(self):
        """Moving a note to vault/templates/ takes it out of the embedding scope. The
        destination is not a note, so there is nothing to embed at the new path."""
        _git(self.brain, "add", "--", self.note)
        _git(self.brain, "commit", "-q", "-m", "the note")
        (self.brain / "vault" / "templates").mkdir(parents=True, exist_ok=True)
        _git(self.brain, "mv", self.note, "vault/templates/a-note.md")
        self.assertEqual(ns.notes_for_commit(root=self.brain), [])

    def test_non_notes_and_other_roots_are_ignored(self):
        for rel in ("vault/templates/new-note.md", "README.md", "vault/projects/x.txt"):
            self.write(rel, "x")
        _git(self.brain, "add", "-A")
        selected = ns.notes_for_commit(root=self.brain)
        self.assertIn(self.note, selected)
        self.assertNotIn("vault/templates/new-note.md", selected)
        self.assertNotIn("README.md", selected)


@unittest.skipUnless(HAVE_CRYPTO, "needs the optional 'cryptography' package")
class EncryptedModeTest(_BrainCase):
    """Encryption on — where `git diff --cached` returns nothing and used to end the story."""

    def setUp(self):
        super().setUp()
        import encrypt_vault as ev
        os.environ["SECOND_BRAIN_ENCRYPTION"] = "1"
        os.environ["SECOND_BRAIN_PASSPHRASE"] = PASSPHRASE
        self.addCleanup(os.environ.pop, "SECOND_BRAIN_ENCRYPTION", None)
        self.addCleanup(os.environ.pop, "SECOND_BRAIN_PASSPHRASE", None)
        from features import _config
        _config.cache_clear()
        self.ev = ev
        ev.save_keyfile(ev.new_keyfile(PASSPHRASE, **CHEAP), self.brain / "enc" / "keyfile.json")
        self.keys = ev.keys_from_keyfile(
            ev.load_keyfile(self.brain / "enc" / "keyfile.json"), PASSPHRASE)
        # The vault is git-ignored, exactly as an encrypted brain has it.
        (self.brain / ".gitignore").write_text("/vault/**\n", encoding="utf-8")

    def test_git_stages_nothing_which_is_why_the_old_selector_went_blind(self):
        """Pins the premise. If this ever fails, the rest of this class proves nothing."""
        _git(self.brain, "add", "-A")
        self.assertEqual(ns.staged_notes(root=self.brain), [],
                         "the vault is not actually git-ignored — this fixture is not "
                         "reproducing the encrypted brain it claims to")

    def test_a_never_encrypted_note_is_selected(self):
        selected = ns.notes_for_commit(root=self.brain)
        self.assertIn(self.note, selected,
                      "a note with no blob was not selected — with the vault git-ignored "
                      "this is how notes silently stop being embedded")

    def test_an_edited_note_is_selected(self):
        self.ev.encrypt_file(self.keys, self.note, self.brain)
        (self.brain / self.note).write_text(NOTE + "\nEdited.\n", encoding="utf-8")
        self.assertIn(self.note, ns.notes_for_commit(root=self.brain))

    def test_an_unchanged_note_is_not_reselected(self):
        """The churn gate: an already-encrypted, unedited note is no work at all."""
        self.ev.encrypt_file(self.keys, self.note, self.brain)
        self.assertNotIn(self.note, ns.notes_for_commit(root=self.brain))

    def test_a_note_in_a_subdirectory_is_selected(self):
        deep = self.write("vault/projects/2026/q3/deep.md")
        self.assertIn(deep, ns.notes_for_commit(root=self.brain))

    def test_selection_does_not_depend_on_the_index(self):
        """Staging is irrelevant here — the working tree is the only witness left."""
        _git(self.brain, "add", "-A")
        self.assertIn(self.note, ns.notes_for_commit(root=self.brain))

    def test_a_missing_passphrase_raises_rather_than_returning_nothing(self):
        """The whole lesson in one assertion.

        Returning [] on a missing passphrase is indistinguishable from 'nothing changed',
        so the commit would proceed and embed nothing — the original bug, reintroduced by
        the code written to fix it.
        """
        import passphrase as pp
        os.environ.pop("SECOND_BRAIN_PASSPHRASE")
        with self.assertRaises((pp.PassphraseError, Exception)):
            ns.notes_for_commit(root=self.brain)


class PassphraseTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(os.environ.pop, "SECOND_BRAIN_PASSPHRASE", None)

    def test_env_var_wins(self):
        import passphrase as pp
        os.environ["SECOND_BRAIN_PASSPHRASE"] = "from-env"
        self.assertEqual(pp.resolve(self.brain), "from-env")

    def test_a_key_file_is_read_and_stripped_of_its_trailing_newline(self):
        import passphrase as pp
        key = self.brain / "key"
        key.write_text("from-file\n", encoding="utf-8")
        self.assertEqual(pp.read_key_file(key), "from-file")

    def test_an_empty_key_file_is_an_error_not_an_empty_passphrase(self):
        import passphrase as pp
        key = self.brain / "key"
        key.write_text("\n   \n", encoding="utf-8")
        with self.assertRaises(pp.PassphraseError):
            pp.read_key_file(key)

    def test_missing_everything_explains_how_to_fix_it(self):
        import passphrase as pp
        os.environ.pop("SECOND_BRAIN_PASSPHRASE", None)
        with self.assertRaises(pp.PassphraseError) as ctx:
            pp.resolve(self.brain)
        self.assertIn("SECOND_BRAIN_PASSPHRASE", str(ctx.exception))

    def test_the_default_location_is_outside_the_repo(self):
        """A secret inside the working tree is one `git add -f` from the remote."""
        import passphrase as pp
        self.assertFalse(pp.is_inside_repo(pp.default_path(self.brain), self.brain))


class BrainIdentityTest(unittest.TestCase):
    """A brain's key file is found by what the BRAIN says it is, not where it sits.

    Deriving the key filename from the local folder breaks in both directions, and both
    failures are silent-ish: two brains whose folders share a name quietly share one key
    file, and one brain cloned to two paths looks for two different files — reporting
    "wrong passphrase" when the real answer is "wrong filename".
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def brain(self, folder: str, *, brain_id: str | None = None,
              name: str | None = None) -> Path:
        path = self.root / folder
        (path / "enc").mkdir(parents=True)
        if brain_id or name:
            payload = {"v": 1, "kdf": "scrypt"}
            if brain_id:
                payload["id"] = brain_id
            if name:
                payload["name"] = name
            (path / "enc" / "keyfile.json").write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_identity_comes_from_the_keyfile_not_the_folder(self):
        import passphrase as pp
        b = self.brain("some-local-folder", brain_id="4f2a91c8", name="my-brain")
        self.assertEqual(pp.brain_identity(b), ("4f2a91c8", "my-brain"))
        self.assertIn("my-brain-4f2a91c8.key", str(pp.default_path(b)))

    def test_the_same_brain_at_two_paths_wants_ONE_key_file(self):
        """Clone it anywhere; the key file's name does not move."""
        import passphrase as pp
        a = self.brain("laptop-copy", brain_id="4f2a91c8", name="my-brain")
        b = self.brain("desktop-copy", brain_id="4f2a91c8", name="my-brain")
        self.assertEqual(pp.default_path(a), pp.default_path(b))

    def test_two_brains_sharing_a_folder_name_do_NOT_share_a_key_file(self):
        import passphrase as pp
        (self.root / "one").mkdir()
        (self.root / "two").mkdir()
        a = self.brain("one/second-brain", brain_id="aaaaaaaa", name="second-brain")
        b = self.brain("two/second-brain", brain_id="bbbbbbbb", name="second-brain")
        self.assertNotEqual(pp.default_path(a), pp.default_path(b))

    def test_a_keyfile_without_an_id_keeps_the_old_folder_derived_path(self):
        """A brain encrypted before ids existed must not be told its key has vanished."""
        import passphrase as pp
        b = self.brain("legacy-brain")
        self.assertEqual(pp.brain_identity(b), (None, "legacy-brain"))
        self.assertTrue(str(pp.default_path(b)).endswith("second-brain/legacy-brain.key"))

    def test_lookup_matches_the_id_so_a_renamed_brain_still_resolves(self):
        import passphrase as pp
        b = self.brain("brain", brain_id="4f2a91c8", name="renamed-since")
        keys_dir = self.root / "keys"
        keys_dir.mkdir()
        stale = keys_dir / "whatever-it-was-called-4f2a91c8.key"
        stale.write_text("secret", encoding="utf-8")
        real_dir = pp.KEYS_DIR
        pp.KEYS_DIR = keys_dir
        self.addCleanup(setattr, pp, "KEYS_DIR", real_dir)
        self.assertEqual(pp.find_key_file(b), stale)

    def test_the_id_and_name_carry_no_secret(self):
        import encrypt_vault as ev
        kf = ev.new_keyfile(PASSPHRASE, name="my-brain", **CHEAP)
        blob = json.dumps(kf)
        for secret in PASSPHRASE.split():
            self.assertNotIn(secret, blob)
        self.assertEqual(len(kf["id"]), 8)


if __name__ == "__main__":
    unittest.main()
