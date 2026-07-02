# Second Brain — Agent Memory

You are working **inside a Second Brain**: a PARA Markdown vault (for humans) plus
a local SQLite `vec0` cache (for you). The full contract is in [SPEC.md](SPEC.md);
this file is the operational memory.

> `GEMINI.md` is a symlink to this file so Claude and Gemini read identical
> instructions.

## North star — this repo is the generator's spec

The eventual [`second-brain-devkit`](https://github.com/cornjacket/second-brain-devkit)
will **generate a copy of this repo** from its structure + git history +
`PLAN.md`/`tasks/`. So every action here is the generator's source material:
**if it isn't recorded, the generator can't reproduce it.** Keep work fully
traceable — schema-compliant commits (see *Git Automation*), a `tasks/` doc for
non-trivial work, and `PLAN.md` kept in sync. Favor legibility over speed.

## Recording knowledge

Durable lessons, insights, and architecture understandings belong here as **PARA
notes** — there is no separate ingestion path; a note *is* the ingestion.

- File the note under the right PARA root inside the vault: `vault/projects/`
  (goal-bound effort), `vault/areas/` (ongoing responsibility), `vault/resources/`
  (durable reference), `vault/archive/` (inactive).
- Lowercase kebab-case filename, `.md`, with YAML frontmatter (`tags: [...]`).
  Link related notes with `[[wikilinks]]`.
- Commit it. On commit the hook refreshes the note's `.embed.json` sidecar
  locally, then run `hydrate_cache.py` to update the cache. Vault sidecars are
  **derived and git-ignored** (regenerated locally) — do not hand-edit or commit
  them. The only committed sidecars are the deterministic fixtures under
  `tests/fixtures/vault/`.

## Querying knowledge

Before solving something from scratch, search what the brain already knows:

```bash
python3 scripts/search_vault.py "<natural-language query>"
```

After adding or editing notes, rebuild the cache:

```bash
python3 scripts/hydrate_cache.py
```

## Invariants & safety

- **Same model for notes and queries.** Search only works if the query is
  embedded by the same backend/model as the notes. Both go through
  `scripts/embedder.py`; do not bypass it. The backend is set once in
  `config/embedder.toml` (`ollama` = real semantic search; `test` = deterministic
  plumbing) and overridable per-command with `SECOND_BRAIN_EMBEDDER`.
- **Never** edit a `.embed.json` sidecar by hand or let git conflict markers into
  one (`merge=binary` is enforced).
- **Never commit live-vault vectors** (they're machine/model-dependent, derived,
  git-ignored). Only the deterministic `test`-backend `tests/fixtures/vault/`
  sidecars are committed — and this golden repo is **pinned to `test`**: don't
  commit `ollama` fixtures. `scripts/self_test.py` verifies the fixtures byte-diff.
- **Never** add a cloud vector store. This brain is local-first.
- The cache (`data/brain.db`) is derived — safe to delete and rebuild anytime.

## First-time setup

```bash
git config core.hooksPath .githooks   # activate the embed hook
pip install -r requirements.txt        # sqlite-vec (+ apsw fallback)
```

<!-- ai-project-status:begin -->
<!--
  This block is injected and refreshed by ai-project-status:
  https://github.com/cornjacket/ai-project-status

  It defines the commit-message discipline this repo must follow so
  the meta-repo can summarize cross-portfolio activity in summary.md.

  Do not edit between the begin/end markers — local edits will be
  overwritten on the next `setup-new-repo.sh --update`. To change
  the rules, edit templates/claude-rule.md in ai-project-status
  and re-run `setup-new-repo.sh --update <this-repo-remote>`.
-->
## Knowledge Extraction & Git Automation

This repo is monitored by [`ai-project-status`](https://github.com/cornjacket/ai-project-status). It no longer reads a `log.md` file — backward-looking activity is reconstructed **directly from your git history**. Your job is to make every commit message a high-level, self-contained telemetry record so the meta-repo can summarize cross-portfolio activity in `summary.md`.

### Commit-message schema

Every commit MUST follow this shape:

```
<domain>(<scope>): <high-level functional summary>
- [Context]: Why this was done / what was learned.
- [Impact]: How it alters the project or system behavior.
```

### Rules

1. **The title summarizes the functional change, not the files.** Describe the overall behavior change or architectural decision (`engine(telemetry): replace log.md mining with commit parsing`), NOT a list of touched file names (`update _lib.py and tests`). A reader scanning `git log` should grasp *what changed in the system* from the title alone.

2. **`[Context]` and `[Impact]` are required on any non-trivial commit.** `[Context]` captures the why / the lesson learned; `[Impact]` captures how the project or system behavior changes. Each may span multiple lines. Trivial mechanical commits (typo, formatting) may omit them.

3. **Commit at task granularity — never per-prompt.** Multiple prompts inside one task land in one commit. Open a new commit when the focus changes (a new task, a substantively different question, a meaningfully new concept). Avoid both **commit-per-prompt** (noise that drowns out signal) and **task-without-a-commit** (gaps that make the history untrustworthy).

4. **Automate the commit before session close.** Stage the work (`git add`) and run `git commit -m` with a schema-compliant message before ending the session. Do not leave completed work uncommitted — uncommitted work is invisible to the meta-repo.

5. **Announce each task commit.** Immediately after committing, print `✅ <short-hash> — <title>` on its own line in the conversation, so the user can scan the transcript for recorded work at a glance. One checkmark per task commit — the commit *is* the record, so there is nothing else to back-fill.

## Daily plan (daily-plan.md)

`daily-plan.md` is a **forward-looking** plan file at the repo root. It captures the intent for one working day. ai-project-status aggregates every tracked repo's `daily-plan.md` into [`daily-plan-summary.md`](https://github.com/cornjacket/ai-project-status/blob/main/daily-plan-summary.md).

### Rules

1. **Single-day scope.** The file represents *one* day's plan. It is **always overwritten**, never appended. History of what actually happened lives in your git history and `summary.md`.

2. **Header carries the date.** The first line MUST be `# Daily plan — YYYY-MM-DD`, where the date is the day the plan is *for*. The aggregator parses this to detect stale plans; an unparseable header is treated as stale.

3. **Body is a 100-ft view, written as a bullet list.** Capture the day's intent as a short bullet list (a handful of bullets, not a wall of prose), plus a small ASCII diagram (timeline, flow, milestones) that conveys the shape of the day at a glance. Each bullet is one scannable line of intent. Don't write a dense paragraph — the aggregated `daily-plan-summary.md` is meant to be skimmed in seconds. Don't write granular tasks either — your commit history records granularity after the fact.

4. **Forward-write rule.** Overwrite `daily-plan.md` with the next working day's plan **only when the user explicitly asks to plan tomorrow** — e.g., "write tomorrow's plan", "set up tomorrow", or an end-of-day signoff that includes a forward-planning intent. Do NOT auto-trigger on ambiguous "let's stop here" or "good for today" signoffs — wait for an explicit forward-planning ask. If today is Friday, write Monday's plan (the aggregator's weekend tolerance keeps the Friday-written-on-Friday plan valid through the weekend; Monday's plan is what's needed for Monday).

5. **Start-of-session safety net.** A `SessionStart` hook (installed at `.claude/hooks/check-daily-plan.py`) checks `daily-plan.md` freshness against today's most-recent-weekday. If stale or missing, it injects a prompt instructing you to ask the user for today's plan and overwrite the file before doing other work. Treat this as a hard precondition — don't proceed with other tasks until the plan is fresh.

<!-- ai-project-status:end -->
