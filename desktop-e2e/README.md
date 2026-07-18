# Claude Desktop e2e — confirm your Desktop connection works, human-driven & script-verified

Does your Claude Desktop actually reach **this** brain, and can it read, write, and search it
the way it should? This suite is how you find out. A human is the driver — there is no API to
drive Desktop's GUI — so you **paste a few canned prompts** into Desktop, then run **verifier
scripts** that assert the **deterministic side effects** (a note created + committed, a glossary
term defined) rather than the model's prose. A few checks are inherently human-observed (a refused
read, search ranking); those print as `MANUAL`.

Run it after connecting Desktop to this brain for the first time, after a Desktop update, or any
time you want to confirm the connection still works end-to-end.

## The scenarios write notes — so run them on a disposable branch

Scenarios 01–03 **write** to your vault (`add_note` / `add_glossary_term` commit notes). To keep
your brain pristine, the suite isolates the whole run on a throwaway git branch: Desktop's MCP
server operates on whatever is checked out, so **a disposable branch *is* a throwaway brain**.
Every note the scenarios write commits onto that branch; teardown deletes it and rebuilds the
search index so your working branch comes back **byte-identical** — with **zero Desktop
reconfiguration** (Desktop stays pointed at this brain the whole time).

```
desktop-e2e/setup.sh                 # assert clean + doctor green, then git checkout -b e2e-run
#   … paste the prompts below into Desktop, in order …
python3 desktop-e2e/verify/run_all.py
desktop-e2e/teardown.sh              # delete the branch, rebuild the index, assert byte-identical
```

`setup.sh` refuses to start unless your tree is clean and `doctor.py` is green (a known-good
baseline). `teardown.sh` fails **loudly** (non-zero) if HEAD moved, the tree is dirty, or the
index is not green after restore — that assertion doubles as a standalone "did it clean up?"
check. Both default to this brain and branch `e2e-run` (override with `--brain` / `--branch`).

**Prerequisite:** Claude Desktop is connected to this brain (its `mcp_server.py` registered in
`claude_desktop_config.json`) and the connector shows its tools. If it shows "no tools available",
the server is not being reached. See the brain README's Claude Desktop setup.

## Run

Do the scenarios **in order** (02 depends on 01 seeding the tag vocabulary). For each: paste the
prompt from `prompts/NN-*.md` into Desktop, eyeball the expected reply, then run its verifier —
or run them all at once after doing all the pastes:

```
python3 desktop-e2e/verify/run_all.py
```

`PASS`/`FAIL` are deterministic (brain state); `MANUAL` items you confirm by eye in Desktop.
Exit 0 means every deterministic check held — it does **not** mean the MANUAL items passed.

## Scenarios

| # | Prompt | Deterministic check | Human-observed |
|---|---|---|---|
| 01 | add a note (`ai-agents`, `planning`) | note exists, tags right, committed | reply says "created …" |
| 02 | add a note with a **near-miss** tag `ai-agent` | note exists; brain's rule maps `ai-agent`→`ai-agents` | reply carries a `TAG HINT:` line |
| 03 | add a glossary term `ablation study` | glossary note exists, def + alias, committed | reply says "defined …" |
| 04 | `get_note` on `/etc/passwd` | — | reply **refused**, no file contents |
| 05 | search "how do vector databases work" | — | right seed notes surface |

Scenario 02 is the point of the whole suite: it proves the write-time near-miss tag warning
**reaches the model inside Desktop** — something an automated MCP client (which never renders in
the real Desktop UI) can never demonstrate.
