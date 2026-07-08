# Daily plan — 2026-07-08

**Focus:** Back **in play** as the prototyping surface — the devkit's next work is the
**emitted managed-block thread** (#10 splice helper → #8 auto-linking → #9 README markers),
which all prototype here first. Build + prove them against real Ollama, then hand off
(vendor → template → diff). Stay a clean diff oracle; mothball still nears.

- **Prototype task #10 — the shared "splice a marked block" helper** in the emitted
  `scripts/`, and **refactor this repo's `install_skill.py --nudge` onto it** (no behavior
  change; install→idempotent→uninstall round-trip green). This is the emitted half the devkit
  vendors + templatizes.
- **Then start #8 auto-linking here:** canonical-body embedding (`embed_staged.py`),
  `related_auto:` quoted-wikilink frontmatter (Obsidian graph edges), the `content_hash`
  gate — exercise embed→hydrate→search with real Ollama to confirm no feedback-loop drift.
- **Stay a stable diff oracle** — `self_test.py` green; fix any golden/template mismatch
  here first. CI tooling (compile gate, `check_*`) lives in the devkit, not here.
- Re-sequenced: the earlier "post-merge sync hook + FTS5" as the immediate next is
  superseded — those stay queued, but the managed-block thread jumps ahead.

```
 role: hand-prototype → prove (real Ollama) → hand off to the devkit
                              │
 devkit pulls:  vendor_golden.py → tests/golden → build_template → ci.py diff
                              │
 wed 07-08 ▸ prototype #10 splice helper (refactor --nudge) → start #8 auto-linking
            (embed substance-not-metadata · related_auto frontmatter · content_hash)
```
