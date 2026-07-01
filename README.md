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
│   └── pre-commit      # Refreshes derived vault sidecars locally + line-count guard
├── config/             # Optional: tool-specific configs (e.g. AI agent prompts)
├── data/               # Derived cache — git-ignored (rebuilt by hydrate)
│   └── brain.db        # SQLite vec0 vector cache (safe to delete & rebuild)
├── scripts/            # embedder, db, embed_staged, hydrate, search, register, self_test
├── tests/
│   ├── README.md       # Testing strategy (structural vs semantic tiers)
│   └── fixtures/vault/ # Committed test-backend fixtures for scripts/self_test.py
└── vault/              # The Obsidian Vault root — point Obsidian here (your Second Brain)
    ├── .obsidian/      # Native Obsidian configuration directory
    ├── projects/  areas/  resources/  archive/   # PARA notes
    └── …/.<note>.embed.json   # per-note vectors — DERIVED, git-ignored (not committed)
```

> **Committed vs derived vectors.** Live-vault sidecars are *derived* (semantic,
> machine-dependent) and git-ignored — regenerate them locally. The **only**
> committed sidecars are the deterministic `test`-backend fixtures under
> `tests/fixtures/vault/`. See [tests/README.md](tests/README.md).

## Pipeline

The four verbs, in order:

1. **Embed** — turn a note's text into a vector (a list of numbers) via
   `scripts/embedder.py`. Written to a per-note `.embed.json` **sidecar**.
2. **Sidecar** — the `.<note>.embed.json` file holding one note's vector. Derived
   and git-ignored for the live vault; committed only for the test fixtures.
3. **Hydrate** — *(re)build the queryable cache from the sidecars.*
   `scripts/hydrate_cache.py` scans every sidecar and **wipes-and-rebuilds**
   `data/brain.db` (the `vec0` table). "Hydrate" = pour the vectors from the
   many small sidecar files into the single searchable database.
4. **Search** — embed a query with the **same** backend and run a nearest-neighbour
   lookup against `data/brain.db` (`scripts/search_vault.py`).

## Quickstart

```bash
git config core.hooksPath .githooks    # activate the pre-commit hook
pip install -r requirements.txt         # sqlite-vec (+ apsw fallback)

# write a note under a PARA root, then commit (the hook refreshes its local,
# git-ignored sidecar; embedding runs with the configured backend)
git add vault/areas/ && git commit -m "add note"

python3 scripts/hydrate_cache.py        # (re)build the vec0 cache from sidecars
python3 scripts/search_vault.py "vector search"

python3 scripts/self_test.py            # deterministic pipeline check (no model needed)
```

> **Tip for Obsidian:** You will want to point Obsidian to open the `/vault`
> directory as the vault root, rather than the root of the entire Git
> repository. This keeps Obsidian's internal `.obsidian` files clean and prevents
> it from indexing your Python scripts or SQLite databases as notes.

By default the pipeline uses a deterministic **`test`** embedder (stable,
diffable, but not semantic). For real semantic search, run a local Ollama server
and set `SECOND_BRAIN_EMBEDDER=ollama`. See [SPEC.md](SPEC.md) §4.
