# Daily plan — 2026-07-06

**Focus:** Serve as the **prototyping vehicle for `../second-brain-devkit`**. Every
devkit feature is hand-built and proven *here* first (the golden), then productized
into the devkit and diffed back against this repo. Monday's devkit work is OQ-5
**layer 2 (in-place hydrate)** and the **MCP server v1**, so this repo hosts those
prototypes before they're vendored.

- Prototype-first surface: build layer 2 (in-place `hydrate_cache.py` rebuild) and a
  live `scripts/mcp_server.py` here, confirm they behave, *then* the devkit vendors +
  templatizes them.
- Stay a stable, known-good **diff oracle**: keep the tree coherent so the devkit's
  Mode-A generate→diff stays meaningful; `self_test.py` stays green.
- Reactive: if the devkit's diff surfaces a golden/template mismatch, fix it *here*
  first, then let the devkit re-templatize.
- Ollama is live — real embed→hydrate→search + `doctor.py` exercise the semantic path
  here when a prototype needs it.

```
 role: hand-prototype → prove → hand off to the devkit
                              │
 devkit pulls:  vendor_golden.py → tests/golden → build_template → ci.py diff
                              │
 mon 07-06 ▸ prototype here: layer 2 (in-place hydrate) · mcp_server.py v1
             then devkit vendors + diffs back against this repo
```
