---
id: 0001
title: Migrate repo to the vault/-rooted directory layout documented in README
status: open
priority: next
tags: [refactor, layout, paths, obsidian]
---

# Task 0001 — Migrate to the `vault/`-rooted directory layout

## Goal

Make the **actual** repo structure match the **target layout** documented in
[`README.md`](../README.md) → *Layout*. Today the README describes the intended
structure, but the code and files still use the old flat layout. This task closes
that gap.

## Why

- The README now tells Obsidian users to open `vault/` as the vault root (so
  `.obsidian/`, Python scripts, and the SQLite DB stay out of the note space).
  That only works once notes actually live under `vault/`.
- Keeps the human note space (`vault/`) cleanly separated from machine artifacts
  (`scripts/`, `data/`, `.githooks/`).

## Current vs. target

```
CURRENT (flat)                      TARGET (README Layout)
projects/   areas/                  vault/projects/  vault/areas/
resources/  archive/                vault/resources/ vault/archive/
.cache/vault.db   (derived)         data/brain.db    (derived)
scripts/                            scripts/          (unchanged location)
.githooks/pre-commit                .githooks/pre-commit (unchanged location)
(no config/)                        config/           (optional, may stay empty)
```

## Concrete changes required

### 1. Move the PARA note roots under `vault/`
- `git mv projects areas resources archive` into a new `vault/` directory.
- This moves the `.md` notes **and** any committed `.*.embed.json` sidecars with
  them (paths inside sidecars are not absolute, so contents are unaffected).
- Coordinates with **Task 0003**: the canonical seed notes' home becomes
  `seeds/<para>/`, and `vault/<para>/` is (re)populated by `seed_vault.py`. Decide
  with 0003 whether the moved notes land directly in `vault/` (then copied back to
  `seeds/`) or are relocated to `seeds/` first and seeded into `vault/`.

### 1b. Activate the pipeline (gates all note generation)
- `chmod +x .githooks/pre-commit`; `git config core.hooksPath .githooks`.
- Symlink `GEMINI.md` → `CLAUDE.md` so both AIs read identical instructions.
- This is done **here** (not deferred to M1) so the restructure's own smoke test
  and the later M1 verification both run against an active hook.

### 2. Repoint the embed-staging logic (`scripts/embed_staged.py`)
- `PARA_ROOTS = ("projects", "areas", "resources", "archive")` (line ~22) — the
  staged-file filter at line ~34 does `line.split("/", 1)[0] in PARA_ROOTS`.
  After the move, staged paths look like `vault/projects/foo.md`, so the first
  path segment is `vault`. Fix by either:
  - prefixing the roots: match `vault/<root>/…`, **or**
  - changing the filter to detect notes anywhere under `vault/`.
- `sidecar_path()` (line ~41) uses `REPO_ROOT / p.parent / …` — already
  path-relative, so it keeps working once the note paths include `vault/`.

### 3. Repoint the cache path (`data/brain.db`)
- `scripts/hydrate_cache.py` (lines ~21–22):
  `CACHE_DIR = REPO_ROOT / ".cache"` → `REPO_ROOT / "data"`;
  `DB_PATH = CACHE_DIR / "vault.db"` → `CACHE_DIR / "brain.db"`.
- `scripts/search_vault.py` (line ~21):
  `DB_PATH = REPO_ROOT / ".cache" / "vault.db"` → `REPO_ROOT / "data" / "brain.db"`.
- `scripts/hydrate_cache.py` `find_sidecars()` (line ~26) does
  `REPO_ROOT.rglob(".*.embed.json")` — recursive, so it still finds sidecars under
  `vault/`. No change needed, but confirm it does **not** now also pick up
  `data/` or `config/` (it won't, those have no sidecars).

### 4. Update ignore / attribute rules
- `.gitignore`: `.cache/` → `data/` (keep the derived DB out of git). Decide
  whether to `git rm -r --cached .cache` if it was ever tracked (it is gitignored,
  so likely untracked already).
- `.gitattributes`: `.*.embed.json merge=binary` is path-agnostic — no change.

### 5. Update the pre-commit hook (`.githooks/pre-commit`)
- The hook calls `scripts/embed_staged.py`; its comment references "staged PARA
  notes." No path logic lives in the hook itself, so only update the comment if
  the root-matching strategy in step 2 changes wording. Verify the hook still
  fires for notes committed under `vault/`.

### 6. Create the supporting dirs
- `data/` — created automatically by `hydrate_cache.py` (`CACHE_DIR.mkdir`), but
  add a `.gitkeep` if an empty tracked dir is desired.
- `config/` — optional; create with a `.gitkeep` only if we want it present now.
- `vault/.obsidian/` — **not** created by us; Obsidian generates it when the user
  opens `vault/`. Leave it gitignored or untracked as preferred.

### 7. Sweep docs for stale path references
- `CLAUDE.md` — "Recording knowledge" / "Querying knowledge" sections reference
  PARA roots and `.cache/vault.db`; update to `vault/<root>/` and `data/brain.db`.
- `SPEC.md` — § for layout, sidecar schema, and runtime mention `projects/…`,
  `.cache/vault.db`; update to the new paths.
- `PLAN.md` — Milestone 1 line referencing PARA seed notes paths.
- `README.md` — Quickstart commands (`git add areas/ …`) should become
  `git add vault/areas/ …`; the Layout block is already correct (it's the target).

## Acceptance criteria

- [ ] All PARA notes + sidecars live under `vault/` (`projects/ areas/ resources/ archive/`).
- [ ] Cache builds to `data/brain.db` (not `.cache/vault.db`).
- [ ] Committing a note under `vault/<root>/` triggers the hook and stages its
      `.embed.json` sidecar (verify with `SECOND_BRAIN_EMBEDDER=test` for a clean,
      deterministic diff).
- [ ] `python3 scripts/hydrate_cache.py` builds the cache from the moved sidecars.
- [ ] `python3 scripts/search_vault.py "<query>"` returns ranked rows from `data/brain.db`.
- [ ] No script, hook, `.gitignore`, or doc references `.cache/vault.db` or a
      top-level `projects/`/`areas/`/`resources/`/`archive/` path anymore
      (`grep -rn -E "\.cache/vault\.db|^(projects|areas|resources|archive)/"`).

## Verification

```bash
git config core.hooksPath .githooks          # ensure hook is active
echo "..." > vault/areas/migration-smoke.md  # add a throwaway note
git add vault/areas/ && git commit -m "test: smoke"   # hook writes sidecar
python3 scripts/hydrate_cache.py             # builds data/brain.db
python3 scripts/search_vault.py "migration smoke"      # returns the note
git rm vault/areas/migration-smoke.md vault/areas/.migration-smoke.embed.json
```

## Notes / risks

- Use `git mv` (not plain `mv`) so history follows the files.
- This must land as **one** task commit per CLAUDE.md schema (moves + path edits +
  doc sweep together), since a half-migrated tree breaks both the hook and search.
- **This task gates the rest of the build:** it activates the hook and creates the
  `vault/` structure, so Task 0003 (seeding) and the M1 verification/sidecar-commit
  steps all depend on it. No further PARA notes are generated until this lands.
