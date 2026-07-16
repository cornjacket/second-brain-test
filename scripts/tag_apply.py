#!/usr/bin/env python3
"""Backfill a tag rename/merge across the vault from an explicit mapping — the applier CLI.

This is the mechanical layer *after* the human judgment: tag_lint.py surfaces candidate
splits, a human decides the canonical form, and this applies that decision — nothing more.
It never infers a mapping; it rewrites exactly what the mapping file says, in frontmatter
`tags:` only, and is idempotent (re-running an applied mapping changes nothing).

    python3 scripts/tag_apply.py mapping.txt              # dry-run (default): show the diff
    python3 scripts/tag_apply.py mapping.txt --apply      # write the edits + stage them

Mapping file — one rename per line, `old -> new` (also `old: new` or `old = new`); blank
lines and `#` comments are ignored. A JSON object `{"old": "new", ...}` is accepted too.
A merge is just two olds pointing at one new; a note that would then carry the tag twice
is deduped.

On --apply the edited notes are written and `git add`-ed (only those notes — any other
working-tree changes are left untouched), but NOT committed: review the staged diff and
commit yourself. Pure stdlib.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import tag_hygiene  # noqa: E402

VAULT = REPO_ROOT / "vault"


def parse_mapping(text: str) -> dict[str, str]:
    """Parse a mapping file into `{old: new}`. JSON object, or `old -> new` lines."""
    stripped = text.strip()
    if stripped.startswith("{"):
        obj = json.loads(stripped)
        return {str(k): str(v) for k, v in obj.items()}
    mapping: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        for sep in ("->", ":", "="):
            if sep in line:
                old, new = line.split(sep, 1)
                break
        else:
            raise ValueError(f"line {lineno}: expected 'old -> new', got {raw!r}")
        old, new = old.strip(), new.strip()
        if not old or not new:
            raise ValueError(f"line {lineno}: empty old or new tag in {raw!r}")
        mapping[old] = new
    return mapping


def _git_add(paths: list[str]) -> str:
    """Stage exactly `paths` (vault-relative). Returns a one-line status for the report."""
    if not paths:
        return ""
    try:
        subprocess.run(["git", "add", "--", *paths], cwd=str(REPO_ROOT),
                       check=True, capture_output=True, text=True)
        return f"staged {len(paths)} note(s) (review with `git diff --staged`, then commit)"
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        return f"WARNING: could not stage the edited notes ({detail.strip()}); edits are on disk"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply a tag rename/merge mapping across the vault (dry-run by default).")
    parser.add_argument("mapping", help="mapping file: 'old -> new' lines, or a JSON object")
    parser.add_argument("--apply", action="store_true",
                        help="write the edits (default is a dry-run that changes nothing)")
    args = parser.parse_args(argv)

    mapping = parse_mapping(Path(args.mapping).read_text(encoding="utf-8"))
    if not mapping:
        print("mapping is empty — nothing to do")
        return 0

    changes = tag_hygiene.apply_mapping(VAULT, mapping, dry_run=not args.apply)
    mode = "APPLIED" if args.apply else "DRY-RUN (no files changed)"
    print(f"{mode} — mapping: " + ", ".join(f"{o} -> {n}" for o, n in mapping.items()))
    if not changes:
        print("no note needed a change (already consistent, or the mapping matched nothing)")
        return 0

    for c in changes:
        print(f"  {c.note}: [{', '.join(c.old)}] -> [{', '.join(c.new)}]")
    print(f"{len(changes)} note(s) " + ("edited" if args.apply else "would change"))

    if args.apply:
        status = _git_add([f"vault/{c.note}" for c in changes])
        if status:
            print(status)
    else:
        print("re-run with --apply to write these edits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
