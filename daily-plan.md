# Daily plan — 2026-07-16

**Focus:** hand-prototyping surface for the devkit — features are built here by hand first
(step 1 of the loop), confirmed to behave, then vendored into `second-brain-devkit`. Wed 07-15's
`doctor` stale-vector check and the server hang-safety changes were prototyped here and vendored.
Thu 07-16's work is **#27**, which is all on the emitted `mcp_server.py` — so it prototypes here.

- **▶▶ Prototype #27 here — bounded/filterable list tools + `list_tags`.** In
  `scripts/mcp_server.py`: give `list_vault` / `list_glossary_terms` a `match` filter and a capped,
  self-describing reply (state what was omitted — never truncate silently), and add a new
  `list_tags` that returns the vault's tag vocabulary sorted by count (frequency ordering makes a
  cap meaningful). Exercise by hand against this vault's real tags, then vendor.
- **#23 is docs/research** (does a plugin-bundled MCP server reach Claude Desktop?) — **no golden
  change**, so the golden is idle for it.
- **Discipline:** prototype here → `vendor_golden.py` → `build_template.py` → devkit `tools/ci.py`
  (12 gates) + mcp tier stay green; the golden IS the regression baseline (clean structural diff =
  acceptance). Sidecars stay on the **`test`** backend so the vendored snapshot is byte-stable.

```
 golden = build-by-hand, then vendor
   prototype #27 (list tools + list_tags) ──► vendor_golden → build_template → devkit CI 12/12
 (#23 is investigation only — no golden change)
```
