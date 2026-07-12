# Daily plan — 2026-07-12

**Focus:** this brain is the **hand-prototyping surface** for devkit **#3**. Sat prototyped hybrid
FTS5 + RRF here (`scripts/`, committed `a51870c`) and vendored it into the devkit. Today hand-builds
**#3 increment 2** here first, then keeps the tree clean and vendorable.

- **Prototype #3 inc 2:** add `config/features.toml` + `scripts/features.py`; wire the `hybrid_search`/`rrf_k`
  toggle into `search_vault.search()`; **verify hybrid on/off with real Ollama** before it's vendored.
- **Clean the tree for vendor:** resolve the stale `README.md` managed-block change (commit or restore)
  so `vendor_golden.py` snapshots a tidy working tree.
- **Hold the baseline:** keep `self_test.py` + `doctor.py` green and sidecars on the **`test`** backend, so
  the vendored golden stays byte-stable for the devkit's structural diff.
- **Hand off:** once verified, the devkit's `vendor_golden.py` picks it up — no direct edits over there.

```
 golden (prototype here) ──vendor──► devkit tests/golden ──build_template──► template
   │
   ├─ #3 inc2  config/features.toml + scripts/features.py + toggle   (verify real Ollama on/off)
   ├─ tidy README managed-block; keep test-backend baseline
   └─ self_test + doctor green
```
