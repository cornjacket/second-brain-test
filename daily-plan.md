# Daily plan — 2026-07-15

**Focus:** hand-prototyping surface for the devkit — features are built here by hand first
(step 1 of the loop), confirmed to behave, then vendored into `second-brain-devkit` and
regenerated. Tue 07-14 prototyped the whole write path here — `add_note`, `add_glossary_term`,
the wikilink-invariant `note_view`, the `add_note` index-poison fix — all since vendored. Wed
07-15's devkit work (a `doctor` check + server hardening) gets prototyped here first.

- **▶▶ Prototype #30 here first — `doctor` stale-vector detection.** Add the check to
  `scripts/doctor.py`: recompute each note's `content_hash`, compare to the sidecar's, report a
  mismatch as stale-and-repairable (`--repair` re-embeds). Confirm it flags a note whose canonical
  view changed but whose text didn't — then it gets vendored.
- **Prototype #24 — MCP hang-safety** in `scripts/mcp_server.py` + `scripts/embedder.py`: a
  timeout on the embedder's `urlopen`, `stdin=DEVNULL` on git subprocesses, ssh `BatchMode`.
  Exercise by hand (a stalled or down Ollama must error, not hang) before vendoring.
- **Discipline:** every change is prototyped here, then `vendor_golden.py` → `build_template.py`,
  then `tools/ci.py` (10 gates) in the devkit must stay green — the golden IS the regression
  baseline, so a clean structural diff is the acceptance test. Keep sidecars on the **`test`**
  backend so the vendored snapshot stays byte-stable.

```
 golden = build-by-hand, then vendor
   prototype #30 (doctor) ─┐
   prototype #24 (hang)  ──┴─► vendor_golden → build_template → devkit CI 10/10
 the live .git + pre-commit hook still fire here for real (step 1 of the loop)
```
