# Daily plan — 2026-07-21

**What this repo is (for a newcomer):** `second-brain-test` is the *golden reference* for the devkit
next door — a hand-built, known-good copy of a generated brain. Features are prototyped **here by
hand first**; once they behave, they are vendored into the devkit as its regression baseline. The
workbench, not the product.

**Last implemented:** #38 (permission-denied ≠ empty) prototyped and vendored; the golden is clean,
with no mid-prototype work parked.

**Focus / plan:**
- **Prototype #39 — the embed-excluded block — HERE by hand:** a marker that keeps decorative text
  (ASCII diagrams) out of `canonical_body()` for both embedding and the content hash.
- Prove the invariant: editing the marked region must **not** re-embed or flag the vector stale.
- Then hand it to the devkit loop: `vendor_golden.py` → `build_template.py` → `tools/ci.py` green.
- Keep the search backend on `test` so the vendored snapshot stays byte-for-byte stable.

```
 workbench: prototype #39 by hand → vendor into the devkit
   7/21 ▶ marked decorative block: strip from embed + hash · prove edit-doesn't-re-embed
   guardrail: backend = test; prototype → vendor → devkit CI stays green
```
