#!/usr/bin/env python3
"""MCP server exposing this brain's semantic search to Claude Desktop (``stdio``).

The **secondary** AI interface, for chat clients that cannot shell out to local
Python — the motivating case is Claude Desktop. (The ``second-brain`` skill stays
the primary mechanism for every CLI/agent client: it adds no new tool schema and
loads only on demand. See ``docs/mcp-server.md`` in the devkit for the full scoping.)

It is a **thin wrapper** over the brain's own modules — ``embedder`` (embed the
query), ``db`` (WAL sqlite-vec connection), and ``search_vault.search()``
(cosine-KNN over ``data/brain.db``) — so there is exactly one retrieval
implementation.

**Mostly read** — search, fetch, browse, glossary — plus exactly one writer,
``add_note``, which **commits and pushes**. That is deliberate, and it is what keeps
the write path from becoming a second system: a note is embedded by the *pre-commit
hook* and the cache is refreshed by the *post-commit hook*, so committing reuses the
one embedding path this brain already has instead of inventing a parallel one that
would have to be kept in step with it forever. Pushing is what makes the note real for
**every other client** of the brain (another machine, a shared/served brain) rather
than only for the laptop that happened to write it.

Claude Desktop launches it over stdio; run it directly the same way:

    python3 scripts/mcp_server.py

Requires the MCP SDK, an **optional** dependency kept out of the base
``requirements.txt`` so the core plumbing stays minimal:

    pip install -r requirements-mcp.txt
"""
from __future__ import annotations

import contextlib
import difflib
import os
import re
import subprocess
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
TEMPLATE = VAULT / "templates" / "new-note.md"
PARA_ROOTS = ("projects", "areas", "resources", "archive")

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


# --- the write path ----------------------------------------------------------------------
# add_note is the ONLY tool that mutates the brain. Two rules shape it:
#
#   1. It commits, because the commit IS the embed. The pre-commit hook embeds staged notes
#      and the post-commit hook re-hydrates the cache, so a committed note is searchable with
#      no extra step. Writing the file and embedding it "by hand" here would fork a second
#      ingestion path that has to track the hooks forever — the bug you find six months later.
#   2. It pushes, because a note only on this disk is invisible to every other client of the
#      brain. A failed push is still not a lost note: the commit landed and search works
#      locally, so we report the failure rather than pretend or roll back.


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run git in the brain. GIT_TERMINAL_PROMPT=0 is load-bearing: this server runs headless
    under Claude Desktop, so a credential prompt has no terminal to appear in — without it a
    push against an auth-needing remote would hang the tool call forever instead of failing."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": ""}
    return subprocess.run(["git", *args], cwd=BRAIN, env=env, check=check,
                          capture_output=True, text=True, timeout=120)


def _slugify(title: str) -> str:
    """Note title -> filename stem: lowercase kebab-case, alphanumerics and hyphens only.

    This is also the security boundary for the write path. It is a strict *allow*-list, not a
    denylist of bad characters: everything outside [a-z0-9-] is dropped, so `../../etc/passwd`
    or a leading `/` cannot survive it — a traversal payload in the title collapses to a plain
    stem. Never build the path from the raw title.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug


def _why(proc: subprocess.CompletedProcess) -> str:
    """git's complaint as one readable line — its stderr is multi-line, and splicing that
    verbatim into a report renders as garbage in a chat client."""
    return " ".join((proc.stderr or proc.stdout or "").split())[:200]


def _push(branch: str) -> str:
    """Push the current branch; return a human-readable outcome line (never raises).

    Handles the case the multi-client story guarantees will happen: another client pushed
    first, so ours is rejected as non-fast-forward. Rebase onto the remote and retry once —
    but only with a clean tree, because rebasing over someone's uncommitted edits from a chat
    tool is a worse outcome than telling them to do it themselves.
    """
    if not _git("remote", check=False).stdout.strip():
        return "not pushed: this brain has no git remote (it is local-only)"

    first = _git("push", "origin", branch, check=False)
    if first.returncode == 0:
        return f"pushed to origin/{branch}"

    dirty = bool(_git("status", "--porcelain", check=False).stdout.strip())
    if dirty:
        return (f"NOT PUSHED — push rejected and your working tree has uncommitted changes, so "
                f"it cannot be safely rebased ({_why(first)}). The note IS committed and "
                f"searchable locally; pull/rebase and push when convenient.")

    rebased = _git("pull", "--rebase", "origin", branch, check=False)
    if rebased.returncode != 0:
        _git("rebase", "--abort", check=False)
        return (f"NOT PUSHED — the remote moved ahead and the rebase did not apply cleanly "
                f"({_why(rebased)}). The note IS committed and searchable locally; resolve by "
                f"hand and push.")

    retry = _git("push", "origin", branch, check=False)
    if retry.returncode == 0:
        return f"pushed to origin/{branch} (after rebasing onto the remote)"
    return (f"NOT PUSHED — {_why(retry)}. The note IS committed and searchable locally; push "
            f"by hand.")


@mcp.tool(structured_output=False)
def add_note(title: str, para_root: str, body: str, tags: list[str] | None = None) -> str:
    """Create a NEW note in the brain, then commit and push it. The only writing tool.

    Call `list_vault` FIRST to see where the note belongs (and whether something like it already
    exists — prefer extending your own knowledge over scattering near-duplicates), and
    `get_note_template` to follow this brain's house style for the body.

    `para_root` must be one of projects / areas / resources / archive (PARA, by actionability):
    projects = a goal-bound effort; areas = an ongoing responsibility; resources = durable
    reference; archive = inactive. `title` becomes both the H1 and the kebab-case filename.
    `body` is Markdown (no frontmatter, no H1 — both are generated). Link related notes with
    [[wikilinks]].

    Refuses to overwrite an existing note. Committing is what embeds it (the pre-commit hook),
    so it is searchable immediately; the push is what makes it visible to the brain's other
    clients. Returns a report of what landed, including whether the push succeeded.
    """
    if para_root not in PARA_ROOTS:
        raise ValueError(f"para_root must be one of {PARA_ROOTS}, got {para_root!r}")
    slug = _slugify(title)
    if not slug:
        raise ValueError(f"title {title!r} has no usable characters for a filename")

    path = VAULT / para_root / f"{slug}.md"
    # Defense in depth: _slugify already makes an escape impossible, so this can only fire if
    # someone loosens it. Cheap to keep, and this is the one tool that writes to disk.
    if path.resolve().parent != (VAULT / para_root).resolve():
        raise ValueError(f"refusing to write outside vault/{para_root}: {title!r}")
    if path.exists():
        raise ValueError(f"note already exists: {path.relative_to(BRAIN)} — add_note creates "
                         "new notes only; edit an existing one in your editor")

    front = ["---", f"tags: [{', '.join(tags)}]" if tags else "tags: []", "---", ""]
    path.write_text("\n".join([*front, f"# {title}", "", body.strip(), ""]), encoding="utf-8")

    rel = str(path.relative_to(BRAIN))
    try:
        # Stage ONLY this file, and commit ONLY this pathspec. A bare `git commit -a` (or
        # staging the whole tree) would sweep the user's in-progress edits into a commit an
        # agent authored — their work, our commit message, no consent. The pathspec keeps
        # anything else they have staged exactly where it was: still staged, uncommitted.
        _git("add", "--", rel)
        _git("commit", "-m", f"note: add {title}", "--", rel)
    except subprocess.CalledProcessError as exc:
        path.unlink(missing_ok=True)  # leave no half-written note behind
        raise ValueError(f"git commit failed, note not created: {_why(exc)}") from exc

    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    pushed = _push(branch)

    # The hooks are what embed + hydrate. If they are not installed (a fresh clone forgets
    # `git config core.hooksPath .githooks`), the commit lands but the note is NOT searchable —
    # a silent, confusing failure. Detect it by the missing sidecar and say so out loud.
    sidecar = path.parent / f".{path.stem}.embed.json"
    embedded = ("embedded + searchable now (pre/post-commit hooks)" if sidecar.exists() else
                "WARNING: committed but NOT embedded — the git hooks are not active in this "
                "brain (run: git config core.hooksPath .githooks), so this note will not be "
                "found by search until you run scripts/embed_vault.py + scripts/hydrate_cache.py")

    # Lead with the bad news. A partial failure here still returns SUCCESS (the note really was
    # created, committed and embedded — it would be wrong to raise), so nothing forces the model
    # to mention a failed push. Buried on line 3 it reads as detail and gets summarized away as
    # "saved!", leaving the user believing a note synced when it did not. First line, in caps,
    # with the word ACTION, is what survives summarization.
    problems = [line for line in (pushed, embedded)
                if line.startswith(("NOT PUSHED", "WARNING", "not pushed"))]
    head = (f"PARTIAL SUCCESS — ACTION NEEDED (tell the user this, do not just say 'saved'): "
            f"{' | '.join(problems)}\n" if problems else "")
    return f"{head}created {rel}\ncommitted to {branch}\n{pushed}\n{embedded}"


@mcp.tool(structured_output=False)
def list_vault(para_root: str = "") -> list[dict]:
    """Browse the vault's structure — call this BEFORE add_note to decide where a note belongs.

    With no argument: the PARA roots and how many notes each holds. With a `para_root`
    (projects / areas / resources / archive): the notes filed under it, so you can see this
    brain's existing subject matter and file a new note next to its siblings rather than
    guessing. Nested folders, if any, are walked.

    This lists paths and titles only — it does not read note bodies (use `search_second_brain`
    to find notes by meaning, or `get_note` to read one). The glossary is not listed here; it
    has its own tools.
    """
    if para_root and para_root not in PARA_ROOTS:
        raise ValueError(f"para_root must be one of {PARA_ROOTS}, got {para_root!r}")

    if not para_root:
        return [{"para_root": r,
                 "notes": sum(1 for _ in (VAULT / r).rglob("*.md")) if (VAULT / r).is_dir() else 0}
                for r in PARA_ROOTS]

    root = VAULT / para_root
    if not root.is_dir():
        return []
    return [{"title": p.stem, "source_file": str(p.resolve()),
             "path": str(p.relative_to(VAULT))}
            for p in sorted(root.rglob("*.md"))]


@mcp.tool(structured_output=False)
def get_note_template() -> str:
    """Return this brain's note template — the house style `add_note`'s body should follow.

    Read it before composing a note so a new note looks like the ones already here. This is the
    vault's live template, which the brain's owner may have edited, so it is the authority on
    shape — not any convention you might assume.
    """
    if not TEMPLATE.exists():
        return ("This brain has no vault/templates/new-note.md. Use a short H1 title, a "
                "paragraph or two of durable content, and [[wikilinks]] to related notes.")
    return TEMPLATE.read_text(encoding="utf-8")


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
