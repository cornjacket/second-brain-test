#!/usr/bin/env python3
"""MCP server exposing this brain's semantic search to Claude Desktop (``stdio``).

The **secondary** AI interface, for chat clients that cannot shell out to local
Python — the motivating case is Claude Desktop. (The ``second-brain`` skill stays
the primary mechanism for every CLI/agent client: it adds no new tool schema and
loads only on demand. See ``docs/mcp-server.md`` in the devkit for the full scoping.)

It is a **thin wrapper** over the brain's own modules — ``embedder`` (embed the
query), ``db`` (WAL sqlite-vec connection), and ``search_vault.search()``
(cosine-KNN over ``data/brain.db``) — so there is exactly one retrieval
implementation. **Read-only:** search + fetch, no note creation/editing (writing
goes through the git-committed vault flow, which an MCP write tool would bypass).

Claude Desktop launches it over stdio; run it directly the same way:

    python3 scripts/mcp_server.py

Requires the MCP SDK, an **optional** dependency kept out of the base
``requirements.txt`` so the core plumbing stays minimal:

    pip install -r requirements-mcp.txt
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hydrate_cache  # noqa: E402
import search_vault  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

# .../<brain>/scripts/mcp_server.py -> parents[1] == <brain>. Resolved relative to
# this file so the server works wherever it is installed/symlinked (per-brain).
BRAIN = Path(__file__).resolve().parents[1]
VAULT = BRAIN / "vault"
DB_PATH = BRAIN / "data" / "brain.db"

mcp = FastMCP("second-brain")

# structured_output=False on every tool — a deliberate compatibility choice. These
# functions have typed returns (``-> list[dict]`` / ``-> str``), so modern FastMCP
# would auto-advertise an ``outputSchema`` ("structured output", a newer MCP feature).
# Claude Desktop's embedded MCP client (as of 2026-07-04) predates that field and
# silently DROPS any tool carrying it — the connector then shows "no tools available"
# and the model can't call it. Disabling structured output makes each tool a classic
# text-output tool every client accepts (the return still reaches the model as a JSON
# text block). Revisit if/when Desktop's MCP client gains outputSchema support.


@mcp.tool(structured_output=False)
def search_second_brain(query: str, k: int = 5) -> list[dict]:
    """Search the personal second-brain for notes relevant to a natural-language query.

    Consult this BEFORE designing a system, choosing conventions/naming, or deciding
    "how do we do X / what did we decide about Y" — the brain holds prior decisions,
    conventions, and hard-won context. Returns up to ``k`` hits, nearest first, each
    with the note's **absolute** path (the client is not in the brain's directory)
    and its cosine ``distance`` (smaller = more relevant). Read a hit with ``get_note``.
    """
    return [
        {"source_file": str(BRAIN / src), "distance": round(float(dist), 4)}
        for src, dist in search_vault.search(query, k)
    ]


@mcp.tool(structured_output=False)
def get_note(source_file: str) -> str:
    """Return the Markdown of a note surfaced by ``search_second_brain``.

    ``source_file`` may be the absolute path from a search hit or a vault-relative
    one; it must resolve **inside** the brain's ``vault/`` — arbitrary file reads are
    refused.
    """
    p = Path(source_file)
    if not p.is_absolute():
        p = BRAIN / source_file
    p = p.resolve()
    vault = VAULT.resolve()
    if p != vault and vault not in p.parents:
        raise ValueError(f"refusing to read outside the vault: {source_file}")
    if not p.is_file():
        raise FileNotFoundError(source_file)
    return p.read_text(encoding="utf-8")


def main() -> int:
    # The cache is derived — rebuild it from the vault's sidecars if it's missing, so
    # a freshly-installed brain answers the first query (same policy as the skill).
    # Redirect hydrate's progress to stderr: on stdio, stdout is the JSON-RPC channel
    # and any stray bytes there would corrupt the protocol handshake.
    if not DB_PATH.exists():
        with contextlib.redirect_stdout(sys.stderr):
            hydrate_cache.main()
    mcp.run()  # stdio transport by default
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
