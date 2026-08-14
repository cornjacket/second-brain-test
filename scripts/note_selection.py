#!/usr/bin/env python3
"""Which notes does this commit have to work on? — one answer, shared by every caller.

Three separate places used to ask git the same question in the same words::

    git diff --cached --name-only --diff-filter=ACM -- '*.md'

That is correct exactly as long as notes are tracked files. Turn encryption on and the
vault becomes git-ignored, so git stages no note, so that command returns nothing — and
every caller quietly does nothing at all. Not an error; an empty list. The pre-commit
hook still exits 0, the note still commits, and it is simply never embedded again.

This is the failure mode where **the test does not break, its window does**: the logic is
fine, it is pointed at a view that no longer contains the subject. The fix is not to
patch three copies of the query, it is to stop asking git a question git can no longer
answer, in one place that every caller shares.

  * **encryption off** — what git staged. Byte-for-byte today's behaviour.
  * **encryption on** — the working tree is the only witness left, so selection becomes
    "notes whose plaintext differs from the blob already committed for them", which is
    the same comparison the encryptor uses to decide what to re-encrypt.

When encryption is on and the passphrase cannot be found, this **raises**. It must: the
alternative is returning an empty list, which is indistinguishable from "nothing changed"
and reproduces the exact bug this module exists to prevent.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import encryption  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = "vault"
PARA_ROOTS = ("projects", "areas", "resources", "archive")


def _is_note(rel: str, roots: tuple[str, ...]) -> bool:
    """A Markdown note under ``vault/<root>/…`` — the shape both hooks care about."""
    if not rel.endswith(".md"):
        return False
    parts = rel.split("/")
    return len(parts) >= 3 and parts[0] == VAULT_DIR and parts[1] in roots


def staged_notes(roots: tuple[str, ...] = PARA_ROOTS, root: Path = REPO_ROOT) -> list[str]:
    """Notes git has staged (added/copied/modified). The plaintext-brain answer."""
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if _is_note(line, roots)]


def all_notes(roots: tuple[str, ...] = PARA_ROOTS, root: Path = REPO_ROOT) -> list[str]:
    """Every note in the working tree under the given roots, sorted."""
    notes: list[str] = []
    for name in roots:
        base = root / VAULT_DIR / name
        if base.is_dir():
            notes += [p.relative_to(root).as_posix() for p in base.rglob("*.md")]
    return sorted(notes)


def unencrypted_notes(roots: tuple[str, ...] = PARA_ROOTS, root: Path = REPO_ROOT) -> list[str]:
    """Notes whose plaintext differs from the blob committed for them. The encrypted answer."""
    import encrypt_vault as ev
    import passphrase as pp

    keys = ev.keys_from_keyfile(ev.load_keyfile(root / "enc" / "keyfile.json"), pp.resolve(root))
    return [rel for rel in all_notes(roots, root) if ev.needs_encrypting(keys, rel, root)]


def notes_for_commit(roots: tuple[str, ...] = PARA_ROOTS, root: Path = REPO_ROOT) -> list[str]:
    """The notes this commit must process, whichever mode the brain is in."""
    if encryption():
        return unencrypted_notes(roots, root)
    return staged_notes(roots, root)


if __name__ == "__main__":
    # Printed one per line for the pre-commit hook, which is shell and cannot import this.
    print("\n".join(notes_for_commit()))
