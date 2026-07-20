# Daily plan — 2026-07-20

**What this repo is (for a newcomer):** `second-brain-test` is the *golden reference* for the devkit
next door — a hand-built, known-good copy of a generated brain. New features are prototyped **here by
hand first**; once they behave, they are vendored into the devkit to serve as its regression
baseline. Think of it as the workbench, not the product.

**Last implemented:** #7 PDF ingestion, prototyped here through M6 and vendored — chunking,
extraction, the PDF cache and search, `add_pdf`, and the interactive `add_pdf_guided` picker that
walks folder → PDF → PARA via MCP elicitation. Nothing is mid-prototype right now.

**Focus / plan:**
- **Prototype the source-folder permission fix HERE** (devkit task #1): `scripts/add_pdf.py`
  `list_pdfs` reports an unreadable folder as empty — `is_dir()` is True but `glob` swallows
  `PermissionError` and returns `[]`. Make "denied" distinguishable from "empty" by hand, then push
  it through the loop.
- Carry it through the surfaces that expose it: a `readable` signal on the `list_inbox_pdfs` MCP
  tool, and a source-folder preflight in `scripts/doctor.py`.
- Real-world provenance: this surfaced ingesting an actual PDF, where macOS TCC denied `~/Downloads`
  (a default source folder) and the empty listing read as "no PDFs here" — so the fixture worth
  building is a folder the test process genuinely cannot read.
- Keep the search backend on `test` so the vendored snapshot stays byte-for-byte stable.
- House rule: prototype here → devkit's `vendor_golden.py` → `build_template.py` → the devkit's
  `python3 tools/ci.py` must stay green.

```
 workbench: fix the permission bug by hand here → vendor into the devkit
   7/20 ▶ list_pdfs: permission-denied ≠ empty ──► list_inbox_pdfs `readable` · doctor preflight
   guardrail: keep backend = test; prototype → vendor → devkit CI stays green
```
