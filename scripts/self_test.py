#!/usr/bin/env python3
"""Deterministic pipeline self-test — the structural tier (see tests/README.md).

Re-embeds every note in ``tests/fixtures/vault/`` with the deterministic ``test``
backend and byte-compares the result against the committed expected sidecar. A
clean match proves the embed pipeline is intact and reproducible **on this
machine** — with no model, network, or Ollama required. This ships with every
generated brain as its built-in "is my pipeline wired correctly?" check.

Exit ``0`` = all fixtures match; non-zero = drift (prints which note diverged).

    python3 scripts/self_test.py
"""
from __future__ import annotations

import os
import sys

# Fixtures are byte-diffable test-backend vectors — force it regardless of env.
os.environ["SECOND_BRAIN_EMBEDDER"] = "test"

from pathlib import Path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "vault"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import embed_staged as es  # noqa: E402


def expected_sidecar(note: Path) -> Path:
    return note.parent / f".{note.stem}.embed.json"


def check_link_invariance() -> int:
    """A wikilink must not change what gets embedded (returns the failure count).

    Link markup is not substance: `[[ablation]]` and `ablation` say the same thing. If they
    hashed differently, auto-linking a term across the vault would re-embed every note it
    touched for a change that carries no meaning — and the system's own output would be
    feeding back into its own vectors. Cheap to assert, so every brain checks it.
    """
    from note_view import content_hash

    plain = "# N\n\nAn ablation of the corpus.\n"
    cases = {
        "[[term]]":            "# N\n\nAn [[ablation]] of the corpus.\n",
        "[[slug|surface]]":    "# N\n\nAn [[abl-study|ablation]] of the [[corpus]].\n",
        "![[embed]]":          "# N\n\nAn ![[ablation]] of the corpus.\n",
    }
    failures = 0
    for label, linked in cases.items():
        if content_hash(linked) != content_hash(plain):
            print(f"  DRIFT    link-invariance: {label} changed the embed input — a link "
                  f"insertion would needlessly re-embed the note")
            failures += 1
    if content_hash(plain + "Extra prose.\n") == content_hash(plain):
        print("  DRIFT    link-invariance: a REAL prose edit did not change the hash — the "
              "no-op gate would skip an embed it must perform")
        failures += 1
    if not failures:
        print("  ok       link-invariance: links don't re-embed; prose edits do")
    return failures


def main() -> int:
    notes = sorted(FIXTURES.rglob("*.md"))
    if not notes:
        print(f"self-test: no fixtures under {FIXTURES.relative_to(REPO_ROOT)}",
              file=sys.stderr)
        return 1

    failures = check_link_invariance()
    for note in notes:
        rel = note.relative_to(REPO_ROOT).as_posix()
        exp = expected_sidecar(note)
        if not exp.exists():
            print(f"  MISSING  {rel} — no committed sidecar {exp.name}")
            failures += 1
            continue
        got = es.sidecar_bytes(rel)
        if got == exp.read_text(encoding="utf-8"):
            print(f"  ok       {rel}")
        else:
            print(f"  DRIFT    {rel} — regenerated vector != committed sidecar")
            failures += 1

    total = len(notes)
    if failures:
        print(f"self-test FAILED: {failures}/{total} fixture(s) drifted")
        return 1
    print(f"self-test OK: {total}/{total} fixtures reproduce byte-for-byte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
