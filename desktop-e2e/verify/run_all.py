#!/usr/bin/env python3
"""Run every Desktop e2e verifier against this brain and summarize.

    python3 desktop-e2e/verify/run_all.py            # this brain (default)
    python3 desktop-e2e/verify/run_all.py --brain PATH

Exit 0 iff every DETERMINISTIC check passed. MANUAL items (human-observed in Desktop) are
printed by each verifier and are NOT reflected in the exit code — confirm them by eye.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    verifiers = sorted(HERE.glob("verify_*.py"))
    worst = 0
    for v in verifiers:
        print(f"\n=== {v.name} ===", flush=True)  # flush so the header precedes the child's output
        r = subprocess.run([sys.executable, str(v), *sys.argv[1:]])
        worst = worst or r.returncode
    print(f"\n{'ALL DETERMINISTIC CHECKS PASSED' if worst == 0 else 'SOME DETERMINISTIC CHECKS FAILED'}"
          " — now confirm the MANUAL (human-observed) items above.")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
