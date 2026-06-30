# Second Brain — Agent Memory

You are working **inside a Second Brain**: a PARA Markdown vault (for humans) plus
a local SQLite `vec0` cache (for you). The full contract is in [SPEC.md](SPEC.md);
this file is the operational memory.

> `GEMINI.md` is a symlink to this file so Claude and Gemini read identical
> instructions.

## Recording knowledge

Durable lessons, insights, and architecture understandings belong here as **PARA
notes** — there is no separate ingestion path; a note *is* the ingestion.

- File the note under the right PARA root: `projects/` (goal-bound effort),
  `areas/` (ongoing responsibility), `resources/` (durable reference),
  `archive/` (inactive).
- Lowercase kebab-case filename, `.md`, with YAML frontmatter (`tags: [...]`).
  Link related notes with `[[wikilinks]]`.
- Commit it. The pre-commit hook embeds the note into a `.embed.json` sidecar and
  stages that sidecar into the same commit automatically — do not hand-edit
  sidecars.

## Querying knowledge

Before solving something from scratch, search what the brain already knows:

```bash
python3 scripts/search_vault.py "<natural-language query>"
```

After adding or editing notes, rebuild the cache:

```bash
python3 scripts/hydrate_cache.py
```

## Invariants & safety

- **Same model for notes and queries.** Search only works if the query is
  embedded by the same backend/model as the notes. Both go through
  `scripts/embedder.py`; do not bypass it. (`SECOND_BRAIN_EMBEDDER=test` is
  deterministic plumbing; `=ollama` is real semantic search.)
- **Never** edit a `.embed.json` sidecar by hand or let git conflict markers into
  one (`merge=binary` is enforced).
- **Never** add a cloud vector store. This brain is local-first.
- The cache (`.cache/vault.db`) is derived — safe to delete and rebuild anytime.

## First-time setup

```bash
git config core.hooksPath .githooks   # activate the embed hook
pip install -r requirements.txt        # sqlite-vec (+ apsw fallback)
```
