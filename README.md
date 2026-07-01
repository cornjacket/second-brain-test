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
├── .githooks/
│   └── pre-commit      # Embeds staged notes into .embed.json sidecars on commit
├── config/             # Optional: tool-specific configs (e.g. AI agent prompts)
├── data/               # Derived cache — hidden/read-only from Obsidian
│   └── brain.db        # SQLite vec0 vector cache (safe to delete & rebuild)
├── scripts/            # Local utility scripts (embedder, db, hydrate, search, register)
│   ├── embedder.py     # Single embedding backend (test | ollama)
│   ├── hydrate_cache.py# Builds brain.db from the .embed.json sidecars
│   └── search_vault.py # Semantic query over the cache
└── vault/              # The Obsidian Vault root — point Obsidian here (your Second Brain)
    ├── .obsidian/      # Native Obsidian configuration directory
    ├── projects/       # PARA: goal-bound efforts        (+ .embed.json sidecars)
    ├── areas/          # PARA: ongoing responsibilities
    ├── resources/      # PARA: durable reference
    └── archive/        # PARA: inactive
```

## Quickstart

```bash
git config core.hooksPath .githooks    # activate the embed hook
pip install -r requirements.txt         # sqlite-vec (+ apsw fallback)

# write a note under a PARA root, then commit — the hook writes its sidecar
git add vault/areas/ && git commit -m "add note"

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
