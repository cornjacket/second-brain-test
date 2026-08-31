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
from note_selection import notes_for_commit  # noqa: E402
from note_view import (  # noqa: E402
    EMBED_TOKEN_BUDGET, NO_EMBED_BEGIN, NO_EMBED_END,
    canonical_body, content_hash, embed_excluded, estimate_tokens, has_unpaired_no_embed,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = "vault"
PARA_ROOTS = ("projects", "areas", "resources", "archive")


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


def warn_embed_input(note: str) -> None:
    """Print (never raise) anything wrong with what ``note`` is about to embed as.

    Both warnings describe the *canonical view*, not the file, because that is what the
    model sees — and both are advisory: the commit proceeds either way, since a note the
    hook refuses is a note the user cannot save.

    - **Unpaired marker** — a ``no-embed`` block that never closes excludes nothing, so
      the art the human fenced off is embedded anyway. Silent without this: the note
      commits and searches fine, just polluted.
    - **Over the token budget** — the note is close enough to the embedder's context that
      the embed may fail outright. Said *here* rather than left to the backend's
      ``input length exceeds the context length`` error, because this message can name
      the fix.
    """
    text = (REPO_ROOT / note).read_text(encoding="utf-8")
    if has_unpaired_no_embed(text):
        print(f"  ⚠️  {note}: a no-embed marker has no partner — nothing was excluded. "
              f"Pair {NO_EMBED_BEGIN} with {NO_EMBED_END}.")
    tokens = estimate_tokens(canonical_body(text))
    if tokens > EMBED_TOKEN_BUDGET:
        print(f"  ⚠️  {note}: ~{tokens} tokens of embed input (budget {EMBED_TOKEN_BUDGET}) — "
              f"the embed may fail. Fence decorative regions (diagrams, ASCII art, wide "
              f"tables) in a no-embed block, or split the note.")


def drop_sidecar(note: str) -> bool:
    """Remove ``note``'s sidecar if it has one; return whether anything was deleted.

    Adding ``embed: false`` to a file that was **already embedded** must retract the vector,
    not merely stop refreshing it. Left in place, the stale sidecar keeps being hydrated into
    the cache, so the file goes on answering searches while its frontmatter says it is not a
    note — the exclusion would appear to work and silently not.
    """
    dest = sidecar_path(note)
    if not dest.exists():
        return False
    dest.unlink()
    return True


def main() -> int:
    # Vault sidecars are derived + git-ignored: refresh them locally, never commit.
    # The note list comes from note_selection, NOT from `git diff --cached`: with
    # encryption on the vault is git-ignored, so asking git what is staged returns
    # nothing and every note silently stops being embedded.
    for note in notes_for_commit():
        if embed_excluded((REPO_ROOT / note).read_text(encoding="utf-8")):
            if drop_sidecar(note):
                print(f"  embed: false -> {note} (excluded; stale sidecar removed)")
            else:
                print(f"  embed: false -> {note} (excluded, not a note)")
            continue
        warn_embed_input(note)
        dest, wrote = write_sidecar(note)
        if wrote:
            print(f"  embed: {note} -> {dest.relative_to(REPO_ROOT)} (derived, not committed)")
        else:
            print(f"  skip (substance unchanged): {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
