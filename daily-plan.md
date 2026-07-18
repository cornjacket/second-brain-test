# Daily plan — 2026-07-18

**What this repo is (for a newcomer):** `second-brain-test` is the *golden reference* for the devkit
next door — a hand-built, known-good copy of a generated brain. New features are built **here by hand
first**; once they behave, they're copied ("vendored") into the devkit to serve as its regression
baseline. Think of it as the workbench, not the product.

**Where we left off:** the whole Desktop e2e kit — the 5-scenario verifier suite, the disposable-branch
setup/teardown, and the #36 pure-client cross-session test — was prototyped **here** and vendored into
the devkit, which emits it into every brain. Nothing is mid-prototype right now.

**Today — on standby; a fix or two may come back from running the kit:**
- **Nothing new queued to prototype.** The devkit's active work is running the Desktop e2e suites
  against the real brain and folding in two findings (a `list_tags` match filter for the pure-client
  tag query; the cosmetic "pushed" no-op on the disposable branch).
- **If either fix touches emitted files, it starts HERE.** Prototype in `desktop-e2e/`, then push it
  through the loop: `python3 tools/vendor_golden.py` → `python3 tools/build_template.py` → the
  devkit's `python3 tools/ci.py` must stay green.
- **House rule:** keep the search backend on `test` so the vendored snapshot stays byte-for-byte
  stable.

```
 golden = the workbench: build by hand here, then vendor into the devkit
   on standby — e2e kit already prototyped + vendored; nothing mid-flight
   on call: if a Desktop-test fix is needed → fix here → vendor → devkit CI stays green
```
