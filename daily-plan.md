# Daily plan — 2026-07-07

**Focus:** Stay the **prototyping surface + diff oracle** for `../second-brain-devkit`.
Idle since 07-04 on purpose — the recent devkit work (CI coverage, `update_brain.py`, the
design docs) is all devkit-internal and **doesn't emit into a brain**, so there was no
"prototype here first" step. The golden comes back into play for the next **emitted**
features. Keep the tree a clean diff oracle; mothball ([G4](../second-brain-devkit/PLAN.md))
still nears as generation gets more trusted.

- **Next to prototype here (emitted features):**
  - the **`post-merge` sync hook** + sync helper (big-brain Approach A) once task #6 lands
    a remote — pull → re-embed/hydrate, push-after-commit, surface merge conflicts;
  - **hybrid FTS5 search** in `search_vault`/`hydrate`/`update_cache` (devkit task #3).
  Build + prove them here (real Ollama), then let the devkit vendor + templatize.
- **Stay a stable diff oracle** — keep the tree coherent so Mode-A generate→diff stays
  meaningful; `self_test.py` green. CI-tooling (compile gate, `check_*`) lives in the
  devkit, not here.
- **Reactive:** if the devkit's diff surfaces a golden/template mismatch, fix it here first.
- **Ollama is live** — exercise embed→hydrate→search + `doctor.py` when a prototype needs it.

```
 role: hand-prototype → prove → hand off to the devkit
                              │
 devkit pulls:  vendor_golden.py → tests/golden → build_template → ci.py diff
                              │
 07-04 ✅ prototyped here: layer-2 hydrate · mcp_server.py v1 (→ vendored)
 tue 07-07 ▸ next emitted features to prototype here: post-merge sync hook · FTS5 search
```
