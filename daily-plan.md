# Daily plan — 2026-07-13

**Focus:** hand-prototyping surface for the devkit. Sun 07-12 prototyped the whole glossary feature
here (the PARA(G) namespace, `glossary_new`/`glossary_scan`/`glossary_autolink_staged`, and the #20
MCP glossary tools) plus the #3 `features.toml` toggle — all vendored into the devkit. Mon 07-13's
lead (**#21**) is **harness-side** (`check_mcp_server.py`), so the golden mostly holds the baseline.

- **Hold the baseline:** `self_test.py` + `doctor.py` green; sidecars on the **`test`** backend so the
  vendored golden stays byte-stable for the devkit's structural diff.
- **If the glossary flashcard/graph tail lands:** it touches `vault/glossary/README.md` here first,
  then vendor → template.
- **#21 needs no golden change** — it exercises the already-emitted `mcp_server.py`; no direct edits to
  the devkit from here.

```
 golden (prototype here) ──vendor──► devkit tests/golden ──build_template──► template
   │
   ├─ baseline: self_test + doctor green, test-backend sidecars byte-stable
   └─ glossary flashcard/graph tail (docs) if it lands; else idle — #21 is harness-side
```
