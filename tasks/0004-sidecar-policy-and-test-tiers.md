---
id: 0004
title: Sidecar-commit policy + two-tier testing (derived vault vectors, committed test fixtures)
status: done-primary
depends_on: 0001
tags: [architecture, embeddings, testing, sidecars, devkit]
---

# Task 0004 — Sidecar policy & test tiers

> **Status: primary done.** Live-vault sidecars are now derived/git-ignored;
> committed deterministic fixtures + `self_test.py` are in. Deferred: hydrate/
> search `type` enforcement and the semantic (Ollama) E2E tier.

## Decision (why)

Real brains must **not commit semantic vectors** — they're machine/model-
dependent (float drift across CPU/GPU/BLAS/model versions), bloaty, and always
regenerable from the notes. Since querying needs the model anyway (same-model
invariant), committing them saves only a one-time bulk re-embed while costing
churn forever. So: **notes are the source of truth; vectors are a cache.**

But we still need a **deterministic** artifact to (a) regression-test the pipeline
wiring and (b) give the devkit a byte-stable diff target. That's the `test`
backend, isolated in a **fixture vault** so the live vault can be a real semantic
brain with no collision.

## What changed (this repo)

- **Live-vault sidecars: derived + git-ignored** (`/vault/**/.*.embed.json`). The
  4 committed sidecars from M1b were `git rm`'d.
- **Committed fixtures:** `tests/fixtures/vault/` holds a tiny fixed note set with
  committed `test`-backend sidecars — the *only* committed sidecars.
- **Sidecar `type` field:** `test` or `ollama:<model>`, stamped by
  `embedder.backend_id()`. Non-deterministic sidecars also get `embedded_at`;
  deterministic ones do **not** (keeps fixtures byte-stable).
- **Hook decoupled from committing:** `embed_staged.py` refreshes the derived
  sidecar locally and no longer `git add`s it.
- **`scripts/self_test.py`** — re-embeds fixtures with `test` and byte-compares to
  the committed sidecars. Ships with every generated brain (structural tier).
- **`tests/README.md`** — the two-tier testing strategy (structural byte-diff vs
  semantic behavioural E2E) + what each may/​may-not assert.
- Docs swept: SPEC §3.1/§5.1/§8/§9, README (pipeline glossary defines *hydrate*),
  CLAUDE.md invariants. Golden is **pinned to `test`** as an explicit invariant.

## Two-tier testing (see `tests/README.md`)

- **Structural tier** — `test` backend, byte-exact, hermetic, CI gate, pinpoint
  diagnostics, sensitive to subtle corruption. Cannot judge meaning.
- **Semantic tier** — `ollama`, asserts *behaviour* (related in top-k / cosine
  threshold), never bytes. Opt-in/local, the only tier that proves relevance.

## Verified

- [x] `self_test.py` passes: 2/2 fixtures reproduce byte-for-byte with `type: test`.
- [x] Live-vault sidecars are git-ignored (regenerated ones don't show in status);
      the 4 old committed sidecars removed.
- [x] Fixture sidecars are committable (not ignored).

## Deferred (follow-ups)

- [ ] Enforce the `type` invariant in `hydrate_cache.py` (reject a mixed index) and
      `search_vault.py` (error if query backend ≠ index backend) — turn silent
      corruption into a loud failure.
- [ ] Implement the **semantic E2E** tier (related/unrelated fixtures, Ollama,
      ranking/threshold asserts). Blocked on Ollama availability.
- [ ] Devkit: generator must emit `vault/` uncommitted + committed
      `tests/fixtures/vault/` + `self_test.py` (devkit **OQ-3** / **G1**).
