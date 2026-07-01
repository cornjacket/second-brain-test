---
id: 0002
title: Markdown line-count guard — warn when a note exceeds 300 non-empty lines
status: done-primary
priority: after-0001
depends_on: 0001
tags: [tooling, hooks, claude-md, markdown, dx]
---

# Task 0002 — Markdown line-count guard

> **Status: primary mechanism implemented.** `scripts/check_line_count.py` +
> the non-blocking pre-commit guard are live and tested. The **optional**
> PostToolUse live-feedback hook is intentionally **not** installed yet (it
> mutates `.claude/settings.json` and wants hook-trust approval) — see below.

## Goal

When a Markdown note in this repo grows past **300 non-empty lines**, surface a
nudge to **segment it into two or more files**. Long notes hurt both human
readability and embedding/retrieval quality (one giant vector per note).

## Scope — what the guard checks

- **Threshold: > 300 non-empty lines** = violation (blank / whitespace-only lines
  do not count).
- **Excluded paths** (never checked, regardless of length):
  - `README.md`
  - everything under `tasks/` (task documents are allowed to be long).
- All other `*.md` files are in scope.

## Components

### Component A — line-count checker script
- New script, e.g. `scripts/check_line_count.py`.
- Input: one (or more) Markdown file path(s).
- Counts **non-empty** lines only; threshold is **> 300**.
- Skips excluded paths (`README.md`, anything under `tasks/`).
- Output contract (finalize at implementation):
  - exit `0` + no output when under threshold or excluded,
  - non-zero exit (or a structured stdout line) naming the file and its count on
    violation, so a caller/hook can act on it.
- Pure stdlib Python; no dependency on the embedder/cache pipeline.

### Component B — the trigger wiring
See the decision below. The chosen mechanism runs Component A and, on violation,
emits a single **emoji-led** line telling the user to segment the file.

Behavior rules:
- **Respect exclusions** (`README.md`, `tasks/`).
- **Never auto-edit.** The guard only surfaces the nudge; the AI must **not**
  split/segment the file on its own. The user must expressly direct any
  restructuring.

## Decision — wiring mechanism

Adopted approach: **pre-commit check (primary coverage) + optional PostToolUse
hook (live in-session feedback).** Both are deterministic and cost zero model
tokens. The standalone CLAUDE.md-directive option is rejected (soft enforcement,
token cost every edit, unreliable "show once" state).

Rationale — the key insight: **a PostToolUse hook only fires when *Claude* edits
a file.** In this second brain, most note growth happens in **Obsidian / a plain
editor**, where no Claude tool runs, so a PostToolUse-only guard would miss the
dominant case. A CLAUDE.md directive has the same blind spot (and is also
Claude-only — Gemini ignores it). A **pre-commit** check catches *every* note
regardless of who or what edited it (Claude, Gemini, Obsidian, vim), making it
the right primary mechanism for this repo, which already ships a
`.githooks/pre-commit`.

### Primary — pre-commit check (editor-agnostic, all coverage)
- Extend the existing `.githooks/pre-commit` (or call Component A from it) to
  check each staged `*.md` (excluding `README.md` and `tasks/`).
- On violation: **warn, do not block** the commit — print the emoji-led
  segmentation nudge to the terminal.
- Catches every note however it was edited; deterministic; zero tokens; works for
  both Claude and Gemini.
- Limitation: fires at commit time, not live mid-edit. The optional hook below
  covers the live case.

### Optional — PostToolUse hook (live feedback while editing with Claude)
- A `PostToolUse` hook in `.claude/settings.json` matching `Edit`/`Write`/
  `MultiEdit`, running Component A on the edited file (exclusions enforced
  **inside** the script, since matchers key on tool name, not path).
- Have the **hook print the warning directly** (no round-trip back through the
  model) so it stays truly zero-token. Drop the earlier "the AI outputs it"
  framing — a deterministic printed line is preferred over an AI-authored one.
- "Display once per edit" falls out naturally (one fire per edit event); dedupe
  repeated edits to the same file within a turn / `MultiEdit` so it doesn't
  multi-fire.
- Claude-Code-only and requires hook-trust approval on each clone — acceptable
  because it's a convenience layer on top of the pre-commit guarantee.
- An idempotent installer (`scripts/install_line_guard_hook.py`, same managed-
  block pattern as the planned `register.py`) can add/refresh this hook config.

## Acceptance criteria

- [x] `scripts/check_line_count.py` counts non-empty lines and flags files with
      > 300; respects the `README.md` and `tasks/` exclusions.
- [x] The pre-commit path warns (without blocking) when a staged in-scope `.md`
      exceeds 300 non-empty lines, however the file was edited.
- [x] Editing `README.md` or any file under `tasks/` never triggers the warning,
      regardless of length.
- [ ] *(optional, not installed)* If the PostToolUse hook is installed, editing an
      in-scope `.md` over threshold surfaces exactly one emoji-led nudge per edit.
- [x] The guard never modifies/splits the offending file — the script only prints.
- [x] The pre-commit wiring needs no separate installer (it lives in the existing
      `.githooks/pre-commit`); an idempotent installer is only needed for the
      optional hook, which is deferred.

### Verified (temp-repo integration test)
- 353-non-empty-line note → single `📏` warning; **commit still succeeds**.
- `README.md` (500 lines) and `tasks/*.md` (500 lines) → no warning.
- Blank/whitespace-only lines are not counted; threshold is strict `> 300`.

### Confirmed decisions (user)
- **Skip the "instant" PostToolUse hook** — user chose not to add the live
  in-session version; the commit-time pre-commit guard is sufficient. Not just
  deferred: intentionally skipped for now.
- **`CLAUDE.md` stays in scope** — we *do* want to be warned if `CLAUDE.md` grows
  too big. We may later give `CLAUDE.md` its own (different) threshold, but the
  current 300-line rule applies to it for now.

### Remaining (optional, opt-in later)
- `scripts/install_line_guard_hook.py` + the PostToolUse hook in
  `.claude/settings.json` for live in-session feedback. Not planned unless the
  user later opts in.

## Notes / risks

- Decide the exact emoji + message wording at implementation (single short,
  scannable line).
- Confirm non-empty-line semantics on fenced code blocks / front-matter (current
  intent: any line with non-whitespace content counts).
- Use the repo-root resolution pattern already used in `scripts/` so paths work
  from arbitrary CWDs.
- Keep the pre-commit warning non-blocking — a hard reject would be hostile to
  in-progress note-taking.
