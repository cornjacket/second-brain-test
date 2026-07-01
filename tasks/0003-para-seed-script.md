---
id: 0003
title: PARA seed script — wipe & re-seed the vault from a canonical seed set
status: done
priority: after-0001
depends_on: 0001
tags: [tooling, seeding, vault, testing]
---

# Task 0003 — PARA seed script (wipe & re-seed)

> **Status: done.** `seeds/` holds the canonical baseline; `scripts/seed_vault.py`
> seeds/resets `vault/` from it. Chose **Option A** (commit both `seeds/` source
> and the live `vault/` notes). Verified: idempotent seed keeps git clean; `--wipe`
> is a dry run unless `--force`; a wipe removes only PARA `*.md`/`.embed.json` and
> leaves `.obsidian/`, `config/`, `data/`, `.gitkeep`, and non-note files intact.

## Goal

Provide a Python script that **(re)populates the PARA vault from a canonical seed
set**, with a **wipe** option, so the live notes can be reset and re-seeded on
demand. This makes the embed → hydrate → search pipeline repeatable from a clean,
known state (essential for verification and for the devkit using this repo as a
golden reference).

## Why

- Today the seed notes *are* the only copy — there's no way to reset to a known
  baseline after experimenting.
- Verifying the pipeline (M1) repeatedly needs a deterministic starting point:
  wipe → re-seed → embed → hydrate → search.
- Depends on **Task 0001**: seeding targets the new `vault/<para>/` structure.

## Design

### Source of truth
- Canonical seed notes live under a dedicated **`seeds/`** directory mirroring the
  PARA roots:
  ```
  seeds/projects/  seeds/areas/  seeds/resources/  seeds/archive/
  ```
- The existing root notes become this source set (relocate during/with Task 0001):
  - `projects/second-brain.md`
  - `areas/knowledge-management.md`
  - `resources/embeddings.md`, `resources/sqlite-vec.md`
  - `archive/.gitkeep`
- `seeds/` is committed; it is the reproducible baseline.

### Script — `scripts/seed_vault.py`
- Default action: **copy** every note from `seeds/<para>/` into the matching
  `vault/<para>/`, creating dirs as needed. Idempotent (re-running overwrites the
  seeded copies, never duplicates).
- `--wipe`: before copying, remove the seeded note set from `vault/<para>/`
  (the `*.md` notes **and** their `.*.embed.json` sidecars).
  - Guardrails: only touch `*.md` / `.*.embed.json` under the four PARA roots in
    `vault/`; **never** delete `vault/.obsidian/`, `config/`, `data/`, or any
    non-note file. Consider a confirmation flag (or `--force`) so an accidental
    run can't nuke work.
- Pure stdlib (`pathlib`, `shutil`); repo-root resolution like the other
  `scripts/`. No dependency on the embedder/cache.

### Open decision — are the live `vault/` notes committed?
- **Option A (recommended):** commit both `seeds/` (source) and the seeded
  `vault/` notes + sidecars (the reference "working brain"). `seed_vault.py` then
  just resets `vault/` to match `seeds/`. Trade-off: the note text exists twice.
- **Option B:** gitignore `vault/<para>/` notes as derived, commit only `seeds/`.
  Problem: the `.embed.json` sidecars (which we *want* committed as the verified
  brain) live next to the notes, so they'd be ignored too. Rejected unless we
  relocate sidecars.
- Decide at implementation; A keeps the golden-reference artifact intact.

## Acceptance criteria

- [x] `seeds/` holds the canonical PARA seed notes (copied from the current
      `vault/` notes — Option A).
- [x] `python3 scripts/seed_vault.py` populates `vault/<para>/` from `seeds/`
      (idempotent; leaves git clean when already in sync).
- [x] `python3 scripts/seed_vault.py --wipe --force` clears the seeded notes +
      sidecars from `vault/` first, then re-seeds — deterministic roundtrip.
      (`--wipe` alone is a safe dry run.)
- [x] Wipe never touches `.obsidian/`, `config/`, `data/`, `.gitkeep`, or
      non-note files (guardrail-tested).
- [ ] End-to-end `--wipe` → re-seed → **hydrate** → `search_vault.py` returns the
      seeded notes — deferred to **M1b** (needs the deps installed + a hydrate run).

## Notes / risks

- Keep wipe scoped and guarded — destructive by nature.
- If Option A is chosen, document that editing a note means editing it in
  `seeds/` (source) when the change should survive a re-seed, vs. `vault/` for
  throwaway experiments.
