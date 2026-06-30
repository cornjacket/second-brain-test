# Daily plan — 2026-06-30

Drive **second-brain-test** to a working core pipeline. PLAN.md is the canonical tracker; this is just the day's shape.

- Re-orient: skim PLAN.md, the `scripts/` pipeline, and SPEC.md invariants before touching code.
- Finish Milestone 1: activate the embed hook + symlink, then verify the full embed → hydrate → search loop end-to-end and commit the generated sidecars.
- Stretch (if time): start Milestone 2 — `register.py` injects an idempotent brain block into a target repo; smoke-test ingestion.
- Respect invariants: one embedder for notes + queries, no hand-edited sidecars, local-first only.
- Known blocker: real semantic-quality check needs the `ollama` backend (unavailable here); `test` backend proves plumbing only.

```
Warm-up ──> M1: activate + verify pipeline ──> commit sidecars ──> [stretch] M2: register + ingest
 reorient        embed → hydrate → search          working brain        idempotent block
```
