#!/usr/bin/env python3
"""Pre-commit helper: (re)generate ``.embed.json`` sidecars for staged notes.

For every staged Markdown note under the PARA roots, compute its embedding and
write the sidecar ``<dir>/.<stem>.embed.json``, then stage the sidecar so it
lands in the same commit. This keeps the machine-readable vectors in lockstep
with the human-authored Markdown — "write for humans, index for machines".

See SPEC.md §5.1.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from embedder import embed  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
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
        if line.split("/", 1)[0] in PARA_ROOTS:
            notes.append(line)
    return notes


def sidecar_path(note: str) -> Path:
    p = Path(note)
    return REPO_ROOT / p.parent / f".{p.stem}.embed.json"


def write_sidecar(note: str) -> Path:
    text = (REPO_ROOT / note).read_text(encoding="utf-8")
    payload = {"source_file": note, "vector": embed(text)}
    dest = sidecar_path(note)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


def main() -> int:
    notes = staged_notes()
    for note in notes:
        dest = write_sidecar(note)
        subprocess.run(["git", "add", str(dest)], cwd=REPO_ROOT, check=True)
        print(f"  embed: {note} -> {dest.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
