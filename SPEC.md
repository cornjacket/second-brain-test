# Second Brain — Product Specification

This is the **canonical contract** for what a single Second Brain *is*: its
layout, its storage formats, its embedding rules, and the behavior of each
pipeline stage. The generator ([`second-brain-devkit`](https://github.com/cornjacket/second-brain-devkit))
exists to produce a repo that conforms to this spec, and validates its output by
diffing against this repo (the golden reference).

For the wider picture — the three-repo system, knowledge flow, and lifecycle —
see the devkit's system spec (`../second-brain-devkit/SPEC.md`).

---

## 1. What a brain is

A brain is a **dual-interface knowledge graph** over one plain-text source of
truth:

- **Human interface** — [Obsidian](https://obsidian.md) over a PARA Markdown
  vault (write, link, graph view).
- **Machine interface** — a local SQLite `vec0` cache, derived from the vault,
  that an AI (Claude / Gemini) queries deterministically and cheaply.

The pipeline keeps the two in sync:

```
note.md ─(pre-commit)→ .note.embed.json ─(hydrate)→ vec0 cache ─(search)→ AI
```

## 2. Vault layout (PARA)

Notes are organized with the **PARA** method. The four PARA directories are the
**vault roots** — and they define the embedding scope. Only Markdown under these
roots is embedded; repo meta files (`README.md`, `CLAUDE.md`, `SPEC.md`,
`scripts/`) are not.

```
projects/    # active efforts with a goal and an end
areas/       # ongoing responsibilities to maintain
resources/   # topics & references of durable interest
archive/     # inactive items from the other three
```

### Note format

- **Filename:** lowercase kebab-case `.md` (e.g. `sqlite-vec.md`).
- **Frontmatter:** YAML block with at least `tags: [...]`; other keys are free.
- **Links:** Obsidian-style `[[wikilinks]]` between notes are allowed and
  preserved verbatim (link-graph extraction is a roadmap item, §10).

```markdown
---
tags: [tech, search]
---

# sqlite-vec

Body text, with optional [[links]] to other notes.
```

## 3. Storage formats

### 3.1 Sidecar (`.<stem>.embed.json`)

Each note has a sibling vector sidecar in the **same directory**, named with a
**dotted prefix** (hidden by default) and the `.embed.json` suffix:
`areas/knowledge-management.md` → `areas/.knowledge-management.embed.json`.

```json
{
  "source_file": "areas/knowledge-management.md",
  "vector": [0.0, 0.0, "... 768 floating-point numbers"]
}
```

- `source_file` — vault-relative POSIX path to the note.
- `vector` — exactly `EMBED_DIM` (768) floats (see §4).
- Sidecars are **committed** (they are the expected output). The hook keeps them
  in lockstep with the note.
- `.gitattributes` sets `.*.embed.json merge=binary` — git must **never** inject
  conflict markers into a vector, which would silently poison search.

### 3.2 Cache (`.cache/vault.db`)

Derived state, rebuilt from the sidecars. **Gitignored.** A single `sqlite-vec`
virtual table:

```sql
CREATE VIRTUAL TABLE notes USING vec0(
  source_file TEXT PRIMARY KEY,
  embedding   FLOAT[768] distance_metric=cosine
);
```

## 4. Embedding contract

| Property | Value |
| --- | --- |
| Dimensions (`EMBED_DIM`) | 768 |
| Normalization | L2 (unit vectors) |
| Serialized precision | rounded to 6 decimals (byte-stable JSON) |
| Backend selector | env `SECOND_BRAIN_EMBEDDER` ∈ {`test`, `ollama`}, default `test` |

- **`test` backend** — deterministic, dependency-free, hash-seeded
  pseudo-embedding. The same text yields an identical vector on every machine, so
  the golden's sidecars are byte-stable and diffable in CI. It is **not**
  semantic: it validates *plumbing*, not retrieval quality.
- **`ollama` backend** — real `nomic-embed-text` via a local Ollama server
  (`OLLAMA_HOST`, default `http://localhost:11434`; model override via
  `SECOND_BRAIN_EMBED_MODEL`). This is the production path and the only one that
  yields meaningful search.

**Same-model invariant.** The note vectors and the query vector MUST be produced
by the same backend/model. Mismatched models produce incomparable vectors and
corrupt search. The shared `scripts/embedder.py` is the single source for both.

## 5. Pipeline stage contracts

### 5.1 Pre-commit hook (embed)

- Activated via `git config core.hooksPath .githooks`; the tracked hook lives at
  `.githooks/pre-commit` and fires for real on commit.
- For every **staged** `*.md` under the PARA roots, it (re)computes the embedding,
  writes the sidecar, and `git add`s it so the sidecar lands in the **same**
  commit.
- Implemented by `scripts/embed_staged.py`.

### 5.2 Hydrate (`scripts/hydrate_cache.py`)

- **Wipe-and-rebuild** `.cache/vault.db` from scratch each run (the cache is
  derived; never trusted as incremental state at this stage).
- Scans every `**/.*.embed.json`, validates dimension, inserts into the `notes`
  table (§3.2).
- Prints `hydrated N note(s) -> .cache/vault.db`.

### 5.3 Search (`scripts/search_vault.py "<query>"`)

- Embeds the query with the **same** backend (§4), runs a cosine KNN:
  `WHERE embedding MATCH ? AND k = ? ORDER BY distance`.
- Prints `distance  source_file`, nearest first. `-k/--top-k` controls count
  (default 5).

## 6. Registration & ingestion

A brain ingests knowledge from external **project repos**. Ingestion is **not** a
separate path: a deposited "lesson" is simply a new PARA note that flows through
§5's pipeline.

### `scripts/register.py <project-path>`

Injects an **idempotent managed block** (begin/end markers) into the target
project's `CLAUDE.md`, instructing that project's agent to:

- record durable lessons, insights, and architecture understandings as PARA notes
  in this brain, and
- query prior knowledge via this brain's `search_vault.py` before solving anew.

Re-running `register` **refreshes** the block in place (never duplicates it).

```
<!-- second-brain:begin -->
... managed instructions pointing at this brain ...
<!-- second-brain:end -->
```

**Independence.** This mechanism is fully independent of `ai-project-status`. A
brain user must never be required to adopt that tooling.

## 7. Runtime constraints

- The cache stages (§5.2, §5.3) load the `sqlite-vec` extension. They use
  `scripts/db.py`, which prefers Python's stdlib `sqlite3`
  (`enable_load_extension`) and **falls back to `apsw`** when the local Python or
  SQLite build cannot load extensions (common on macOS). Install per
  `requirements.txt`.
- The embed stage (§5.1) is pure Python (stdlib only for the `test` backend) and
  needs no extension support.

## 8. Repository layout

```
projects/  areas/  resources/  archive/   # the PARA vault (notes + sidecars)
scripts/
  embedder.py        # embedding backends (§4)
  db.py              # sqlite-vec connection (§7)
  embed_staged.py    # pre-commit embed (§5.1)
  hydrate_cache.py   # build cache (§5.2)
  search_vault.py    # semantic search (§5.3)
  register.py        # register a project repo (§6)
.githooks/pre-commit
.gitattributes       # .*.embed.json merge=binary
.gitignore           # .cache/, __pycache__/, .venv/
requirements.txt     # sqlite-vec, apsw
CLAUDE.md            # in-brain agent memory (GEMINI.md symlinks to it)
SPEC.md              # this file
README.md
```

- **Committed:** PARA notes, `.embed.json` sidecars, scripts, hook, config.
- **Derived (gitignored):** `.cache/vault.db`, `__pycache__/`.

## 9. Safety prohibitions

- **Never** use third-party cloud vector stores (Pinecone, Milvus, Supabase) —
  local-first by design.
- **Never** allow git conflict markers into sidecar files (`merge=binary`
  enforced for `.*.embed.json`).

## 10. Roadmap

- Frontmatter/tag extraction into queryable cache columns.
- `[[wikilink]]` graph extraction (backlinks, neighbor expansion).
- Content chunking for long notes (multiple vectors per note).
- Incremental hydrate (only changed sidecars).
- PARA taxonomy refinements (sub-areas, per-PARA conventions).
- Generation by the devkit + the regenerate-and-diff acceptance harness.
