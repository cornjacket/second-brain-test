# Daily plan — 2026-07-01

**Focus:** Milestone 2 — registration & ingestion. The pipeline plumbing is proven
(M1b), so wire the brain into a target project and then eye the devkit.

- Build `scripts/register.py` — inject an idempotent managed block into a target
  repo's `CLAUDE.md` pointing at this brain.
- Verify idempotency: re-running refreshes the block, never duplicates it.
- Ingestion smoke test: record a note via the registered flow → `search_vault.py`
  finds it.
- Stretch: scaffold `devkit/` now that this repo is a known-good oracle to diff against.
- Watch: semantic validation stays blocked until an Ollama backend is available
  (the `test` backend only proves plumbing).

```
 done ▸ 0001 vault/ · 0002 guard · 0003 seed · M1b plumbing ✅
                              │
 today ▸ M2: register.py → verify idempotent → ingest smoke test
                              │
                    stretch ▸ devkit/ scaffold (reproduce this reference)
```
