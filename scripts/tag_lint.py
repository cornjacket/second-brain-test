#!/usr/bin/env python3
"""Report tag-vocabulary hygiene for this brain — the read-only lint entry point.

Runs the deterministic detector in tag_hygiene (near-miss, discrimination, overlap,
format-lint) and prints its findings. Read-only: it never edits a note and always exits
0, so it is safe to wire into pre-commit or CI as an *informational* check — drift is
made visible, never fatal. Its output is a report to read, then act on with tag_apply.py.

    python3 scripts/tag_lint.py            # human-readable report
    python3 scripts/tag_lint.py --json     # machine-readable report

Pure stdlib; all detection logic lives in tag_hygiene so this and the write-time warning
(mcp_server) share one implementation and cannot drift.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import tag_hygiene  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(tag_hygiene.main(sys.argv[1:]))
