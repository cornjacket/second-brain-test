---
id: 0002
title: Markdown line-count guard — warn when a note exceeds 200 non-empty lines
status: open
priority: after-0001
deferred: true
depends_on: 0001
tags: [tooling, hooks, claude-md, markdown, dx]
---

# Task 0002 — Markdown line-count guard

> **Implementation deferred.** This document captures intent and design only. Do
> not implement until explicitly prioritized.

## Goal

When a Markdown file in this repo grows past **200 non-empty lines**, surface a
one-time nudge to **segment it into two or more files**. Long notes hurt both
human readability and embedding/retrieval quality (one giant vector per note).

## Components

### Component A — line-count checker script
- New script, e.g. `scripts/check_line_count.py`.
- Input: one (or more) Markdown file path(s).
- Counts **non-empty** lines only (lines that are blank or whitespace-only do
  **not** count toward the total).
- Threshold: **> 200** non-empty lines = violation.
- Output contract (to be finalized at implementation time):
  - exit `0` + no output when under threshold,
  - non-zero exit (or a structured stdout line) naming the file and its count
    when over threshold, so a caller/hook can act on it.
- Pure stdlib Python; no dependency on the embedder/cache pipeline.

### Component B — the trigger wiring
Whenever a Markdown file **other than `README.md`** is edited, run Component A on
it. On violation, the AI emits a single **emoji-led** line telling the user the
file should be segmented into two or more files.

Behavior rules:
- **Exclude `README.md`** from the check.
- **Display once per edit.** The warning is shown once when the violating edit
  happens. It is **not** repeated until the file is edited again (the next edit
  re-triggers the check).
- **Never auto-edit.** The AI must **not** split/segment the Markdown file on its
  own. It only surfaces the nudge; the user must expressly direct any
  restructuring.

## Open design decision — how to wire the trigger

Two candidate mechanisms; **pick one at implementation time.** The PostToolUse
hook (Option 1) is the cleaner fit and is the current lean.

### Option 1 (recommended) — PostToolUse tool hook
- A `PostToolUse` hook in `.claude/settings.json` matching `Edit`/`Write`/
  `MultiEdit` on `*.md` paths (excluding `README.md`).
- The hook runs `scripts/check_line_count.py` on the edited file.
- On violation it feeds the result back to the session (e.g. via the hook's
  JSON output / additionalContext) so the AI prints the emoji-led segmentation
  warning.
- "Display once per edit" falls out naturally: the hook fires once per edit
  event, so the warning appears once and only re-appears on the next edit.
- A second script (`scripts/install_line_guard_hook.py`, idempotent — same
  managed-block pattern as the planned `register.py`) can install/update this
  hook config so setup is one command.

### Option 2 (literal original ask) — directive injected into CLAUDE.md
- A script that injects an idempotent **managed block** into `CLAUDE.md`
  instructing the AI: after editing any `.md` file except `README.md`, invoke
  `scripts/check_line_count.py` and, on violation, emit the emoji-led "segment
  this file" nudge once.
- Downside vs. Option 1: relies on the AI remembering to run the check every
  time (soft enforcement), whereas a hook enforces it deterministically.

## Acceptance criteria (when implemented)

- [ ] `scripts/check_line_count.py` correctly counts non-empty lines and flags
      files with > 200.
- [ ] Editing a `.md` file (not `README.md`) that exceeds 200 non-empty lines
      surfaces exactly one emoji-led segmentation warning.
- [ ] Editing `README.md` never triggers the warning regardless of length.
- [ ] The warning is not repeated until the file is edited again.
- [ ] The AI does not modify/split the offending file unless the user explicitly
      asks.
- [ ] Whichever wiring is chosen (hook or CLAUDE.md directive) is installed by an
      idempotent setup script (re-running refreshes, never duplicates).

## Notes / risks

- Decide the exact emoji + message wording at implementation (keep it short and
  scannable, e.g. a single line).
- Confirm the non-empty-line semantics on fenced code blocks / front-matter (do
  they count? current intent: any line with non-whitespace content counts).
- If Option 1 is chosen, verify the hook path resolution works from arbitrary
  CWDs (use the repo-root resolution pattern already used in `scripts/`).
