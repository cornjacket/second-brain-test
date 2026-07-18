#!/usr/bin/env python3
"""Verify scenario 04 — a get_note on /etc/passwd was refused (human-observed).

A refused read leaves no side effect on disk, so there is nothing deterministic for this script
to assert — the check is that Desktop's reply showed NO file contents. The deterministic version
of this guard is CI gate G6 (tools/check_mcp_server.py), which drives the stdio server directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import brain_from_argv, Checker  # noqa: E402


def main() -> int:
    brain_from_argv()  # validate the --brain arg for a uniform CLI, even though unused here
    c = Checker("04 path-traversal")
    c.skip("no on-disk side effect to assert (a refused read writes nothing); "
           "the server-side guard is covered deterministically by CI gate G6")
    c.manual("the read was REFUSED — the reply showed no /etc/passwd contents, and the model "
             "reported it could not read outside the vault")
    return c.done()


if __name__ == "__main__":
    raise SystemExit(main())
