# project-status guide

<!--
  Installed and overwritten by project-status:
  https://github.com/cornjacket/project-status

  This whole file is upstream-managed — local edits are replaced on the next
  `setup-new-repo.sh --update <this-repo-remote>`. To change it, edit
  templates/project-status-guide.md in project-status.
-->

Reference for the commit and daily-plan discipline this repo follows. The hard
rules live in `CLAUDE.md` (always loaded); everything here is the *why*, the
worked examples, and the structure you need **while writing** a commit message
or a daily plan. Read it at those two moments — you do not need it otherwise.

## Why this exists

[`project-status`](https://github.com/cornjacket/project-status) tracks several
repos at once. It no longer reads a `log.md` file: backward-looking activity is
reconstructed **directly from git history**, and forward-looking intent from each
repo's `daily-plan.md`. Two artifacts come out of it:

- [`summary.md`](https://github.com/cornjacket/project-status/blob/main/summary.md)
  — an interpretive, daily-resolution rollup of what changed across all repos.
- [`daily-plan-summary.md`](https://github.com/cornjacket/project-status/blob/main/daily-plan-summary.md)
  — every repo's current plan in one place, with stale plans flagged.

So a commit message here is **telemetry**, not decoration: it is the only input
the rollup has. A message that makes sense only to someone deep in this repo
today summarizes into noise tomorrow.

## Commit messages

### The schema

```
<domain>(<scope>): <high-level functional summary>
- [Context]: Why this was done / what was learned.
- [Impact]: How it alters the project or system behavior.
```

`[Context]` and `[Impact]` may each span multiple lines. Trivial mechanical
commits (typo, formatting) may omit them; anything else may not.

### Write the title for a stranger

The title describes the **behavior change or architectural decision**, not the
files touched. A reader scanning `git log` should grasp *what changed in the
system* from the title alone.

- Good: `engine(telemetry): replace log.md mining with commit parsing`
- Bad: `update _lib.py and tests`

Because these messages are summarized **across the whole portfolio**, assume the
reader knows neither your file names nor your internal shorthand. Name the
capability in plain language and say what it does for the product or the user,
then give the detail. A bare `refactor: lazy-import db` or `wire gate 4/7` is
too esoteric to survive the rollup. This applies to the title **and** to
`[Context]` / `[Impact]`.

- Good: `feat(auth): let users reset a forgotten password by email`
- Bad: `add token TTL check to reset handler`

### Granularity

One commit per **task**, not per prompt. Several prompts inside one task land in
a single commit. Open a new commit when the focus changes — a new task, a
substantively different question, a meaningfully new concept.

Both failure modes are real: **commit-per-prompt** buries signal in noise, and
**task-without-a-commit** leaves gaps that make the history untrustworthy.

### Before the session ends

Stage the work and commit it with a schema-compliant message before you finish.
Uncommitted work does not exist as far as the tracker is concerned.

Right after each task commit, print `✅ <short-hash> — <title>` on its own line
so the user can scan the transcript for recorded work. One checkmark per task
commit — the commit *is* the record, so there is nothing to back-fill.

## The daily plan

`daily-plan.md` at the repo root is the **forward-looking** companion to your git
history: the intent for one working day. It is aggregated into
`daily-plan-summary.md` alongside every other tracked repo.

### Header

The first line must be exactly:

```
# Daily plan — YYYY-MM-DD
```

…where the date is the day the plan is *for*. The aggregator parses this line to
detect stale plans, and an unparseable header counts as stale.

Put **nothing else on that line — especially not the repo's URL**. project-status
already knows this repo's URL from its own registry and links the repo name to it
automatically, so the one-click link is handled for you. A hand-written URL can
only go stale (e.g. after a rename); never write one anywhere in this file.

### Body structure

Use this order, so the aggregated summary reads consistently across the whole
portfolio:

1. **`**What this repo is (for a newcomer):**`** — one or two plain-language
   sentences so a reader who has *never seen this repo* understands what it is
   and what it does. This is the standalone context that makes the plan legible
   in the cross-portfolio rollup, and it is what gets quoted in the workspace
   roster. Keep it stable day to day; revise it only when the repo's purpose
   actually shifts.
2. **`**Last implemented:**`** — a one-liner naming the most recent thing
   shipped, so the reader knows where the repo currently stands.
3. **Focus / plan** — a short bullet list of the day's intent. A handful of
   scannable one-line bullets, not a wall of prose: the summary is meant to be
   skimmed in seconds. Don't write granular tasks either — your commit history
   records granularity after the fact.
4. **A small ASCII diagram** (timeline, flow, milestones) conveying the shape of
   the day at a glance.

### Single-day scope

The file represents *one* day. It is always overwritten, never appended — the
history of what actually happened lives in your git history and in `summary.md`.

### When to write tomorrow's plan

Overwrite `daily-plan.md` with the next working day's plan **only when the user
explicitly asks to plan ahead** — "write tomorrow's plan", "set up tomorrow", or
an end-of-day signoff that clearly includes forward-planning intent. Do **not**
auto-trigger on an ambiguous "let's stop here" or "good for today"; wait for the
explicit ask, or you will destroy today's plan before it has been aggregated.

If today is Friday, write **Monday's** plan. The aggregator is weekend-tolerant:
a Friday plan stays fresh through Sunday, so Monday's plan is the one that's
actually missing.

### Start-of-session safety net

A `SessionStart` hook at `.claude/hooks/check-daily-plan.py` checks the plan's
freshness against today's most-recent weekday. When the plan is missing or
stale it injects a prompt telling the assistant to ask the user for today's plan
and overwrite the file before doing anything else. Treat that as a hard
precondition — don't proceed with other work until the plan is fresh.

(The hook is Claude Code-specific. If you are a different assistant, apply the
same check yourself at the start of a session.)
