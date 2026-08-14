#!/usr/bin/env python3
"""Enabling encryption, cloning, and coming back (task #42, step 3).

The unit tests prove the mechanism; these prove the *migration* — the part a user actually
runs, against a real git repository. The question they answer is the one the whole feature
exists for: **after this, does the repository still contain my notes?**

So the load-bearing assertions are about **absence**, and absence is exactly the shape that
passes forever without comparing anything. They are written to look in the place that
cannot be faked — every blob in the object store, via ``git cat-file --batch-all-objects``
— rather than at the working tree, and the fixture plants canaries in a note's *body*, its
*filename*, and a *subdirectory name* so each hiding place is checked separately.

Nothing here needs a network or the real brain: each test builds a throwaway git repo.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import encrypt_vault as ev  # noqa: E402

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

PASSPHRASE = "migration test passphrase"
BODY_CANARY = "zarquon-severance-clause"
NAME_CANARY = "quillfeather"
DIR_CANARY = "mistlethwaite"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def all_object_text(root: Path) -> str:
    """Every byte of every object in the repository, as one searchable string.

    Not ``git log -p`` and not the working tree: this walks the object store itself, which
    is the only view that cannot be tidied up by a checkout. Tree objects are included on
    purpose — that is where **filenames** live, and filenames are half of what is being
    hidden.

    Read as bytes and decoded with ``replace``: ciphertext is binary, so a text-mode read
    dies on the very objects this is meant to inspect. Decoding leniently keeps any ASCII
    that *is* in there — including a leaked name — findable.
    """
    objects = subprocess.run(["git", "cat-file", "--batch-all-objects", "--batch"],
                             cwd=root, capture_output=True)
    log = subprocess.run(["git", "log", "--format=%H %s%n%b", "--name-only", "--all"],
                         cwd=root, capture_output=True)
    return (objects.stdout + b"\n" + log.stdout).decode("utf-8", "replace")


def committed_text(root: Path, ref: str = "HEAD") -> str:
    """Everything ``ref`` commits — every tracked path and every tracked byte.

    This, not ``all_object_text``, is what the feature actually promises: encryption
    governs what a commit *contains* from now on. It cannot reach backwards into objects
    that were written before it was switched on — see
    ``test_history_before_the_migration_still_holds_the_plaintext``, which pins that limit
    rather than leaving it as a claim in the docs.
    """
    listing = subprocess.run(["git", "ls-tree", "-r", ref], cwd=root, capture_output=True)
    parts = [listing.stdout]
    for line in listing.stdout.decode("utf-8", "replace").splitlines():
        meta, _, _name = line.partition("\t")
        fields = meta.split()
        if len(fields) >= 3 and fields[1] == "blob":
            parts.append(subprocess.run(["git", "cat-file", "-p", fields[2]],
                                        cwd=root, capture_output=True).stdout)
    parts.append(subprocess.run(["git", "log", "--format=%s%n%b", ref],
                                cwd=root, capture_output=True).stdout)
    return b"\n".join(parts).decode("utf-8", "replace")


@unittest.skipUnless(HAVE_CRYPTO, "needs the optional 'cryptography' package")
class _EncryptedBrain(unittest.TestCase):
    """A throwaway brain-shaped repo, seeded with three canaries. No tests of its own —
    subclassed so the fixture is built once per case rather than inherited along with a
    second copy of every assertion."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Path(self._tmp.name) / "brain"
        self.addCleanup(self._tmp.cleanup)
        os.environ["SECOND_BRAIN_PASSPHRASE"] = PASSPHRASE
        self.addCleanup(os.environ.pop, "SECOND_BRAIN_PASSPHRASE", None)
        # Cheap KDF: the shipped cost is pinned by the unit tests and would add ~1s per
        # derivation here for no extra coverage.
        self._real_n = ev.SCRYPT_N
        ev.SCRYPT_N = 1 << 10
        self.addCleanup(setattr, ev, "SCRYPT_N", self._real_n)

        for name in ev.CONTENT_ROOTS + ("templates",):
            (self.brain / "vault" / name).mkdir(parents=True)
        (self.brain / "config").mkdir()
        (self.brain / "config" / "features.toml").write_text(
            "hybrid_search = true\nglossary_autolink = false\n\n[pdf]\nlist_sort = \"newest\"\n",
            encoding="utf-8")
        (self.brain / ".gitignore").write_text("data/*\n", encoding="utf-8")
        (self.brain / "vault" / "templates" / "new-note.md").write_text(
            "# template\n", encoding="utf-8")
        (self.brain / "README.md").write_text("# A brain\n", encoding="utf-8")

        self.note = f"vault/projects/{NAME_CANARY}-plan.md"
        (self.brain / self.note).write_text(
            f"---\ntags: [t]\n---\n\n# Plan\n\nThe {BODY_CANARY} applies.\n", encoding="utf-8")
        self.deep = f"vault/resources/{DIR_CANARY}/nested/deep-note.md"
        (self.brain / self.deep).parent.mkdir(parents=True)
        (self.brain / self.deep).write_text("---\ntags: [t]\n---\n\n# Deep\n\nBody.\n",
                                            encoding="utf-8")
        (self.brain / "vault" / "glossary" / "a-term.md").write_text(
            "# a-term\n\nA definition.\n", encoding="utf-8")
        # An empty bucket: its emptiness must not be visible either.
        _git(self.brain, "init", "-q")
        _git(self.brain, "config", "user.email", "m@example.invalid")
        _git(self.brain, "config", "user.name", "M")
        _git(self.brain, "add", "-A")
        _git(self.brain, "commit", "-q", "-m", "seed")

    def enable(self, **kw):
        return ev.enable(self.brain, PASSPHRASE, **kw)


@unittest.skipUnless(HAVE_CRYPTO, "needs the optional 'cryptography' package")
class MigrationTest(_EncryptedBrain):
    # --- the point of the whole feature ---------------------------------------

    def test_note_body_is_absent_from_what_is_committed(self):
        self.enable()
        self.assertNotIn(BODY_CANARY, committed_text(self.brain))

    def test_note_filename_is_absent_from_what_is_committed(self):
        self.enable()
        self.assertNotIn(NAME_CANARY, committed_text(self.brain))

    def test_subdirectory_name_is_absent_from_what_is_committed(self):
        """A folder called `divorce/` is a tell even when its notes are unreadable."""
        self.enable()
        self.assertNotIn(DIR_CANARY, committed_text(self.brain))

    def test_the_canaries_were_present_before_encrypting(self):
        """Proves the three assertions above can fail — without this they test nothing."""
        text = committed_text(self.brain)
        for canary in (BODY_CANARY, NAME_CANARY, DIR_CANARY):
            self.assertIn(canary, text, f"{canary} was not in the seed commit, so its "
                                        f"absence afterwards would prove nothing")

    def test_history_before_the_migration_still_holds_the_plaintext(self):
        """The documented limit, pinned as a fact rather than left as a claim.

        Encryption governs what future commits contain. Everything already committed —
        and, if the brain has a remote, already pushed — stays exactly where it is, in
        reachable objects, until the history itself is rewritten or the repo deleted.

        This test exists to fail loudly if anyone ever "fixes" it quietly, and to make the
        consequence concrete: **a brain that has ever committed plaintext cannot be made
        retroactively private by switching this on.** For a repo where that matters, start
        from a history that never held plaintext.
        """
        self.enable()
        history = all_object_text(self.brain)
        for canary in (BODY_CANARY, NAME_CANARY, DIR_CANARY):
            self.assertIn(canary, history,
                          "the pre-migration history no longer holds the plaintext — if that "
                          "is now genuinely true, the README's warning is wrong and should be "
                          "corrected, not this test")

    def test_only_the_note_template_stays_tracked_under_vault(self):
        self.enable()
        tracked = _git(self.brain, "ls-files", "vault").stdout.split()
        self.assertEqual(tracked, ["vault/templates/new-note.md"])

    def test_every_note_has_a_blob(self):
        notes = self.enable()
        blobs = list((self.brain / "enc").glob(f"*{ev.SUFFIX}"))
        self.assertEqual(len(blobs), len(notes))
        self.assertEqual(sorted(notes), sorted([self.note, "vault/glossary/a-term.md", self.deep]),
                         "the content set is wrong — it must be the vault minus the one "
                         "machinery carve-out, across every PARA root and the glossary")

    def test_the_glossary_is_encrypted_but_its_guide_is_not(self):
        """Terms are content; GLOSSARY.md would be machinery — the rule, not a list."""
        notes = self.enable()
        self.assertIn("vault/glossary/a-term.md", notes)

    # --- round trip ------------------------------------------------------------

    def test_a_fresh_clone_decrypts_byte_identically(self):
        self.enable()
        before = {rel: (self.brain / rel).read_bytes() for rel in ev.content_notes(self.brain)}
        clone = self.brain.parent / "clone"
        _git(self.brain.parent, "clone", "-q", str(self.brain), str(clone))
        self.assertFalse((clone / "vault" / "projects").exists() and
                         list((clone / "vault" / "projects").glob("*.md")),
                         "the clone arrived with plaintext notes — nothing was encrypted")
        ev.decrypt_all(clone, PASSPHRASE)
        after = {rel: (clone / rel).read_bytes() for rel in ev.content_notes(clone)}
        self.assertEqual(after, before)

    def test_a_clone_rebuilds_subdirectories_from_the_envelope(self):
        self.enable()
        clone = self.brain.parent / "clone2"
        _git(self.brain.parent, "clone", "-q", str(self.brain), str(clone))
        ev.decrypt_all(clone, PASSPHRASE)
        self.assertTrue((clone / self.deep).exists(),
                        "a nested note did not come back — nothing commits the directory, so "
                        "it has to be rebuilt from the path inside the envelope")

    def test_a_clone_rebuilds_the_para_skeleton(self):
        self.enable()
        clone = self.brain.parent / "clone3"
        _git(self.brain.parent, "clone", "-q", str(self.brain), str(clone))
        ev.decrypt_all(clone, PASSPHRASE)
        for name in ev.CONTENT_ROOTS:
            self.assertTrue((clone / "vault" / name).is_dir(), f"vault/{name} was not recreated")

    def test_the_wrong_passphrase_cannot_decrypt_a_clone(self):
        self.enable()
        clone = self.brain.parent / "clone4"
        _git(self.brain.parent, "clone", "-q", str(self.brain), str(clone))
        with self.assertRaises(ev.WrongPassphrase):
            ev.decrypt_all(clone, "not the passphrase")

    # --- migration mechanics ---------------------------------------------------

    def test_the_working_tree_is_untouched(self):
        """Obsidian, search and the embedder must not notice anything happened."""
        before = (self.brain / self.note).read_bytes()
        self.enable()
        self.assertEqual((self.brain / self.note).read_bytes(), before)

    def test_the_toggle_is_written_as_a_top_level_key(self):
        self.enable()
        text = (self.brain / "config" / "features.toml").read_text(encoding="utf-8")
        self.assertIn("encryption = true", text)
        self.assertLess(text.index("encryption = true"), text.index("[pdf]"),
                        "the toggle landed after a [section] header, which would make it a "
                        "member of that table instead of a top-level toggle")

    def test_ignore_rules_are_spliced_without_disturbing_existing_ones(self):
        self.enable()
        text = (self.brain / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/*", text)
        self.assertIn("/vault/**", text)

    def test_a_dirty_tree_is_refused_before_anything_is_written(self):
        (self.brain / "vault" / "projects" / "unsaved.md").write_text("wip\n", encoding="utf-8")
        with self.assertRaises(ev.EncryptionError):
            self.enable()
        self.assertFalse((self.brain / "enc").exists(),
                         "a refused migration still created enc/ — preflight must run before "
                         "anything is written")

    def test_enabling_twice_is_refused(self):
        self.enable()
        with self.assertRaises(ev.EncryptionError):
            self.enable()

    def test_sync_is_quiet_when_nothing_changed(self):
        """The churn gate at migration scale: a second run must produce no new ciphertext."""
        self.enable()
        encrypted, removed = ev.sync(self.brain, PASSPHRASE)
        self.assertEqual((encrypted, removed), ([], []))
        self.assertEqual(_git(self.brain, "status", "--porcelain").stdout.strip(), "")

    def test_sync_picks_up_an_edit_and_drops_a_deletion(self):
        self.enable()
        (self.brain / self.note).write_text("---\ntags: [t]\n---\n\n# Plan\n\nNew.\n",
                                            encoding="utf-8")
        (self.brain / self.deep).unlink()
        encrypted, removed = ev.sync(self.brain, PASSPHRASE)
        self.assertEqual(encrypted, [self.note])
        self.assertEqual(len(removed), 1)

    def test_disable_restores_plaintext_and_retracks_it(self):
        self.enable()
        ev.disable(self.brain, PASSPHRASE)
        self.assertEqual((self.brain / self.note).read_text(encoding="utf-8").count(BODY_CANARY), 1)
        self.assertIn(self.note, _git(self.brain, "ls-files", "vault").stdout.split())
        self.assertFalse((self.brain / "enc").exists())
        self.assertIn("encryption = false",
                      (self.brain / "config" / "features.toml").read_text(encoding="utf-8"))


@unittest.skipUnless(HAVE_CRYPTO, "needs the optional 'cryptography' package")
class LeakSurfaceTest(_EncryptedBrain):
    """The remaining places a fact about your notes could escape."""

    def test_an_empty_bucket_leaves_no_trace(self):
        """Which PARA roots you *do not* use is information too.

        The golden ships `.gitkeep` only in the buckets that happen to be empty, so
        committing them would have advertised exactly that. `vault/areas/` is empty in this
        fixture; nothing may reveal that it exists at all.
        """
        self.enable()
        committed = committed_text(self.brain)
        for bucket in ("areas", "archive"):
            with self.subTest(bucket=bucket):
                self.assertNotIn(f"vault/{bucket}", committed)
                self.assertNotIn(".gitkeep", committed)

    def test_editing_a_note_does_not_change_its_blob_name(self):
        """Otherwise every edit is a delete-plus-add, and the diff advertises churn."""
        self.enable()
        before = sorted(p.name for p in (self.brain / "enc").glob(f"*{ev.SUFFIX}"))
        (self.brain / self.note).write_text("---\ntags: [t]\n---\n\n# Plan\n\nRevised.\n",
                                            encoding="utf-8")
        ev.sync(self.brain, PASSPHRASE)
        after = sorted(p.name for p in (self.brain / "enc").glob(f"*{ev.SUFFIX}"))
        self.assertEqual(after, before)

    def test_the_migration_commit_message_names_no_note(self):
        self.enable()
        subjects = subprocess.run(["git", "log", "--format=%s%n%b"], cwd=self.brain,
                                  capture_output=True, text=True).stdout
        for canary in (BODY_CANARY, NAME_CANARY, DIR_CANARY):
            self.assertNotIn(canary, subjects)

    # --- the passphrase must not travel with the ciphertext -----------------------

    def _stage_key_inside_repo(self) -> Path:
        key = self.brain / "secret.key"
        key.write_text(PASSPHRASE, encoding="utf-8")
        _git(self.brain, "config", "secondbrain.passphrasefile", str(key))
        _git(self.brain, "add", "-f", "--", "secret.key")
        return key

    def test_a_staged_passphrase_file_blocks_the_commit(self):
        """The one leak that is not partial: the key beside the ciphertext is the brain."""
        self.enable()
        self._stage_key_inside_repo()
        self.assertIsNotNone(ev.passphrase_file_problem(self.brain))

    def test_a_passphrase_file_outside_the_repo_is_fine(self):
        self.enable()
        self.assertIsNone(ev.passphrase_file_problem(self.brain))

    def test_an_unstaged_key_inside_the_repo_does_not_block_work(self):
        """A bad habit, not an accident in progress — doctor says so; the commit proceeds."""
        self.enable()
        key = self.brain / "secret.key"
        key.write_text(PASSPHRASE, encoding="utf-8")
        _git(self.brain, "config", "secondbrain.passphrasefile", str(key))
        self.assertIsNone(ev.passphrase_file_problem(self.brain))

    # --- a half-finished migration must be named, not hidden ----------------------

    def test_the_toggle_on_without_a_keyfile_is_reported(self):
        """`encryption = true` is a claim. enc/keyfile.json is the fact.

        A brain in this state looks encrypted to every tool that reads the toggle while its
        notes are still plaintext — the worst possible combination to be silent about.
        """
        import os
        sys.path.insert(0, str(SCRIPTS))
        import doctor
        os.environ["SECOND_BRAIN_ENCRYPTION"] = "1"
        self.addCleanup(os.environ.pop, "SECOND_BRAIN_ENCRYPTION", None)
        from features import _config
        _config.cache_clear()
        real_root = doctor.REPO_ROOT
        doctor.REPO_ROOT = self.brain
        self.addCleanup(setattr, doctor, "REPO_ROOT", real_root)

        rep = doctor.Report()
        doctor.check_encryption(rep)
        self.assertGreater(rep.problems, 0,
                           "doctor stayed silent on a brain claiming encryption it has not "
                           "performed — the notes are plaintext and everything reading the "
                           "toggle believes otherwise")


class UntrackIsNotDeleteTest(unittest.TestCase):
    """Untracking a note is not deleting it — and confusing the two destroys vectors.

    `git diff-tree` reports both as `D`. The cache updater acted on that `D` by unlinking
    the note's sidecar, so the single commit that enables encryption — which untracks the
    whole vault at once — **wiped every embedding in the brain**, forcing a full re-embed
    and leaving search degraded until someone ran `doctor --repair`.

    Found by running the migration end-to-end on a generated brain, not by a test: nothing
    failed, nothing printed, the commit succeeded, and the vectors were simply gone.

    Both halves are asserted. Without the second, the first would pass for a cache updater
    that had simply stopped deleting anything at all.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.brain / "vault" / "projects").mkdir(parents=True)
        self.note = "vault/projects/a-note.md"
        (self.brain / self.note).write_text("---\ntags: [t]\n---\n\n# A\n\nBody.\n",
                                            encoding="utf-8")
        _git(self.brain, "init", "-q")
        _git(self.brain, "config", "user.email", "u@example.invalid")
        _git(self.brain, "config", "user.name", "U")
        _git(self.brain, "add", "-A")
        _git(self.brain, "commit", "-q", "-m", "seed")

        import update_cache as uc
        self.uc = uc
        self._real_root = uc.REPO_ROOT
        uc.REPO_ROOT = self.brain
        self.addCleanup(setattr, uc, "REPO_ROOT", self._real_root)

    def test_untracking_a_note_that_still_exists_is_not_a_deletion(self):
        _git(self.brain, "rm", "--cached", "-q", "--", self.note)
        _git(self.brain, "commit", "-q", "-m", "untrack the vault")
        _, to_delete = self.uc.changed_in_commit("HEAD")
        self.assertEqual(to_delete, [],
                         "untracking a note read as deleting it — the cache updater would "
                         "unlink its sidecar and throw away the embedding")

    def test_actually_deleting_a_note_still_is_a_deletion(self):
        (self.brain / self.note).unlink()
        _git(self.brain, "add", "-A")
        _git(self.brain, "commit", "-q", "-m", "delete the note")
        _, to_delete = self.uc.changed_in_commit("HEAD")
        self.assertEqual(to_delete, [self.note],
                         "a genuinely deleted note was not reported — the fix for the case "
                         "above must not stop real deletions from being cleaned up")


if __name__ == "__main__":
    unittest.main()
