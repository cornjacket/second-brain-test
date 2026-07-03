#!/usr/bin/env python3
"""Query the second-brain this skill was installed from (invoked by the skill).

Resolves the brain root **relative to this file** — even when reached through the
symlink the installer drops into ``~/.claude/skills/`` or a project's
``.claude/skills/`` — so it always queries the right brain with no hardcoded path.
Ensures the search cache exists, forwards to the brain's ``scripts/search_vault.py``,
and rewrites the note paths to **absolute** so the agent (working in some other
project's directory) can open them directly.

    python3 query.py "<natural-language question>" [-k N]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# .../<brain>/skill/second-brain/query.py  ->  parents[2] == <brain>
BRAIN = Path(__file__).resolve().parents[2]
SCRIPTS = BRAIN / "scripts"
DB = BRAIN / "data" / "brain.db"


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True,
    )


def main(argv: list[str]) -> int:
    if not argv:
        print('usage: query.py "<question>" [-k N]', file=sys.stderr)
        return 2

    # The cache is derived — rebuild it from the vault's sidecars if it's missing.
    if not DB.exists():
        h = _run("hydrate_cache.py")
        if h.returncode != 0:
            sys.stderr.write(h.stdout + h.stderr)
            return h.returncode

    r = _run("search_vault.py", *argv)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        return r.returncode

    print(f"# second-brain: {BRAIN}")
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        dist, _, src = line.partition("  ")
        print(f"{dist}  {BRAIN / src.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
