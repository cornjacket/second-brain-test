#!/usr/bin/env python3
"""Embed every PARA note in the vault (bulk), refreshing their ``.embed.json`` sidecars.

The pre-commit hook (``embed_staged.py``) only embeds the notes *staged* in a
commit. This embeds the **whole vault** in one pass — needed when the hook can't:

- **first-time setup** of a freshly seeded brain (the seed notes are already
  committed, so nothing is staged for the hook to embed);
- after a **bulk edit** or import of many notes;
- when **switching backends** (e.g. ``test`` → ``ollama``), to re-embed every note
  with the new model so the whole vault is comparable again.

Follow it with ``hydrate_cache.py`` to rebuild the searchable cache:

    python3 scripts/embed_vault.py                              # active backend (test by default)
    SECOND_BRAIN_EMBEDDER=ollama python3 scripts/embed_vault.py  # real semantic vectors
    python3 scripts/hydrate_cache.py                            # then rebuild the cache

Vault sidecars are **derived and git-ignored** (regenerated locally, never
committed). This reuses the exact sidecar format the pre-commit hook writes, so
bulk- and incremental-embedding stay identical.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from embedder import backend_id  # noqa: E402
from embed_staged import write_sidecar  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = REPO_ROOT / "vault"
PARA_ROOTS = ("projects", "areas", "resources", "archive")


def vault_notes() -> list[str]:
    """Every Markdown note under vault/<para-root>/, as repo-relative POSIX paths."""
    notes: list[str] = []
    for root in PARA_ROOTS:
        base = VAULT_DIR / root
        if base.exists():
            notes += [p.relative_to(REPO_ROOT).as_posix() for p in base.rglob("*.md")]
    return sorted(notes)


def main() -> int:
    notes = vault_notes()
    if not notes:
        print("embed_vault: no notes under vault/<para-root>/", file=sys.stderr)
        return 1
    backend = backend_id()
    for note in notes:
        dest, wrote = write_sidecar(note)
        if wrote:
            print(f"  embed: {note} -> {dest.relative_to(REPO_ROOT)} ({backend})")
        else:
            print(f"  skip (unchanged): {note}")
    print(f"embedded {len(notes)} note(s) with backend '{backend}' — "
          f"run scripts/hydrate_cache.py to rebuild the cache")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
