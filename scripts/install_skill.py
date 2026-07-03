#!/usr/bin/env python3
"""Install this brain's ``second-brain`` skill for Claude Code / Gemini CLI.

The default usage is consulting the brain while working in **other** projects, so
the skill must be reachable from those projects. This symlinks the brain's skill
directory (``skill/second-brain/``) into one of two scopes:

  ``--project <path>``  a specific repo's ``<path>/.claude/skills/`` — opt-in, per-repo
  ``--global``          your ``~/.claude/skills/`` — available in every project

**Per-repo is the deliberate default stance:** nothing touches repos you didn't
name, and you choose exactly where the brain is consulted. ``--global`` is the
one-symlink convenience when you want it everywhere. Symlinking (not copying) keeps
the installed skill in lockstep with the brain, and the skill locates the brain via
its own path, so it always queries *this* brain.

Dry-run by default; pass ``--apply`` to actually create the links. Never mutates
global config silently.

    python3 scripts/install_skill.py --global --apply
    python3 scripts/install_skill.py --project ~/work/service-x --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BRAIN = Path(__file__).resolve().parent.parent
SKILL_SRC = BRAIN / "skill" / "second-brain"
# tool -> its base config dir (skills live under <base>/skills/)
TOOL_BASE = {"claude": Path.home() / ".claude", "gemini": Path.home() / ".gemini"}


def planned_links(args) -> list[tuple[str, Path, bool]]:
    """(label, destination, is_global) for each requested install target."""
    out: list[tuple[str, Path, bool]] = []
    if args.global_:
        for tool in args.tools:
            out.append((tool, TOOL_BASE[tool] / "skills" / SKILL_SRC.name, True))
    if args.project:
        proj = Path(args.project).expanduser().resolve()
        out.append((f"project:{proj.name}", proj / ".claude" / "skills" / SKILL_SRC.name, False))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Install the second-brain skill (symlink).")
    ap.add_argument("--global", dest="global_", action="store_true",
                    help="install for all projects (~/.claude, ~/.gemini)")
    ap.add_argument("--project", metavar="PATH",
                    help="install only for this repo (PATH/.claude/skills/)")
    ap.add_argument("--tools", nargs="+", choices=list(TOOL_BASE), default=list(TOOL_BASE),
                    help="which tools for --global (default: both, if present)")
    ap.add_argument("--apply", action="store_true",
                    help="actually create the symlinks (default: dry run)")
    args = ap.parse_args(argv)

    if not SKILL_SRC.is_dir():
        raise SystemExit(f"install_skill: no skill at {SKILL_SRC}")
    if not (args.global_ or args.project):
        ap.error("choose --global and/or --project <path>")

    for label, dst, is_global in planned_links(args):
        # For --global, skip a tool whose base config dir is absent (detect + instruct).
        if is_global and not TOOL_BASE[label].exists():
            print(f"  {label}: skipped — no {TOOL_BASE[label]} (is {label} installed?)")
            continue
        if dst.is_symlink() and dst.resolve() == SKILL_SRC.resolve():
            print(f"  {label}: already linked ({dst})")
            continue
        if dst.exists() or dst.is_symlink():
            print(f"  {label}: {dst} already exists — remove it first, skipping")
            continue
        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(SKILL_SRC)
            print(f"  {label}: linked {dst} -> {SKILL_SRC}")
        else:
            print(f"  {label}: would link {dst} -> {SKILL_SRC}")

    if not args.apply:
        print("dry run — re-run with --apply to create the symlinks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
