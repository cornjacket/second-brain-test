#!/usr/bin/env python3
"""Install (or remove) this brain's ``second-brain`` integration for Claude / Gemini.

The default usage is consulting the brain while working in **other** projects, so
the integration has two opt-in parts:

  ``--global``          symlink the skill into ``~/.claude/skills/`` (and ``~/.gemini``)
                        so it is reachable from every project
  ``--project <path>``  symlink it into one repo's ``<path>/.claude/skills/`` only
  ``--nudge``           add a reflexive-consult reminder to each tool's **global
                        memory** (``~/.claude/CLAUDE.md`` / ``~/.gemini/GEMINI.md``)
                        so the AI consults the brain *before designing*, unprompted

**Per-repo is the deliberate default stance for the skill:** nothing touches repos
you didn't name. Symlinking (not copying) keeps the installed skill in lockstep
with the brain, and the skill locates the brain via its own path, so it always
queries *this* brain. The nudge is a small marked block — idempotent to add and
cleanly removable — that reinforces the skill's own proactive description.

``--uninstall`` reverses whichever parts you name: it removes only the symlinks
that point at *this* brain and strips only the marked nudge block, leaving the
rest of your config untouched.

Dry-run by default; pass ``--apply`` to actually make changes. Never mutates global
config silently.

    python3 scripts/install_skill.py --global --nudge --apply
    python3 scripts/install_skill.py --project ~/work/service-x --apply
    python3 scripts/install_skill.py --uninstall --global --nudge --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BRAIN = Path(__file__).resolve().parent.parent
SKILL_SRC = BRAIN / "skill" / "second-brain"
# tool -> its base config dir (skills live under <base>/skills/; memory is <base>/<file>)
TOOL_BASE = {"claude": Path.home() / ".claude", "gemini": Path.home() / ".gemini"}
TOOL_MEMORY = {"claude": "CLAUDE.md", "gemini": "GEMINI.md"}

# A marked, idempotent block appended to global memory. The markers let us detect
# an existing install (skip) and remove exactly this block on --uninstall.
NUDGE_BEGIN = "<!-- second-brain:begin -->"
NUDGE_END = "<!-- second-brain:end -->"
NUDGE_BODY = (
    "## Second brain\n\n"
    "Before designing a system, choosing conventions or naming, or answering "
    '"how do we do X / what did we decide about Y", consult the personal '
    "**second-brain** first (via the `second-brain` skill) — it holds prior "
    "decisions, conventions, and hard-won context. Do this proactively, before "
    "proposing a design."
)
NUDGE_BLOCK = f"{NUDGE_BEGIN}\n{NUDGE_BODY}\n{NUDGE_END}\n"


def planned_links(args) -> list[tuple[str, Path]]:
    """(label, destination) for each requested skill-symlink target."""
    out: list[tuple[str, Path]] = []
    if args.global_:
        for tool in args.tools:
            out.append((tool, TOOL_BASE[tool] / "skills" / SKILL_SRC.name))
    if args.project:
        proj = Path(args.project).expanduser().resolve()
        out.append((f"project:{proj.name}", proj / ".claude" / "skills" / SKILL_SRC.name))
    return out


def planned_nudges(args) -> list[tuple[str, Path]]:
    """(label, global-memory-file) for each tool the nudge targets."""
    return [(f"nudge:{tool}", TOOL_BASE[tool] / TOOL_MEMORY[tool]) for tool in args.tools]


def is_our_link(dst: Path) -> bool:
    """True iff ``dst`` is a symlink pointing at this brain's skill dir."""
    return dst.is_symlink() and Path(os.readlink(dst)) == SKILL_SRC


# --------------------------------------------------------------------------- #
# skill symlinks
# --------------------------------------------------------------------------- #

def install_link(label: str, dst: Path, is_global: bool, apply: bool) -> None:
    # For --global, skip a tool whose base config dir is absent (detect + instruct).
    if is_global and not dst.parent.parent.exists():
        print(f"  {label}: skipped — no {dst.parent.parent} (is {label} installed?)")
        return
    if is_our_link(dst):
        print(f"  {label}: already linked ({dst})")
        return
    if dst.exists() or dst.is_symlink():
        print(f"  {label}: {dst} already exists — remove it first, skipping")
        return
    if apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.symlink_to(SKILL_SRC)
        print(f"  {label}: linked {dst} -> {SKILL_SRC}")
    else:
        print(f"  {label}: would link {dst} -> {SKILL_SRC}")


def remove_link(label: str, dst: Path, apply: bool) -> None:
    if is_our_link(dst):
        if apply:
            dst.unlink()
            print(f"  {label}: unlinked {dst}")
        else:
            print(f"  {label}: would unlink {dst}")
    elif dst.exists() or dst.is_symlink():
        print(f"  {label}: {dst} is not this brain's link — leaving it")
    else:
        print(f"  {label}: nothing at {dst}")


# --------------------------------------------------------------------------- #
# global-memory nudge
# --------------------------------------------------------------------------- #

def install_nudge(label: str, mem: Path, apply: bool) -> None:
    if not mem.parent.exists():
        print(f"  {label}: skipped — no {mem.parent} (is the tool installed?)")
        return
    existing = mem.read_text(encoding="utf-8") if mem.exists() else ""
    if NUDGE_BEGIN in existing:
        print(f"  {label}: already present in {mem}")
        return
    if apply:
        prefix = existing
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix:
            prefix += "\n"  # blank line before our block
        mem.write_text(prefix + NUDGE_BLOCK, encoding="utf-8")
        print(f"  {label}: added nudge to {mem}")
    else:
        print(f"  {label}: would add nudge to {mem}")


def remove_nudge(label: str, mem: Path, apply: bool) -> None:
    text = mem.read_text(encoding="utf-8") if mem.exists() else ""
    if NUDGE_BEGIN not in text:
        print(f"  {label}: no nudge block in {mem}")
        return
    before, _, rest = text.partition(NUDGE_BEGIN)
    _, _, after = rest.partition(NUDGE_END)
    before = before.rstrip("\n")
    after = after.lstrip("\n")
    new = before + ("\n\n" if before and after else "") + after
    if new and not new.endswith("\n"):
        new += "\n"
    if apply:
        mem.write_text(new, encoding="utf-8")
        print(f"  {label}: removed nudge from {mem}")
    else:
        print(f"  {label}: would remove nudge from {mem}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Install/remove the second-brain integration.")
    ap.add_argument("--global", dest="global_", action="store_true",
                    help="skill for all projects (~/.claude, ~/.gemini)")
    ap.add_argument("--project", metavar="PATH",
                    help="skill for this repo only (PATH/.claude/skills/)")
    ap.add_argument("--nudge", action="store_true",
                    help="add a 'consult before designing' reminder to global memory")
    ap.add_argument("--tools", nargs="+", choices=list(TOOL_BASE), default=list(TOOL_BASE),
                    help="which tools for --global/--nudge (default: both, if present)")
    ap.add_argument("--uninstall", action="store_true",
                    help="remove the named parts instead of installing them")
    ap.add_argument("--apply", action="store_true",
                    help="actually make changes (default: dry run)")
    args = ap.parse_args(argv)

    if not (args.global_ or args.project or args.nudge):
        ap.error("choose at least one of --global, --project <path>, --nudge")
    # Installing needs the skill source; uninstalling must work even if it's gone.
    if not args.uninstall and not SKILL_SRC.is_dir():
        raise SystemExit(f"install_skill: no skill at {SKILL_SRC}")

    for label, dst in planned_links(args):
        is_global = not label.startswith("project:")
        if args.uninstall:
            remove_link(label, dst, args.apply)
        else:
            install_link(label, dst, is_global, args.apply)

    if args.nudge:
        for label, mem in planned_nudges(args):
            if args.uninstall:
                remove_nudge(label, mem, args.apply)
            else:
                install_nudge(label, mem, args.apply)

    if not args.apply:
        verb = "remove" if args.uninstall else "make"
        print(f"dry run — re-run with --apply to {verb} these changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
