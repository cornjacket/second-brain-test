# Second Brain — Build Plan

The canonical, durable task tracker for building **this repo** (the brain). It
supersedes any ephemeral session plan. We build the brain **first** and get it
working; the devkit will later use this plan + this repo's git history as the
spec for what to generate.

Status: `[x]` done & committed · `[~]` written, not yet verified/committed · `[ ]` not started

Larger units of work get a full **task document** under [`tasks/`](tasks/); this
file links to them and tracks their open/closed state.

### Execution order
The repo must move to the new `vault/` structure **before** any further PARA
notes are generated. So Milestone 1 is split: the written code is **M1a** (done);
its note-generating verification is **M1b**, gated behind the restructure:

- **M1a** — core pipeline code (written, unverified) ✅ *(done)*
1. **Task 0001** — migrate to the `vault/`-rooted layout (+ activate hook) ✅ *(done)*
2. **Task 0002** — markdown line-count guard ← NEXT
3. **Task 0003** — PARA seed script (wipe & re-seed)
4. **M1b** — verify embed → hydrate → search under `vault/`, commit sidecars
5. **Milestone 2** — registration & ingestion

## Milestone 0 — Product docs ✅
- [x] `SPEC.md` — canonical product spec (PARA, sidecar schema, embedding contract, stage contracts, `register`, runtime, safety, roadmap)
- [x] `CLAUDE.md` — in-brain agent memory (`GEMINI.md` will symlink to it)
- [x] `README.md` — overview + quickstart

## Milestone 1a — Core pipeline code (written, unverified)
The pipeline scripts/hooks are written & committed. Activation and live
verification are **gated behind the restructure** — we do **not** generate PARA
notes/sidecars until the new `vault/` structure exists. The remaining M1 work
continues below in **Milestone 1b**, *after* Tasks 0001–0003.
- [x] `scripts/embedder.py` — `test` + `ollama` backends (768-dim, L2, deterministic `test`)
- [x] `scripts/db.py` — stdlib `sqlite3` → `apsw` fallback for `sqlite-vec`
- [x] `scripts/embed_staged.py` — pre-commit embed of staged PARA notes
- [x] `scripts/hydrate_cache.py` — wipe + rebuild `vec0` cache
- [x] `scripts/search_vault.py` — cosine KNN search
- [x] `.githooks/pre-commit`, `.gitattributes`, `.gitignore`, `requirements.txt`
- [x] PARA seed notes written — to be relocated to a `seeds/` source + re-seeded via Task 0003

## Task 0001 — Migrate to `vault/`-rooted layout ✅
- [x] Move PARA roots under `vault/`, repoint cache to `data/brain.db`, activate
      the hook (`chmod +x`, `git config core.hooksPath .githooks`, symlink
      `GEMINI.md` → `CLAUDE.md`), update scripts/`.gitignore` and sweep docs for
      stale paths. **Gates all further note generation.**
      Full spec: [`tasks/0001-migrate-to-vault-rooted-layout.md`](tasks/0001-migrate-to-vault-rooted-layout.md)

## Task 0002 — Markdown line-count guard (after 0001; deferred)
- [ ] Warn (don't block, don't auto-edit) when an in-scope `.md` exceeds 300
      non-empty lines, nudging to segment it. Excludes `README.md` and `tasks/`.
      Primary: pre-commit check (catches Obsidian/any editor); optional PostToolUse
      hook for live feedback. Both deterministic / zero-token. Runs **after** the
      0001 restructure; **implementation deferred.**
      Full spec: [`tasks/0002-markdown-line-count-guard.md`](tasks/0002-markdown-line-count-guard.md)

## Task 0003 — PARA seed script (wipe & re-seed)
- [ ] `scripts/seed_vault.py` copies canonical seed notes from a `seeds/` source
      into `vault/<para>/`, with a guarded `--wipe` so the vault can be reset and
      re-seeded for clean, deterministic pipeline tests. Depends on Task 0001.
      Full spec: [`tasks/0003-para-seed-script.md`](tasks/0003-para-seed-script.md)

## Milestone 1b — verification & sidecar commit (after Tasks 0001–0003)
Continuation of Milestone 1a. Now that the `vault/` structure exists and is
seedable, generate and verify the working brain.
- [ ] Verify stage 1 — commit a note under `vault/` → hook writes & stages its `.embed.json` sidecar; re-embed → clean diff (deterministic `test`)
- [ ] Verify stages 2–3 — `pip install apsw`; `hydrate_cache.py` builds `data/brain.db`; `search_vault.py` returns ranked rows
- [ ] Commit the generated sidecars (the verified, working brain)

## Milestone 2 — Registration & ingestion
- [ ] `scripts/register.py` — inject an idempotent managed block into a target project's `CLAUDE.md` pointing at this brain
- [ ] Verify idempotency (re-run refreshes the block, never duplicates)
- [ ] Ingestion smoke test — record a note via the registered flow → `search_vault.py` finds it
- [ ] Commit

## Later (roadmap; see `SPEC.md` §10)
- [ ] Frontmatter/tag extraction into queryable cache columns
- [ ] `[[wikilink]]` graph (backlinks, neighbor expansion)
- [ ] Content chunking for long notes (multiple vectors per note)
- [ ] Incremental hydrate (only changed sidecars)

## Semantic validation (blocked: no Ollama in current env)
- [ ] Run under `SECOND_BRAIN_EMBEDDER=ollama` and confirm semantically sensible ranking
      (the `test` backend only proves plumbing, not retrieval quality)
