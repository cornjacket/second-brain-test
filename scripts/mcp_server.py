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
import difflib
import re
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
GLOSSARY = VAULT / "glossary"
DB_PATH = BRAIN / "data" / "brain.db"

mcp = FastMCP("second-brain")


# --- glossary index (the symbolic layer) -------------------------------------------------
# The glossary is a controlled vocabulary — exact terms, NOT semantic search. It is
# intentionally excluded from the vector index (a definition sits next to every note that
# mentions the term, so its embedding would become a retrieval/graph hub; see the devkit's
# docs/glossary.md). These tools are the ONLY way to reach it, and they read `glossary/*.md`
# directly — no embedding, no `data/brain.db`. Cheap enough to scan on demand; cached on the
# directory mtime so a newly-added term appears without a server restart.

_GLOSSARY_CACHE: dict = {"mtime": None, "by_key": {}, "terms": []}


def _normalize(term: str) -> str:
    """Fold a term to its lookup key: lowercase, drop punctuation, spaces/underscores -> '-'.

    So ``What is Ablation Study?`` -> ``ablation-study`` -> matches ``ablation-study.md``.
    Mirrors ``glossary_new.slugify`` so filenames and lookups agree.
    """
    s = re.sub(r"[^\w\s-]", "", term.strip().lower())
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


# Interrogative lead-ins/trailers stripped ONLY as a lookup miss-fallback (never on a direct
# hit), so `what is ablation?` resolves to `ablation` without making the match itself fuzzy.
_LEADIN = re.compile(r"^(what-is|what-are|whats|what-does|define|definition-of|meaning-of)-")
_TRAILER = re.compile(r"-(mean|means|defined)$")


def _strip_leadin(key: str) -> str:
    return _TRAILER.sub("", _LEADIN.sub("", key))


def _frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[4:end]
    return ""


def _parse_aliases(text: str) -> list[str]:
    """Declared surface forms from frontmatter ``aliases:`` — inline `[a, b]` or a `- ` block.

    Aliases are explicit vault metadata, never code stemming (explicit beats clever).
    """
    fm = _frontmatter(text)
    inline = re.search(r"^aliases:\s*\[(.*?)\]\s*$", fm, re.MULTILINE)
    if inline:
        return [a.strip().strip("'\"") for a in inline.group(1).split(",") if a.strip()]
    block = re.search(r"^aliases:\s*\n((?:[ \t]*-[ \t]*.+\n?)+)", fm, re.MULTILINE)
    if block:
        return [re.sub(r"^[ \t]*-[ \t]*", "", ln).strip().strip("'\"")
                for ln in block.group(1).splitlines() if ln.strip()]
    return []


def _glossary_index() -> tuple[dict, list]:
    """(``by_key`` normalized-key -> entry, ``terms`` list) for the glossary, mtime-cached.

    ``by_key`` maps the normalized slug **and** each normalized alias to the same entry
    (first-writer-wins on collision — surfaced to stderr, as a real collision is a vault bug).
    ``terms`` is the display listing: ``{"term": <H1 or slug>, "aliases": [...]}`` per note.
    Missing/empty glossary -> ``({}, [])`` (build defensively).
    """
    if not GLOSSARY.exists():
        return {}, []
    try:
        mtime = GLOSSARY.stat().st_mtime
    except OSError:
        return {}, []
    if _GLOSSARY_CACHE["mtime"] == mtime:
        return _GLOSSARY_CACHE["by_key"], _GLOSSARY_CACHE["terms"]

    by_key: dict = {}
    terms: list = []
    for p in sorted(GLOSSARY.glob("*.md")):
        if p.name == "README.md" or p.name.startswith("_"):
            continue
        text = p.read_text(encoding="utf-8")
        slug = p.stem
        display = slug.replace("-", " ")
        for line in text.splitlines():
            if line.startswith("# "):
                display = line[2:].strip()
                break
        aliases = _parse_aliases(text)
        entry = {"path": p, "display": display}
        for key in [_normalize(slug), *(_normalize(a) for a in aliases)]:
            if not key:
                continue
            if key not in by_key:
                by_key[key] = entry
            elif by_key[key]["path"] != p:
                print(f"glossary: key collision on {key!r} — "
                      f"{by_key[key]['path'].name} wins over {p.name}", file=sys.stderr)
        terms.append({"term": display, "aliases": aliases})

    _GLOSSARY_CACHE.update(mtime=mtime, by_key=by_key, terms=terms)
    return by_key, terms

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
    conventions, and hard-won context. Returns up to ``k`` hits, most relevant first, each
    with the note's **absolute** path (the client is not in the brain's directory) and a
    hybrid relevance ``score`` (larger = more relevant). Read a hit with ``get_note``.
    """
    return [
        {"source_file": str(BRAIN / src), "score": round(float(score), 4)}
        for src, score in search_vault.search(query, k)
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


@mcp.tool(structured_output=False)
def list_glossary_terms() -> list[dict]:
    """List every defined glossary term (name + declared aliases), no definitions.

    The glossary is a **controlled vocabulary** of exact terms, **intentionally absent from
    `search_second_brain`** (semantic search) — reach it only through this tool and
    `lookup_glossary_term`. Call this **first** whenever you are unsure a term exists or of
    its exact name, so you can then look it up by an exact key instead of guessing. Returns
    an empty list if this brain has no glossary yet.
    """
    _, terms = _glossary_index()
    return terms


@mcp.tool(structured_output=False)
def lookup_glossary_term(term: str) -> str:
    """Return the full definition note for an EXACT glossary term — a dictionary lookup.

    For **explicit lookup intent only** — "what is X", "define X", "what does X mean" — where
    the key is known. Do **not** call this to add background colour to a conceptual question;
    point those at `search_second_brain`. The glossary is **intentionally absent from semantic
    search**, so this tool and `list_glossary_terms` are the only way to reach it — looking up
    every concept you meet would recreate the hub problem the exclusion exists to prevent.

    Matches the term's normalized slug and its frontmatter `aliases:` (case/punctuation/space
    insensitive, so `"Ablation Study?"` resolves to `ablation-study`). Returns the whole
    (short) note verbatim. On a miss, returns **near-miss suggestions**, not a bare
    not-found — call `list_glossary_terms` first if you're unsure of the exact name.
    """
    by_key, _ = _glossary_index()
    key = _normalize(term)
    entry = by_key.get(key) or by_key.get(_strip_leadin(key))
    if entry is not None:
        return entry["path"].read_text(encoding="utf-8")

    suggestions = _near_misses(_strip_leadin(key), by_key)
    if suggestions:
        return (f"No glossary term matches {term!r}. Did you mean: "
                f"{', '.join(suggestions)}? (Call list_glossary_terms for the full list.)")
    return (f"No glossary term matches {term!r}, and there is no close match. "
            "Call list_glossary_terms to see all defined terms (the glossary may be empty).")


def _near_misses(key: str, by_key: dict, n: int = 3) -> list[str]:
    """Display names of the closest terms: prefix/substring hits first, then difflib fuzzy."""
    keys = list(by_key)
    if not keys or not key:
        return []
    prefix = [k for k in keys if k.startswith(key) or key.startswith(k)]
    substring = [k for k in keys if key in k or k in key]
    fuzzy = difflib.get_close_matches(key, keys, n=5, cutoff=0.6)
    ordered: list[str] = []
    for k in [*prefix, *substring, *fuzzy]:
        display = by_key[k]["display"]
        if display not in ordered:
            ordered.append(display)
    return ordered[:n]


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
