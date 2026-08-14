#!/usr/bin/env python3
"""Register a project repo with this Second Brain.

Injects an **idempotent managed block** (begin/end markers) into a target
project's ``CLAUDE.md``, instructing that project's agent to record durable
lessons as PARA notes in this brain and to query this brain before solving anew.
Re-running **refreshes** the block in place — it never duplicates it.

    python3 scripts/register.py <project-path>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BRAIN_ROOT = Path(__file__).resolve().parent.parent
BEGIN = "<!-- second-brain:begin -->"
END = "<!-- second-brain:end -->"


def managed_block() -> str:
    brain = BRAIN_ROOT
    return "\n".join([
        BEGIN,
        "<!--",
        f"  Injected and refreshed by second-brain register.py from {brain}.",
        "  Do not edit between the begin/end markers — re-running register.py",
        "  overwrites this block.",
        "-->",
        "## Second Brain — capture & recall",
        "",
        f"This project is registered with a **Second Brain** at `{brain}`.",
        "",
        "- **Before solving from scratch**, search what the brain already knows:",
        f'  `python3 {brain}/scripts/search_vault.py "<query>"`',
        "- **Record durable lessons**, insights, and architecture understandings as",
        f"  PARA notes under `{brain}/vault/` (`projects/`, `areas/`, `resources/`,",
        "  `archive/`) — lowercase-kebab `.md` with YAML `tags:`. Committing the note",
        "  embeds it into the brain.",
        END,
        "",
    ])


def register(project_path: Path) -> tuple[Path, str]:
    if not project_path.is_dir():
        raise SystemExit(f"not a directory: {project_path}")
    claude = project_path / "CLAUDE.md"
    text = claude.read_text(encoding="utf-8") if claude.exists() else ""
    block = managed_block()

    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.DOTALL)
    if pattern.search(text):
        new_text = pattern.sub(lambda _m: block, text, count=1)
        action = "refreshed"
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        if text and not text.endswith("\n\n"):
            text += "\n"
        new_text = text + block
        action = "added"

    claude.write_text(new_text, encoding="utf-8")
    return claude, action


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Register a project repo with this Second Brain."
    )
    ap.add_argument("project_path", help="path to the target project repo")
    args = ap.parse_args(argv)

    claude, action = register(Path(args.project_path).resolve())
    print(f"{action} second-brain block in {claude}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
