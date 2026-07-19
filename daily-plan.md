# Daily plan — 2026-07-19

**What this repo is (for a newcomer):** `second-brain-test` is the *golden reference* for the devkit
next door — a hand-built, known-good copy of a generated brain. New features are prototyped **here by
hand first**; once they behave, they are vendored into the devkit to serve as its regression
baseline. Think of it as the workbench, not the product.

**Last implemented:** the README search section, rewritten here to describe hybrid lexical+vector
search and the embedding task prefixes as **shipped** (not "planned"), then vendored into the devkit.
Nothing is mid-prototype right now.

**Focus / plan:**
- **Prototype #7 PDF ingestion, milestone M1, HERE.** Build `scripts/chunker.py` (text → overlapping
  token-window chunks with page + char spans) and `scripts/pdf_extract.py` (`pypdf`, optional dep),
  plus a tiny fixture PDF. Confirm they behave by hand, then push through the loop into the devkit.
- Keep the search backend on `test` so the vendored snapshot stays byte-for-byte stable.
- House rule: prototype here → devkit's `vendor_golden.py` → `build_template.py` → the devkit's
  `python3 tools/ci.py` must stay green.

```
 workbench: build #7 M1 by hand here → vendor into the devkit
   7/19 ▶ prototype chunker.py + pdf_extract.py (+ fixture PDF) — deterministic on the `test` backend
   guardrail: keep backend = test; prototype → vendor → devkit CI stays green
```
