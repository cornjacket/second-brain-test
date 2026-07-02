# Second Brain

A personal knowledge base with **two faces over one source of truth**: you write
plain-Markdown notes (in [Obsidian](https://obsidian.md) or any editor), and an AI
(Claude / Gemini) searches them **semantically**. Notes are organized with
**PARA**; a git pre-commit hook keeps a per-note vector in sync, and those vectors
hydrate a local SQLite cache that powers search — no cloud, no external services.

> This repo is the **golden reference** for
> [`second-brain-devkit`](https://github.com/cornjacket/second-brain-devkit) — the
> hand-built, known-good output the generator is validated against. The design
> internals (sidecar schema, embedding contract, pipeline stages) are in
> [SPEC.md](SPEC.md).

## Setup (one-time)

```bash
git config core.hooksPath .githooks    # activate the embed-on-commit hook
pip install -r requirements.txt         # sqlite-vec (+ apsw fallback)
```

By default the pipeline uses a deterministic **`test`** embedder — stable and
dependency-free, but *not* semantic. For real semantic search, run a local
[Ollama](https://ollama.com) server and set `SECOND_BRAIN_EMBEDDER=ollama`.

## Everyday use

**Record knowledge** — write a note under a PARA root, then commit it:

```bash
#  vault/projects/  goal-bound effort      vault/resources/  durable reference
#  vault/areas/     ongoing responsibility  vault/archive/    inactive
git add vault/areas/my-note.md && git commit -m "note: my-note"
```

Filenames are lowercase kebab-case `.md` with YAML frontmatter (`tags: [...]`);
link notes with `[[wikilinks]]`. On commit, the hook refreshes that note's local
vector sidecar automatically.

**Query knowledge** — rebuild the cache after adding/editing notes, then search:

```bash
python3 scripts/hydrate_cache.py            # (re)build the cache from sidecars
python3 scripts/search_vault.py "vector search"
```

**Self-check** (optional) — confirm the pipeline is wired correctly on your
machine, no model needed:

```bash
python3 scripts/self_test.py
```

## Layout

```
├── .githooks/pre-commit   # embeds staged notes locally + line-count guard
├── scripts/               # embedder, db, embed_staged, hydrate, search, register, self_test
├── vault/                 # your notes — point Obsidian here
│   ├── projects/  areas/  resources/  archive/    # PARA roots (embedding scope)
│   └── …/.<note>.embed.json   # per-note vectors — DERIVED, git-ignored
├── tests/fixtures/vault/  # committed test-backend fixtures for self_test
├── data/brain.db          # SQLite vector cache — DERIVED, git-ignored
└── config/                # optional tool-specific config
```

> **Committed vs derived.** Your live note vectors are *derived* and git-ignored —
> regenerated locally, never committed (they're machine/model-dependent). The only
> committed vectors are the deterministic `test`-backend fixtures under
> `tests/fixtures/vault/`, which anchor `self_test`.

## How it works

```
note.md ─(pre-commit)→ .note.embed.json ─(hydrate)→ SQLite vec cache ─(search)→ AI
```

Embed a note into a vector on commit → hydrate pours every vector into one
searchable cache → search embeds your query with the **same** backend and returns
the nearest notes. (Notes and queries must use the same embedder, or results are
meaningless — everything routes through `scripts/embedder.py`.)

> **Tip for Obsidian:** open the `vault/` directory as your vault root (not the
> repo root), so Obsidian doesn't index scripts or the database as notes.

## Registering a project

To have another repo deposit its learnings here, run
`python3 scripts/register.py <project-path>` — it adds an idempotent block to that
project's `CLAUDE.md` pointing its agent at this brain.
