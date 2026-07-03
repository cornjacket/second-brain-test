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

This brain's embedding backend is set in **`config/embedder.toml`** (override a
single command with the `SECOND_BRAIN_EMBEDDER` env var). Two backends:

- **`ollama`** — real semantic search; needs a local [Ollama](https://ollama.com)
  server running `nomic-embed-text` (`ollama pull nomic-embed-text`).
- **`test`** — deterministic, dependency-free plumbing; stable but *not* semantic.

Notes and queries must share a backend (the same-model invariant), so this one
switch keeps the whole brain consistent.

## Everyday use

**Record knowledge** — write a note under a PARA root, then commit it:

```bash
#  vault/projects/  goal-bound effort      vault/resources/  durable reference
#  vault/areas/     ongoing responsibility  vault/archive/    inactive
git add vault/areas/my-note.md && git commit -m "note: my-note"
```

Filenames are lowercase kebab-case `.md` with YAML frontmatter (`tags: [...]`);
link notes with `[[wikilinks]]`. On commit the **pre-commit** hook embeds the note
and the **post-commit** hook refreshes the cache — so it's searchable right away,
no manual step.

> **Tip — phrase a note the way you'll search for it.** Search ranks a note by how
> close its *wording and meaning* are to your query, so a note that mirrors the
> question you'll later ask is much easier to find. For a quick fact, lead with the
> question **and** answer near the top:
>
> ```markdown
> ---
> tags: [ops]
> ---
> # Deploy rollback
> **Q: How do I roll back a bad deploy?**
> A: `kubectl rollout undo deployment/<name>` — reverts to the previous revision.
> ```
>
> It's not that a question is special — it's that the note now matches *how you'll
> ask*. The closer the note's language is to your future query, the higher it ranks.

**Query knowledge** — just search:

```bash
python3 scripts/search_vault.py "vector search"
```

After a **bulk** change (e.g. `scripts/embed_vault.py`, or editing many notes at
once), rebuild the cache manually: `python3 scripts/hydrate_cache.py`.

**Self-check** (optional) — confirm the pipeline is wired correctly on your
machine, no model needed:

```bash
python3 scripts/self_test.py
```

## Query it from any project (AI skill)

The point of a second brain is for an **AI to consult it while you build something
else** — surfacing existing conventions, past decisions, and tribal knowledge
*before* it designs. This brain ships a skill for **Claude Code / Gemini CLI** that
does exactly that. Install it once (a symlink — nothing is copied):

```bash
python3 scripts/install_skill.py --global --apply             # every project
python3 scripts/install_skill.py --project ~/work/app --apply  # or just one repo
```

Omit `--apply` for a dry run. After that, when you run the AI in another project it
consults this brain automatically (it runs `skill/second-brain/query.py`, which
searches this vault and returns the matching notes as absolute paths). The skill is
written to trigger proactively — before proposing an architecture or convention —
and you can also invoke it directly with `/second-brain`.

- **`--global`** links into `~/.claude/skills/` (and `~/.gemini/skills/`) — all projects.
- **`--project <path>`** links into that repo's `.claude/skills/` — opt-in, per repo.
- Requires Ollama running (queries are embedded with it).

## Layout

```
├── .githooks/pre-commit   # embeds staged notes locally + line-count guard
├── scripts/               # embedder, db, embed_staged, embed_vault, hydrate/update_cache, search, register, self_test, install_skill
├── skill/second-brain/    # AI skill — consult this brain from any project (install_skill.py)
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
