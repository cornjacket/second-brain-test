#!/usr/bin/env python3
"""Pre-commit helper: (re)generate ``.embed.json`` sidecars for staged notes.

For every staged Markdown note under the vault's PARA roots, compute its
embedding and write the **derived** sidecar ``<dir>/.<stem>.embed.json``, keeping
the machine-readable vectors in lockstep with the human-authored Markdown.

Vault sidecars are **derived and git-ignored** — this hook refreshes them locally
so the cache can be rebuilt; it does **not** commit them. (Only the deterministic
``tests/fixtures/vault`` sidecars are committed — see tests/README.md.)
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from embedder import backend_id, embed, is_deterministic  # noqa: E402
from note_view import canonical_body, content_hash  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = "vault"
PARA_ROOTS = ("projects", "areas", "resources", "archive")


def staged_notes() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    notes = []
    for line in out.splitlines():
        if not line.endswith(".md"):
            continue
        # Only embed notes under vault/<para-root>/… (e.g. vault/areas/foo.md).
        parts = line.split("/")
        if len(parts) >= 3 and parts[0] == VAULT_DIR and parts[1] in PARA_ROOTS:
            notes.append(line)
    return notes


def sidecar_path(note: str) -> Path:
    p = Path(note)
    return REPO_ROOT / p.parent / f".{p.stem}.embed.json"


def sidecar_bytes(note: str) -> str:
    """Render a note's sidecar JSON exactly as written to disk.

    ``type`` stamps the embedder that produced the vector (so mixing is
    detectable). ``embedded_at`` is added only for **non-deterministic** backends
    — deterministic (``test``) sidecars stay byte-stable so the committed fixtures
    and the self-test byte-diff cleanly.

    The embedder sees the note's **canonical substance view** (body only, no
    frontmatter — see note_view.py), so metadata never enters the vector.
    """
    text = (REPO_ROOT / note).read_text(encoding="utf-8")
    payload = {"source_file": note, "type": backend_id(),
               "content_hash": content_hash(text),
               "vector": embed(canonical_body(text), task="document")}
    if not is_deterministic():
        payload["embedded_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    return json.dumps(payload, indent=2) + "\n"


def write_sidecar(note: str, force: bool = False) -> tuple[Path, bool]:
    """Write ``note``'s ``.embed.json`` sidecar; return ``(path, wrote)``.

    No-op gate: if a sidecar already exists whose ``content_hash`` matches the note's
    current substance **and** was produced by the active backend, the vector cannot have
    changed, so skip the re-embed (with Ollama, re-embedding unchanged text would only
    churn the sidecar with fresh floating-point noise). This is also what stops an
    auto-linker's ``related_auto:`` frontmatter edit from triggering a re-embed — the body
    is unchanged, so the hash is unchanged. ``force`` bypasses the gate; ``doctor
    --repair`` uses it to rewrite even a hash-matching but corrupt sidecar.
    """
    dest = sidecar_path(note)
    if not force and dest.exists():
        try:
            prev = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = {}
        text = (REPO_ROOT / note).read_text(encoding="utf-8")
        if prev.get("type") == backend_id() and prev.get("content_hash") == content_hash(text):
            return dest, False
    dest.write_text(sidecar_bytes(note), encoding="utf-8")
    return dest, True


def main() -> int:
    # Vault sidecars are derived + git-ignored: refresh them locally, never commit.
    for note in staged_notes():
        dest, wrote = write_sidecar(note)
        if wrote:
            print(f"  embed: {note} -> {dest.relative_to(REPO_ROOT)} (derived, not committed)")
        else:
            print(f"  skip (substance unchanged): {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
