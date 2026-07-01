#!/usr/bin/env python3
"""Seed (or reset) the PARA vault from the canonical seed set (Task 0003).

``seeds/<para>/`` holds the canonical, committed baseline notes. This script
copies them into ``vault/<para>/`` so the vault can be (re)generated from a known
state — useful for repeatable, deterministic pipeline tests (wipe → re-seed →
embed → hydrate → search).

    python3 scripts/seed_vault.py                 # copy seeds/ -> vault/ (idempotent)
    python3 scripts/seed_vault.py --wipe          # dry run: show what --wipe would delete
    python3 scripts/seed_vault.py --wipe --force  # delete vault PARA notes+sidecars, then re-seed

Safety: ``--wipe`` only ever removes ``*.md`` and ``.*.embed.json`` **under the
four PARA roots inside** ``vault/``. It never touches ``vault/.obsidian/``,
``config/``, ``data/``, ``.gitkeep``, or any non-note file, and never removes
directories. A wipe requires ``--force``; without it the script prints what it
would delete and exits (dry run).

Pure stdlib; no dependency on the embedder/cache pipeline.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEEDS_DIR = REPO_ROOT / "seeds"
VAULT_DIR = REPO_ROOT / "vault"
PARA_ROOTS = ("projects", "areas", "resources", "archive")


def wipe_targets() -> list[Path]:
    """Notes + sidecars under vault/<para-root>/ — the only things --wipe removes."""
    targets: list[Path] = []
    for root in PARA_ROOTS:
        base = VAULT_DIR / root
        if not base.exists():
            continue
        targets += base.rglob("*.md")
        targets += base.rglob(".*.embed.json")
    return sorted(targets)


def do_wipe(force: bool) -> None:
    targets = wipe_targets()
    if not targets:
        print("wipe: nothing to remove")
        return
    for t in targets:
        rel = t.relative_to(REPO_ROOT)
        if force:
            t.unlink()
            print(f"  removed {rel}")
        else:
            print(f"  would remove {rel}")
    if not force:
        print("wipe: dry run — pass --force to actually delete")


def do_seed() -> int:
    if not SEEDS_DIR.exists():
        raise SystemExit(f"no seed source at {SEEDS_DIR.relative_to(REPO_ROOT)}/")
    count = 0
    for src in sorted(SEEDS_DIR.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(SEEDS_DIR)
        dest = VAULT_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"  seed {rel}")
        count += 1
    print(f"seeded {count} file(s) -> vault/")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Seed or reset the PARA vault from seeds/."
    )
    ap.add_argument(
        "--wipe", action="store_true",
        help="remove vault PARA notes + sidecars before seeding",
    )
    ap.add_argument(
        "--force", action="store_true",
        help="actually delete during --wipe (otherwise --wipe is a dry run)",
    )
    args = ap.parse_args(argv)

    if args.wipe:
        do_wipe(args.force)
        if not args.force:
            return 0  # dry run only — do not seed
    return do_seed()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
