#!/usr/bin/env python3
"""Encrypt this brain's notes at rest, so a git remote holds nothing readable.

A brain backed by a git remote pushes every note, in the clear, to a server you do
not own. With encryption enabled the *committed* form is unreadable — **bodies and
filenames both** — while the working tree stays exactly as it is: plaintext ``.md``
files that Obsidian opens, ``search_vault.py`` searches and the embedder embeds.

**Encryption is a git-layer concern, not a note-layer one.** Nothing about how a note
is written, embedded, linked or searched changes. What changes is what git may see.

This module is the *mechanism* — keys, names, envelope. It reads and writes bytes and
knows nothing about git, the working tree, or the feature toggle; the migration and
the hook wiring live above it. Keeping it that way is what makes it testable without
a repository.

Layout::

    vault/projects/kitchen-remodel.md     the working tree — plaintext, git-ignored
    enc/JBSWY3DPEHPK3PXPKRUG.md.enc       what git tracks — opaque name, opaque bytes
    enc/keyfile.json                      KDF salt, verifier tag, optional hint

The opaque name is ``HMAC(k_name, <relative path>)``: **keyed**, so nobody without the
passphrase can test whether this brain holds ``salary-negotiation.md``;
**deterministic**, so an unchanged note keeps its name commit after commit and produces
no diff. It is **not reversible** — and does not need to be, because the plaintext path
travels inside the envelope, prefixed to the note before encryption and stripped after,
so a restore is byte-identical and no manifest file is needed. (A single mapping file
would conflict on every concurrent commit of a two-machine brain and, being ciphertext,
could not be merged.)

Four keys are derived from the passphrase, one per purpose, so no key is ever used for
two things: ``enc`` (AES-256-GCM), ``name`` (the HMAC above), ``hash`` (the plaintext
digest that suppresses churn) and ``verify`` (the "is this passphrase right?" tag).

``phash`` is what keeps the diff quiet. AES-GCM uses a random nonce, so re-encrypting an
unchanged note would produce different bytes and re-diff the whole vault on every commit.
The header carries an HMAC of the plaintext, and a caller **skips any note whose
substance is unchanged** — the same skip-gate shape the embed path already uses for
``content_hash``.

Requires ``cryptography`` (``requirements-crypt.txt``) — an *optional* dependency, in the
same way ``pypdf`` is optional for PDF ingestion. A brain that never enables encryption
never installs it. Python's standard library has no AES, and rolling one is not on the
table; ``hashlib.scrypt`` and ``hmac`` cover everything else.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENC_DIR = REPO_ROOT / "enc"
KEYFILE_PATH = ENC_DIR / "keyfile.json"

# --- envelope ----------------------------------------------------------------
FORMAT_VERSION = 1
MAGIC = b"SBE1"          # authenticated as AAD, so a truncated/foreign file fails loudly
NONCE_LEN = 12           # AES-GCM standard nonce
SUFFIX = ".md.enc"       # NOT .mdx: that is a real format (Markdown+JSX) and every
                         # editor would mis-highlight it. The double extension also keeps
                         # the ignore rule an exact glob — `*.md` never matches this.
NAME_CHARS = 32          # base32 chars of the name HMAC → 160 bits, no truncation collisions

# --- KDF ---------------------------------------------------------------------
# Deliberately expensive. The keyfile is committed, so salt + verifier make offline
# brute force possible by construction; the scrypt cost is the entire defense.
SCRYPT_N = 1 << 17
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LEN = 32
# 128 * N * r ≈ 134 MB at the defaults above. OpenSSL's built-in cap is 32 MB, so it
# must be raised explicitly or scrypt() fails rather than runs slow — an easy thing to
# discover only when someone with the defaults tries to unlock their brain.
SCRYPT_MAXMEM = 1 << 29

_INFO_ENC = b"second-brain/v1/enc"
_INFO_NAME = b"second-brain/v1/name"
_INFO_HASH = b"second-brain/v1/hash"
_INFO_VERIFY = b"second-brain/v1/verify"
_VERIFY_MESSAGE = b"second-brain/v1/keyfile"


class EncryptionError(Exception):
    """Base for every failure this module raises."""


class WrongPassphrase(EncryptionError):
    """The passphrase does not match the keyfile's verifier."""


class EnvelopeError(EncryptionError):
    """A blob is not a well-formed envelope, or does not authenticate."""


@dataclass(frozen=True)
class Keys:
    """The four purpose-separated keys derived from one passphrase."""
    enc: bytes
    name: bytes
    hash: bytes
    verify: bytes


def _aesgcm(key: bytes):
    """Import AES-GCM lazily, so a brain without encryption never needs the dependency."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - exercised by the doctor path
        raise EncryptionError(
            "encryption needs the 'cryptography' package: pip install -r requirements-crypt.txt"
        ) from exc
    return AESGCM(key)


def _hkdf_expand(prk: bytes, info: bytes, length: int = KEY_LEN) -> bytes:
    """HKDF-Expand (RFC 5869) over SHA-256.

    No extract step: scrypt's output is already a uniformly random key, which is
    exactly the input HKDF-Expand assumes. Written against ``hmac`` rather than pulled
    from the crypto library so the dependency surface stays at "AES, and nothing else".
    """
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def derive_keys(passphrase: str, salt: bytes, *, n: int = SCRYPT_N,
                r: int = SCRYPT_R, p: int = SCRYPT_P) -> Keys:
    """Stretch a passphrase into the four purpose-separated keys.

    ``n``/``r``/``p`` come from the keyfile rather than from these defaults, so a brain
    encrypted years ago still unlocks after the defaults are raised.
    """
    root = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                          dklen=KEY_LEN, maxmem=SCRYPT_MAXMEM)
    return Keys(
        enc=_hkdf_expand(root, _INFO_ENC),
        name=_hkdf_expand(root, _INFO_NAME),
        hash=_hkdf_expand(root, _INFO_HASH),
        verify=_hkdf_expand(root, _INFO_VERIFY),
    )


def verify_tag(keys: Keys) -> str:
    """The tag stored in the keyfile, proving a passphrase without revealing it."""
    return hmac.new(keys.verify, _VERIFY_MESSAGE, hashlib.sha256).hexdigest()


def new_keyfile(passphrase: str, *, hint: str | None = None, n: int = SCRYPT_N,
                r: int = SCRYPT_R, p: int = SCRYPT_P) -> dict:
    """Build the committed keyfile for a fresh brain. Contains no secret.

    The ``hint`` is optional free text and is **readable by anyone who can read the
    repo** — a hint good enough to remind you may be good enough to narrow a guess, and
    it must never be a function of the passphrase itself.
    """
    salt = secrets.token_bytes(16)
    keys = derive_keys(passphrase, salt, n=n, r=r, p=p)
    kf = {
        "v": FORMAT_VERSION,
        "kdf": "scrypt",
        "n": n, "r": r, "p": p,
        "salt": base64.b64encode(salt).decode("ascii"),
        "verify": verify_tag(keys),
    }
    if hint:
        kf["hint"] = hint
    return kf


def keys_from_keyfile(keyfile: dict, passphrase: str) -> Keys:
    """Derive the keys and confirm the passphrase, or raise ``WrongPassphrase``.

    This is the check that makes a typo legible. Without it a wrong passphrase produces
    N unintelligible authentication failures, one per note, instead of one clear answer
    — and it costs a single KDF pass, before any note is touched.
    """
    if keyfile.get("kdf") != "scrypt":
        raise EncryptionError(f"unsupported kdf: {keyfile.get('kdf')!r}")
    if keyfile.get("v") != FORMAT_VERSION:
        raise EncryptionError(f"unsupported keyfile version: {keyfile.get('v')!r}")
    salt = base64.b64decode(keyfile["salt"])
    keys = derive_keys(passphrase, salt, n=keyfile["n"], r=keyfile["r"], p=keyfile["p"])
    if not hmac.compare_digest(verify_tag(keys), keyfile["verify"]):
        raise WrongPassphrase("wrong passphrase for this brain")
    return keys


def load_keyfile(path: Path = KEYFILE_PATH) -> dict:
    """Read the committed keyfile."""
    try:
        with path.open("rb") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise EncryptionError(f"no keyfile at {path} — is encryption enabled here?") from exc
    except json.JSONDecodeError as exc:
        raise EncryptionError(f"keyfile at {path} is not valid JSON: {exc}") from exc


def save_keyfile(keyfile: dict, path: Path = KEYFILE_PATH) -> None:
    """Write the keyfile, creating ``enc/`` if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keyfile, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def canonical_rel(rel: str | Path) -> str:
    """Normalize a brain-relative note path to the form the name HMAC is taken over.

    The name is a function of this string, so two spellings of one path (``./a/b.md``,
    ``a//b.md``, a Windows separator) must not produce two different blobs for one note.
    """
    text = str(rel).replace("\\", "/")
    parts = [seg for seg in text.split("/") if seg not in ("", ".")]
    if not parts or ".." in parts:
        raise EncryptionError(f"not a brain-relative note path: {rel!r}")
    if Path(text).is_absolute():
        raise EncryptionError(f"path must be relative to the brain root: {rel!r}")
    return "/".join(parts)


def blob_name(keys: Keys, rel: str | Path) -> str:
    """The committed filename for a note — keyed, deterministic, not reversible."""
    tag = hmac.new(keys.name, canonical_rel(rel).encode("utf-8"), hashlib.sha256).digest()
    return base64.b32encode(tag).decode("ascii").rstrip("=")[:NAME_CHARS] + SUFFIX


def plaintext_hash(keys: Keys, body: bytes) -> str:
    """Keyed digest of a note's bytes — the skip-gate that keeps the diff quiet.

    Keyed rather than a bare SHA-256 so the committed header cannot be used to confirm a
    guessed note ("is this brain's note exactly this text?").
    """
    return hmac.new(keys.hash, body, hashlib.sha256).hexdigest()


def encrypt_note(keys: Keys, rel: str | Path, body: bytes) -> bytes:
    """Encrypt one note into its committed envelope.

    The header is prefixed to the body **before** encryption and stripped after, so the
    restored file is byte-identical to what was written and the path never exists on
    disk in plaintext outside the working tree.
    """
    path = canonical_rel(rel)
    header = {"v": FORMAT_VERSION, "path": path, "phash": plaintext_hash(keys, body)}
    payload = json.dumps(header, sort_keys=True).encode("utf-8") + b"\n" + body
    nonce = secrets.token_bytes(NONCE_LEN)
    return MAGIC + nonce + _aesgcm(keys.enc).encrypt(nonce, payload, MAGIC)


def decrypt_note(keys: Keys, blob: bytes) -> tuple[str, bytes]:
    """Decrypt an envelope back into ``(relative path, body)``."""
    if not blob.startswith(MAGIC):
        raise EnvelopeError("not a second-brain envelope (bad magic)")
    nonce = blob[len(MAGIC):len(MAGIC) + NONCE_LEN]
    ciphertext = blob[len(MAGIC) + NONCE_LEN:]
    if len(nonce) != NONCE_LEN or not ciphertext:
        raise EnvelopeError("truncated envelope")
    try:
        payload = _aesgcm(keys.enc).decrypt(nonce, ciphertext, MAGIC)
    except EncryptionError:
        raise
    except Exception as exc:  # InvalidTag, and anything else the backend raises
        raise EnvelopeError("envelope failed to authenticate — wrong key or altered file") from exc
    head, sep, body = payload.partition(b"\n")
    if not sep:
        raise EnvelopeError("envelope has no header")
    try:
        header = json.loads(head)
    except json.JSONDecodeError as exc:
        raise EnvelopeError(f"envelope header is not valid JSON: {exc}") from exc
    if header.get("v") != FORMAT_VERSION:
        raise EnvelopeError(f"unsupported envelope version: {header.get('v')!r}")
    return canonical_rel(header["path"]), body


def envelope_header(keys: Keys, blob: bytes) -> dict:
    """The header of an envelope, without keeping the body.

    Authentication covers the whole envelope, so this decrypts all of it — there is no
    cheaper honest way to read an authenticated header. Notes are kilobytes; a whole
    vault costs milliseconds.
    """
    path, body = decrypt_note(keys, blob)
    return {"v": FORMAT_VERSION, "path": path, "phash": plaintext_hash(keys, body)}


def is_unchanged(keys: Keys, blob: bytes, body: bytes) -> bool:
    """Does an existing blob already hold exactly ``body``? (the churn skip-gate)"""
    try:
        _, existing = decrypt_note(keys, blob)
    except EnvelopeError:
        return False
    return hmac.compare_digest(plaintext_hash(keys, existing), plaintext_hash(keys, body))


def blob_path(keys: Keys, rel: str | Path, root: Path = REPO_ROOT) -> Path:
    """Where a note's committed blob lives."""
    return root / "enc" / blob_name(keys, rel)


def encrypt_file(keys: Keys, rel: str | Path, root: Path = REPO_ROOT) -> tuple[Path, bool]:
    """Write a note's blob; return ``(path, wrote)``.

    Skips when the existing blob already holds exactly these bytes, which is what keeps a
    commit from re-diffing the entire vault: AES-GCM's random nonce means re-encrypting an
    unchanged note would otherwise produce different ciphertext every time.
    """
    rel = canonical_rel(rel)
    body = (root / rel).read_bytes()
    dest = blob_path(keys, rel, root)
    if dest.exists() and is_unchanged(keys, dest.read_bytes(), body):
        return dest, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(encrypt_note(keys, rel, body))
    return dest, True


def needs_encrypting(keys: Keys, rel: str | Path, root: Path = REPO_ROOT) -> bool:
    """Does this note differ from the blob already committed for it?

    With the vault git-ignored, git can no longer answer "what changed" — so this is the
    change detector the commit path uses in its place. A note with no blob at all counts
    as changed, which is what makes the first encrypted commit pick up the whole vault.
    """
    dest = blob_path(keys, rel, root)
    if not dest.exists():
        return True
    return not is_unchanged(keys, dest.read_bytes(), (root / canonical_rel(rel)).read_bytes())


def orphan_blobs(keys: Keys, rel_paths, existing_names) -> set[str]:
    """Blob names with no live note behind them — deletions and the old half of a rename.

    Set difference over names, with **nothing decrypted**: the name is a pure function of
    the path, so every live note's blob name can simply be computed. A deleted note's
    blob is whatever is left over.
    """
    live = {blob_name(keys, rel) for rel in rel_paths}
    return {name for name in existing_names if name.endswith(SUFFIX)} - live
