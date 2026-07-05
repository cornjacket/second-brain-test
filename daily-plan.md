# Daily plan — 2026-07-06

**Focus:** Keep serving as the **prototyping vehicle + diff oracle for
`../second-brain-devkit`**. The weekend's features (layer 2 in-place hydrate, MCP server
v1) were hand-built *here* first, then vendored. Monday's devkit work is CI coverage +
`update_brain.py` (both devkit-only, not prototyped here); the next feature that *does*
prototype here is **hybrid FTS5 search**. Stay coherent so the Mode-A diff stays honest.

- **Next prototype surface: hybrid FTS5 search.** When the devkit picks up task #3,
  build the FTS5 table in `data/brain.db` + Reciprocal Rank Fusion inside
  `search_vault.search()` *here* first, prove it against real Ollama, then let the devkit
  vendor + templatize. (nomic `search_document:`/`search_query:` prefixes likewise.)
- **Stay a stable diff oracle.** Keep the tree known-good so the devkit's
  generate→diff stays meaningful; `self_test.py` green. CI-tooling work (py_compile,
  `check_mcp_server.py`) lives in the devkit, not here.
- **Reactive.** If the devkit's diff surfaces a golden/template mismatch, fix it *here*
  first, then let the devkit re-templatize.
- **Ollama is live** — real embed→hydrate→search + `doctor.py` exercise the semantic path
  when a prototype needs it (as they did for the MCP server).
- **Mothball watch (G4).** As `update_brain.py` and trustworthy generation land, this
  repo nears mothball — its role as the hand-prototyping surface winds down.

```
 role: hand-prototype → prove → hand off to the devkit
                              │
 devkit pulls:  vendor_golden.py → tests/golden → build_template → ci.py diff
                              │
 weekend 07-04 ✅ prototyped here: layer 2 hydrate · mcp_server.py v1 (→ vendored)
 mon 07-06 ▸ next to prototype here: hybrid FTS5 search + RRF (task #3), on demand
```
