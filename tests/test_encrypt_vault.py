#!/usr/bin/env python3
"""The encryption mechanism: keys, names, envelope (task #42, build step 1).

These are unit tests over ``scripts/encrypt_vault.py`` alone — no git, no working tree,
no toggle. The properties they pin are the ones the whole feature rests on:

  * a note **round-trips byte-identically**, or the feature destroys data;
  * the opaque name is **deterministic** (no churn) and **keyed** (a name reveals
    nothing, and two brains with the same note produce different names);
  * a wrong passphrase is caught **once, by the verifier**, not N times by N notes;
  * a tampered envelope **fails** rather than returning plausible bytes.

Cheap KDF parameters throughout: these tests exercise the *wiring*, and the shipped
cost (n=2**17, ~134 MB) would make the suite take minutes to prove nothing extra. The
real parameters travel in the keyfile and are pinned separately, below.

Skipped wholesale when ``cryptography`` is absent — it is an optional dependency, and a
brain that never enables encryption never installs it.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import encrypt_vault as ev  # noqa: E402

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

# Deliberately weak — see the module docstring.
CHEAP = {"n": 1 << 10, "r": 8, "p": 1}
PASSPHRASE = "correct horse battery staple"
NOTE = b"---\ntags: [testing]\n---\n\n# kitchen remodel\n\nQuote came in high.\n"
REL = "vault/projects/kitchen-remodel.md"


def cheap_keys(passphrase: str = PASSPHRASE, salt: bytes = b"0123456789abcdef") -> ev.Keys:
    return ev.derive_keys(passphrase, salt, **CHEAP)


@unittest.skipUnless(HAVE_CRYPTO, "needs the optional 'cryptography' package")
class EnvelopeTest(unittest.TestCase):
    def setUp(self):
        self.keys = cheap_keys()

    def test_round_trip_is_byte_identical(self):
        path, body = ev.decrypt_note(self.keys, ev.encrypt_note(self.keys, REL, NOTE))
        self.assertEqual(path, REL)
        self.assertEqual(body, NOTE)

    def test_round_trip_preserves_exotic_bodies(self):
        """Empty, binary-ish, unicode and newline-heavy notes all survive."""
        for label, body in [
            ("empty", b""),
            ("no trailing newline", b"# just a title"),
            ("unicode", "# café ☕\n\nnaïve — résumé\n".encode("utf-8")),
            ("newlines", b"\n\n\n"),
            ("json-looking", b'{"v": 1, "path": "spoof"}\nreal body\n'),
        ]:
            with self.subTest(label):
                blob = ev.encrypt_note(self.keys, REL, body)
                self.assertEqual(ev.decrypt_note(self.keys, blob)[1], body)

    def test_plaintext_does_not_appear_in_the_envelope(self):
        """The canary the whole feature exists for, at the smallest possible scale."""
        blob = ev.encrypt_note(self.keys, REL, NOTE)
        self.assertNotIn(b"kitchen remodel", blob)
        self.assertNotIn(b"kitchen-remodel", blob)
        self.assertNotIn(b"projects", blob)
        self.assertNotIn(b"Quote came in high", blob)

    def test_tampering_is_detected(self):
        blob = bytearray(ev.encrypt_note(self.keys, REL, NOTE))
        blob[-1] ^= 0x01
        with self.assertRaises(ev.EnvelopeError):
            ev.decrypt_note(self.keys, bytes(blob))

    def test_another_brains_key_cannot_read_it(self):
        blob = ev.encrypt_note(self.keys, REL, NOTE)
        with self.assertRaises(ev.EnvelopeError):
            ev.decrypt_note(cheap_keys("a different passphrase"), blob)

    def test_malformed_envelopes_raise_rather_than_return_garbage(self):
        for label, blob in [
            ("empty", b""),
            ("foreign", b"# just a markdown file\n"),
            ("magic only", ev.MAGIC),
            ("truncated", ev.encrypt_note(self.keys, REL, NOTE)[:10]),
        ]:
            with self.subTest(label), self.assertRaises(ev.EnvelopeError):
                ev.decrypt_note(self.keys, blob)

    def test_nonce_is_fresh_per_encryption(self):
        """Two encryptions of one note differ — which is why the phash skip-gate exists."""
        a = ev.encrypt_note(self.keys, REL, NOTE)
        b = ev.encrypt_note(self.keys, REL, NOTE)
        self.assertNotEqual(a, b)
        self.assertEqual(ev.decrypt_note(self.keys, a), ev.decrypt_note(self.keys, b))


@unittest.skipUnless(HAVE_CRYPTO, "needs the optional 'cryptography' package")
class SkipGateTest(unittest.TestCase):
    def setUp(self):
        self.keys = cheap_keys()

    def test_unchanged_body_is_recognised(self):
        blob = ev.encrypt_note(self.keys, REL, NOTE)
        self.assertTrue(ev.is_unchanged(self.keys, blob, NOTE))

    def test_edited_body_is_not(self):
        blob = ev.encrypt_note(self.keys, REL, NOTE)
        self.assertFalse(ev.is_unchanged(self.keys, blob, NOTE + b"one more line\n"))

    def test_a_one_byte_edit_is_not(self):
        blob = ev.encrypt_note(self.keys, REL, NOTE)
        self.assertFalse(ev.is_unchanged(self.keys, blob, NOTE.replace(b"high", b"hign")))

    def test_corrupt_blob_reads_as_changed_rather_than_throwing(self):
        """A caller asking 'do I need to re-encrypt?' must get an answer, not an exception."""
        self.assertFalse(ev.is_unchanged(self.keys, b"garbage", NOTE))


class NameTest(unittest.TestCase):
    """No cryptography needed — names are HMAC only."""

    def setUp(self):
        self.keys = cheap_keys()

    def test_name_is_deterministic(self):
        self.assertEqual(ev.blob_name(self.keys, REL), ev.blob_name(self.keys, REL))

    def test_name_survives_a_rederived_key(self):
        """The whole no-churn property: a fresh process must compute the same name."""
        self.assertEqual(ev.blob_name(self.keys, REL), ev.blob_name(cheap_keys(), REL))

    def test_name_is_keyed(self):
        other = cheap_keys("a different passphrase")
        self.assertNotEqual(ev.blob_name(self.keys, REL), ev.blob_name(other, REL))

    def test_name_leaks_no_part_of_the_path(self):
        name = ev.blob_name(self.keys, REL).lower()
        for fragment in ("kitchen", "remodel", "projects", "vault"):
            self.assertNotIn(fragment, name)

    def test_distinct_paths_get_distinct_names(self):
        paths = [
            "vault/projects/a.md", "vault/projects/b.md", "vault/areas/a.md",
            "vault/projects/nested/a.md", "vault/glossary/a.md",
        ]
        names = {ev.blob_name(self.keys, p) for p in paths}
        self.assertEqual(len(names), len(paths))

    def test_subdirectory_depth_is_just_a_longer_path(self):
        deep = "vault/projects/2026/q3/kitchen/notes.md"
        self.assertTrue(ev.blob_name(self.keys, deep).endswith(ev.SUFFIX))
        self.assertNotEqual(ev.blob_name(self.keys, deep), ev.blob_name(self.keys, REL))

    def test_path_spellings_are_canonicalised_to_one_name(self):
        """Two spellings of one path must not produce two blobs for one note."""
        for variant in ("./" + REL, "vault//projects/kitchen-remodel.md",
                        "vault\\projects\\kitchen-remodel.md"):
            with self.subTest(variant):
                self.assertEqual(ev.blob_name(self.keys, variant), ev.blob_name(self.keys, REL))

    def test_paths_that_escape_the_brain_are_refused(self):
        for bad in ("../outside.md", "vault/../../etc/passwd", "/etc/passwd", ""):
            with self.subTest(bad), self.assertRaises(ev.EncryptionError):
                ev.blob_name(self.keys, bad)

    def test_suffix_is_not_matched_by_a_plain_md_glob(self):
        """Why `.md.enc` and not `.mdx`: the ignore rule stays an exact glob."""
        name = ev.blob_name(self.keys, REL)
        self.assertTrue(name.endswith(".md.enc"))
        self.assertFalse(Path(name).match("*.md"))


class OrphanTest(unittest.TestCase):
    def setUp(self):
        self.keys = cheap_keys()
        self.live = ["vault/projects/a.md", "vault/areas/b.md"]
        self.names = [ev.blob_name(self.keys, p) for p in self.live]

    def test_nothing_orphaned_when_every_note_is_live(self):
        self.assertEqual(ev.orphan_blobs(self.keys, self.live, self.names), set())

    def test_a_deleted_note_leaves_an_orphan(self):
        orphans = ev.orphan_blobs(self.keys, self.live[:1], self.names)
        self.assertEqual(orphans, {self.names[1]})

    def test_a_rename_orphans_the_old_blob(self):
        renamed = ["vault/projects/a.md", "vault/areas/b-renamed.md"]
        self.assertEqual(ev.orphan_blobs(self.keys, renamed, self.names), {self.names[1]})

    def test_non_envelope_files_are_never_reported(self):
        """`enc/keyfile.json` lives in the same directory and is not an orphan."""
        self.assertEqual(
            ev.orphan_blobs(self.keys, self.live, self.names + ["keyfile.json", "README.md"]),
            set())


class KeyfileTest(unittest.TestCase):
    def test_verifier_accepts_the_right_passphrase(self):
        kf = ev.new_keyfile(PASSPHRASE, **CHEAP)
        keys = ev.keys_from_keyfile(kf, PASSPHRASE)
        self.assertEqual(ev.verify_tag(keys), kf["verify"])

    def test_verifier_rejects_the_wrong_one(self):
        kf = ev.new_keyfile(PASSPHRASE, **CHEAP)
        with self.assertRaises(ev.WrongPassphrase):
            ev.keys_from_keyfile(kf, PASSPHRASE + "!")

    def test_keyfile_holds_no_secret(self):
        kf = ev.new_keyfile(PASSPHRASE, hint="the usual one", **CHEAP)
        blob = repr(kf).lower()
        for secret in ("correct", "horse", "battery", "staple"):
            self.assertNotIn(secret, blob)

    def test_hint_is_optional_and_round_trips(self):
        self.assertNotIn("hint", ev.new_keyfile(PASSPHRASE, **CHEAP))
        self.assertEqual(ev.new_keyfile(PASSPHRASE, hint="h", **CHEAP)["hint"], "h")

    def test_salt_is_fresh_per_brain(self):
        """Two brains with the same passphrase must not share keys or names."""
        a, b = ev.new_keyfile(PASSPHRASE, **CHEAP), ev.new_keyfile(PASSPHRASE, **CHEAP)
        self.assertNotEqual(a["salt"], b["salt"])
        self.assertNotEqual(
            ev.blob_name(ev.keys_from_keyfile(a, PASSPHRASE), REL),
            ev.blob_name(ev.keys_from_keyfile(b, PASSPHRASE), REL))

    def test_kdf_parameters_travel_with_the_brain(self):
        """A brain encrypted under old parameters still unlocks after the defaults rise."""
        kf = ev.new_keyfile(PASSPHRASE, n=1 << 11, r=8, p=1)
        self.assertEqual(kf["n"], 1 << 11)
        self.assertIsInstance(ev.keys_from_keyfile(kf, PASSPHRASE), ev.Keys)

    def test_unknown_kdf_or_version_is_refused(self):
        kf = ev.new_keyfile(PASSPHRASE, **CHEAP)
        for field, value in [("kdf", "pbkdf2"), ("v", 99)]:
            with self.subTest(field), self.assertRaises(ev.EncryptionError):
                ev.keys_from_keyfile({**kf, field: value}, PASSPHRASE)

    def test_save_and_load_round_trip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "enc" / "keyfile.json"
            kf = ev.new_keyfile(PASSPHRASE, hint="h", **CHEAP)
            ev.save_keyfile(kf, path)
            self.assertEqual(ev.load_keyfile(path), kf)

    def test_missing_keyfile_says_so(self):
        with self.assertRaises(ev.EncryptionError):
            ev.load_keyfile(Path("/nonexistent/enc/keyfile.json"))


class ShippedParametersTest(unittest.TestCase):
    """The defaults are a security property, so they are pinned rather than assumed."""

    def test_scrypt_cost_is_the_documented_one(self):
        self.assertEqual((ev.SCRYPT_N, ev.SCRYPT_R, ev.SCRYPT_P), (1 << 17, 8, 1))

    def test_maxmem_covers_the_shipped_cost(self):
        """128*N*r at the defaults is ~134 MB; OpenSSL caps at 32 MB unless told otherwise.

        Without this the shipped parameters do not merely run slowly — scrypt refuses to
        run at all, and only for the people using the defaults.
        """
        self.assertGreater(ev.SCRYPT_MAXMEM, 128 * ev.SCRYPT_N * ev.SCRYPT_R)

    def test_keys_are_purpose_separated(self):
        keys = cheap_keys()
        material = [keys.enc, keys.name, keys.hash, keys.verify]
        self.assertEqual(len(set(material)), 4)


if __name__ == "__main__":
    unittest.main()
