# Second Brain — Build Plan

The canonical, durable task tracker for building **this repo** (the brain). It
supersedes any ephemeral session plan. We build the brain **first** and get it
working; the devkit will later use this plan + this repo's git history as the
spec for what to generate.

Status: `[x]` done & committed · `[~]` written, not yet verified/committed · `[ ]` not started

## Milestone 0 — Product docs ✅
- [x] `SPEC.md` — canonical product spec (PARA, sidecar schema, embedding contract, stage contracts, `register`, runtime, safety, roadmap)
- [x] `CLAUDE.md` — in-brain agent memory (`GEMINI.md` will symlink to it)
- [x] `README.md` — overview + quickstart

## Milestone 1 — Core pipeline (embed → hydrate → search)  ← NEXT
Code is written & committed (unverified). The hook is **not** activated, so no
sidecars exist yet; activation + verification are still pending.
- [x] `scripts/embedder.py` — `test` + `ollama` backends (768-dim, L2, deterministic `test`)
- [x] `scripts/db.py` — stdlib `sqlite3` → `apsw` fallback for `sqlite-vec`
- [x] `scripts/embed_staged.py` — pre-commit embed of staged PARA notes
- [x] `scripts/hydrate_cache.py` — wipe + rebuild `vec0` cache
- [x] `scripts/search_vault.py` — cosine KNN search
- [x] `.githooks/pre-commit`, `.gitattributes`, `.gitignore`, `requirements.txt`
- [x] PARA seed notes (`projects/`, `areas/`, `resources/`, `archive/`)
- [ ] Activate: `chmod +x` hook, `git config core.hooksPath .githooks`, symlink `GEMINI.md` → `CLAUDE.md`
- [ ] Verify stage 1 — commit a note → hook writes & stages its sidecar; re-embed → clean diff (deterministic)
- [ ] Verify stages 2–3 — `pip install apsw`; `hydrate_cache.py` builds cache; `search_vault.py` returns ranked rows
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
