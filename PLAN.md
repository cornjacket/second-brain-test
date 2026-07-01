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
2. **Task 0002** — markdown line-count guard ✅ *(primary done; optional live hook deferred)*
3. **Task 0003** — PARA seed script (wipe & re-seed) ✅ *(done)*
4. **M1b** — verify embed → hydrate → search under `vault/`, commit sidecars ✅ *(plumbing done; semantic validation still pending Ollama)*
5. **Milestone 2** — registration & ingestion ✅ *(done)*
6. **→ devkit G1** — brain core is complete; generator work is now unblocked (cross-repo) ← NEXT

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

## Task 0002 — Markdown line-count guard ✅ *(primary)*
- [x] `scripts/check_line_count.py` warns (don't block, don't auto-edit) when an
      in-scope `.md` exceeds 300 non-empty lines. Excludes `README.md` and
      `tasks/`. Wired into `.githooks/pre-commit` (editor-agnostic, deterministic,
      zero-token) and verified via temp-repo integration test.
- [ ] *(optional, deferred)* PostToolUse live-feedback hook + installer — left
      uninstalled (mutates `.claude/settings.json`, wants trust approval).
      Full spec: [`tasks/0002-markdown-line-count-guard.md`](tasks/0002-markdown-line-count-guard.md)

## Task 0003 — PARA seed script (wipe & re-seed) ✅
- [x] `scripts/seed_vault.py` copies canonical seed notes from the `seeds/` source
      into `vault/<para>/`, with a guarded `--wipe` (dry run unless `--force`) so
      the vault can be reset and re-seeded for clean, deterministic pipeline tests.
      Chose Option A (commit both `seeds/` and live `vault/`). Guardrail-tested.
      Full spec: [`tasks/0003-para-seed-script.md`](tasks/0003-para-seed-script.md)

## Milestone 1b — verification & sidecar commit ✅ (after Tasks 0001–0003)
Continuation of Milestone 1a. Now that the `vault/` structure exists and is
seedable, generate and verify the working brain.
- [x] Verify stage 1 — hook writes & stages `.embed.json` sidecars for staged `vault/` notes (proven in the Task 0002 temp-repo test); re-embed → clean diff (deterministic `test`)
- [x] Verify stages 2–3 — `apsw` installed; `hydrate_cache.py` builds `data/brain.db` (4 notes); `search_vault.py` returns ranked rows
- [x] Commit the generated sidecars (the working brain)
- [ ] **Semantic validation still pending** — the `test` backend proves plumbing only (distances ≈ 1.0, non-semantic). Real ranking needs `SECOND_BRAIN_EMBEDDER=ollama` (blocked: no Ollama here) — see *Semantic validation* below.

## Task 0004 — Sidecar policy & test tiers ✅ *(primary)*
- [x] Live-vault sidecars are **derived + git-ignored**; only deterministic
      `tests/fixtures/vault/` sidecars are committed. Added sidecar `type` field,
      `scripts/self_test.py` (structural tier), and `tests/README.md` (two-tier
      strategy). Golden pinned to `test`. `git rm`'d the 4 M1b sidecars.
- [ ] *(deferred)* Enforce `type` in hydrate/search; implement the semantic
      (Ollama) E2E tier. Full spec: [`tasks/0004-sidecar-policy-and-test-tiers.md`](tasks/0004-sidecar-policy-and-test-tiers.md)

## Milestone 2 — Registration & ingestion ✅
- [x] `scripts/register.py` — injects an idempotent managed block (`<!-- second-brain:begin/end -->`) into a target project's `CLAUDE.md` pointing at this brain
- [x] Verify idempotency — re-run refreshes in place (added → refreshed), byte-identical on repeat, preserves existing content, creates `CLAUDE.md` if missing
- [x] Ingestion smoke test — a new PARA note → embed → hydrate → `search_vault.py` returns it as the top hit (0.0000 distance, deterministic `test` backend)
- [x] Commit

## Later (roadmap; see `SPEC.md` §10)
- [ ] Frontmatter/tag extraction into queryable cache columns
- [ ] `[[wikilink]]` graph (backlinks, neighbor expansion)
- [ ] Content chunking for long notes (multiple vectors per note)
- [ ] Incremental hydrate (only changed sidecars)

## Semantic validation (blocked: no Ollama in current env)
- [ ] Run under `SECOND_BRAIN_EMBEDDER=ollama` and confirm semantically sensible ranking
      (the `test` backend only proves plumbing, not retrieval quality)
