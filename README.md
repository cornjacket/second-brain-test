# Second Brain (golden reference)

A **dual-interface knowledge graph**: write plain Markdown for humans (Obsidian),
query a local SQLite `vec0` cache for AI (Claude / Gemini) — from one source of
truth. Notes are organized with **PARA**; a pre-commit hook keeps a per-note
vector sidecar in sync, which hydrates a local vector cache for semantic search.

> This repo is the **golden reference** for
> [`second-brain-devkit`](https://github.com/cornjacket/second-brain-devkit) — the
> hand-built, known-good output the generator is validated against. The
> authoritative contract is [SPEC.md](SPEC.md); agent memory is [CLAUDE.md](CLAUDE.md).

## Layout

```
projects/  areas/  resources/  archive/   # the PARA vault (notes + .embed.json sidecars)
scripts/                                   # embedder, db, embed_staged, hydrate, search, register
.githooks/pre-commit                       # embeds staged notes on commit
```

## Quickstart

```bash
git config core.hooksPath .githooks    # activate the embed hook
pip install -r requirements.txt         # sqlite-vec (+ apsw fallback)

# write a note under a PARA root, then commit — the hook writes its sidecar
git add areas/ && git commit -m "add note"

python3 scripts/hydrate_cache.py        # build the vec0 cache from sidecars
python3 scripts/search_vault.py "vector search"
```

> **Tip for Obsidian:** You will want to point Obsidian to open the `/vault`
> directory as the vault root, rather than the root of the entire Git
> repository. This keeps Obsidian's internal `.obsidian` files clean and prevents
> it from indexing your Python scripts or SQLite databases as notes.

By default the pipeline uses a deterministic **`test`** embedder (stable,
diffable, but not semantic). For real semantic search, run a local Ollama server
and set `SECOND_BRAIN_EMBEDDER=ollama`. See [SPEC.md](SPEC.md) §4.
