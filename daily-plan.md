# Daily plan — 2026-07-17

**What this repo is (for a newcomer):** `second-brain-test` is the *golden reference* for the devkit
next door — a hand-built, known-good copy of a generated brain. New features are built **here by hand
first**; once they behave, they're copied ("vendored") into the devkit to serve as its regression
baseline. Think of it as the workbench, not the product.

**Where we left off:** the recent features — tag hygiene and the new "reuse existing tags" note-taking
rule — were prototyped here and already vendored into the devkit. Nothing is mid-prototype right now.

**Today — on standby:**
- **Nothing new is queued to prototype.** Today's devkit work is human-run acceptance (exercising the
  Desktop test kit) and the #23 plugin *research* — neither of which changes this repo.
- **If a fix surfaces** while running the Desktop e2e kit, do it here first, then push it through the
  loop: `python3 tools/vendor_golden.py` → `python3 tools/build_template.py` → the devkit's
  `python3 tools/ci.py` must stay green.
- **House rule:** keep the search backend on `test` so the vendored snapshot stays byte-for-byte stable.

```
 golden = the workbench: build by hand here, then vendor into the devkit
   today: nothing queued to prototype
   on call: if a Desktop-test fix is needed → fix here → vendor → devkit CI stays green
```
