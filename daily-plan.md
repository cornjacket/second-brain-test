# Daily plan — 2026-07-09

**Focus:** The #10 → #8 thread was prototyped here and handed off (splice helper + full
auto-linking: canonical-body embedding, nomic prefixes, KNN calibration, `related_auto:`
write path, `content_hash` gate — all proven against real Ollama, then vendored → template →
devkit CI 7/7). Next in the thread is **#9 (README markers)**; after that, seed the
**diverse corpus (#15)** here so real semantic structure exists to tune against.

- **Prototype task #9 — the README managed block** in the golden `README.md`: HTML-comment
  markers (`<!-- BEGIN/END generated -->`) wrapping the devkit-owned region, spliced via the
  shared helper so a user's own preamble/appendix is preserved. This is the emitted half the
  devkit vendors + templatizes.
- **Then seed the task #15 diverse corpus here** — many topically-distinct notes embedded
  with real Ollama, so the auto-link `t_max`/topic-count analysis has genuine cluster
  structure (today's ~7 notes are one blob). This repo is where the deferred auto-link
  `--apply` eventually runs once the corpus lands.
- **Stay a clean diff oracle** — `self_test.py` green; resolve any golden/template mismatch
  here first. CI gates (compile, `check_autolink_format`, …) live in the devkit, not here.

```
 role: hand-prototype → prove (real Ollama) → hand off to the devkit
                              │
 wed 07-08 ✅ prototyped #10 helper + #8 auto-linking end-to-end → handed off (devkit CI 7/7)
                              │
 thu 07-09 ▸ prototype #9 README markers (splice via #10 helper)
            → seed #15 diverse corpus (real Ollama) for t_max / topic-count tuning
```
