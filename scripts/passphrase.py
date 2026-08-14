#!/usr/bin/env python3
"""Find this machine's passphrase for an encrypted brain — a file, never a prompt.

Resolution order, highest first::

    SECOND_BRAIN_PASSPHRASE                     env var, for one command
    git config secondbrain.passphrasefile       a path you chose, per machine
    ~/.config/second-brain/keys/<name>-<id>.key the default

**The brain identifies itself; the folder does not.** ``id`` (random) and ``name`` live in
the committed ``enc/keyfile.json``, so the key file has the same name on every machine that
clones this brain — no matter what the local directory is called. Lookup matches on the
**id** alone; the name is there so a directory of keys is readable by a human. That fixes
both halves of the obvious folder-based scheme: two brains whose folders share a name would
have shared one key file, and one brain cloned to two paths would have looked for two.

Keys sit in their own ``keys/`` subdirectory rather than beside other configuration, so
"never sync this, and keep it 0600" is expressible as one rule about one directory.

**Nothing here ever reads stdin.** The MCP server runs headless under Claude Desktop, and
a server that blocks waiting for input does not ask a question — it hangs, forever, with
no way for the user to answer it. The same code path runs in a pre-commit hook, which is
just as unable to hold a conversation. So a missing passphrase is an *error with
instructions*, never a prompt.

The default location is **outside the repo** on purpose. A secret inside the working tree
is one ``git add -f``, one careless ``.gitignore`` edit, or one "commit everything" away
from the remote — which is the exact failure the encryption exists to prevent. Putting it
somewhere git cannot reach makes that mistake unavailable rather than merely discouraged.

``secondbrain.passphrasefile`` is per-machine and uncommitted, the same shape
``secondbrain.autosync`` already uses.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

KEYS_DIR = Path.home() / ".config" / "second-brain" / "keys"
ENV_VAR = "SECOND_BRAIN_PASSPHRASE"
GIT_CONFIG_KEY = "secondbrain.passphrasefile"


class PassphraseError(Exception):
    """The passphrase could not be found — the message says how to fix it."""


def brain_identity(root: Path = REPO_ROOT) -> tuple[str | None, str]:
    """``(id, name)`` from the committed keyfile; the folder name if it has neither.

    Read as plain JSON rather than through ``encrypt_vault`` so that finding a passphrase
    never requires the optional cipher dependency — a brain can be asked where its key
    lives without being able to decrypt anything.
    """
    try:
        keyfile = json.loads((root / "enc" / "keyfile.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, root.resolve().name
    return keyfile.get("id"), keyfile.get("name") or root.resolve().name


def default_path(root: Path = REPO_ROOT) -> Path:
    """Where this brain's key file lives if nothing else says otherwise.

    A brain with no id — one encrypted before ids existed — keeps the old folder-derived
    path, so an existing setup is not silently told its passphrase has gone missing.
    """
    brain_id, name = brain_identity(root)
    if brain_id:
        return KEYS_DIR / f"{name}-{brain_id}.key"
    return Path.home() / ".config" / "second-brain" / f"{name}.key"


def find_key_file(root: Path = REPO_ROOT) -> Path | None:
    """This brain's key file wherever it actually is, or None.

    Matches on the **id**, so a key written before the brain (or its folder) was renamed is
    still found — the readable half of the filename is allowed to go stale.
    """
    brain_id, _ = brain_identity(root)
    if brain_id and KEYS_DIR.is_dir():
        matches = sorted(KEYS_DIR.glob(f"*{brain_id}.key"))
        if matches:
            return matches[0]
    fallback = default_path(root)
    return fallback if fallback.exists() else None


def configured_path(root: Path = REPO_ROOT) -> Path | None:
    """The path in ``git config secondbrain.passphrasefile``, if set."""
    try:
        out = subprocess.run(["git", "config", "--get", GIT_CONFIG_KEY],
                             cwd=root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    value = out.stdout.strip()
    return Path(value).expanduser() if value else None


def is_inside_repo(path: Path, root: Path = REPO_ROOT) -> bool:
    """Is this key file inside the brain, where a stray ``git add`` could reach it?"""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def read_key_file(path: Path) -> str:
    """Read a passphrase from ``path``, warning if the file is world-readable.

    The permission check warns rather than refuses: a passphrase the tool declines to use
    is a brain the user cannot open, and locking someone out of their own notes is the
    worse outcome of the two.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PassphraseError(f"cannot read the passphrase file at {path}: {exc}") from exc
    try:
        mode = path.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            print(f"  ⚠️  {path} is readable by other users — chmod 600 it.")
    except OSError:
        pass
    passphrase = text.strip("\n")
    if not passphrase.strip():
        raise PassphraseError(f"the passphrase file at {path} is empty")
    return passphrase


def resolve(root: Path = REPO_ROOT) -> str:
    """This machine's passphrase for the brain at ``root``, or a ``PassphraseError``."""
    env = os.environ.get(ENV_VAR)
    if env and env.strip():
        return env.strip("\n")

    configured = configured_path(root)
    if configured is not None:
        if not configured.exists():
            raise PassphraseError(
                f"git config {GIT_CONFIG_KEY} points at {configured}, which does not exist. "
                f"Create it, or repoint it with: git config {GIT_CONFIG_KEY} <path>")
        return read_key_file(configured)

    found = find_key_file(root)
    if found is not None:
        return read_key_file(found)

    raise PassphraseError(
        f"no passphrase for this brain. Set one of:\n"
        f"  {ENV_VAR}=<passphrase>              (one command)\n"
        f"  {default_path(root)}                (default file, chmod 600)\n"
        f"  git config {GIT_CONFIG_KEY} <path>  (a location you choose)")
