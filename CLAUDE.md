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

The gate below is **deliberately duplicated** into `vault/templates/new-note.md`, which is
what the MCP `get_note_template()` tool returns. That is the exception to link-don't-copy,
and it is justified: the two readers are **disjoint**. An agent in this repo reads *this*
file and can never see an MCP tool; an assistant in Claude Desktop reads the *template* and
can never see this file. It is one rule delivered down two pipes that don't connect — not
two competing sources of truth. Keeping only a pointer here would trade an always-loaded
rule for one the model must remember to go fetch, and forgetting it is **silent**: the note
still gets written, just unfiltered. The two copies cannot drift — a devkit CI gate fails
the build if they differ (`tools/check_note_gate.py`). Edit **this** block; it is canonical.

<!-- BEGIN what-earns-a-note -->
**What earns a note (keep the signal high).** A brain is only as good as its
signal-to-noise — every note should be something *future-you would search for*.
Gate it before capturing:

- **Durable over transient** — the decision and *why*, the lesson, the reusable
  pattern; not status updates or one-off logs that expire.
- **Retrieval test** — "would I search for this in six months?" If no, don't save it.
- **Single source of truth** — if it's already authoritative elsewhere (a repo, a
  doc, a ticket), **link to it, don't copy** — a stale duplicate is worse than none.

The mnemonic: **capture what transfers, not what merely happened** — a signup *log*
is what happened; the *lesson* you drew from it is what transfers.
<!-- END what-earns-a-note -->

- File the note under the right PARA root inside the vault: `vault/projects/`
  (goal-bound effort), `vault/areas/` (ongoing responsibility), `vault/resources/`
  (durable reference), `vault/archive/` (inactive).
- Lowercase kebab-case filename, `.md`, with YAML frontmatter (`tags: [...]`).
  Link related notes with `[[wikilinks]]`. Start from the annotated example at
  [`vault/templates/new-note.md`](vault/templates/new-note.md) — copy it into the
  right PARA root and fill it in (the template dir isn't indexed).
- **Fence diagrams and ASCII art in a no-embed block.** Wrap any decorative region
  between `<!-- second-brain:no-embed:begin -->` and `<!-- second-brain:no-embed:end -->`:
  it stays in the file (Obsidian hides the markers) but never reaches the embedder. A
  note is one vector, so unfenced art dilutes it — and box-drawing characters cost about
  a token each, so a note far short of the ~300-line guideline can still overflow the
  model's context and fail to embed. **The embed budget is tokens, not lines.** Editing
  inside the block is free: the excluded region is invisible to the content hash too, so
  redrawing a diagram triggers no re-embed and no `doctor.py` staleness.
- **Reuse tags; don't split the vocabulary.** Before tagging a note, see what tags
  already exist (`python3 scripts/tag_lint.py`, or the `list_tags` MCP tool) and reuse
  one rather than minting a near-duplicate (`ml`/`machine-learning`, `agents`/`ai-agents`)
  — a near-miss silently splits a group and erodes retrieval. A tag names a *topic* and
  stays lowercase kebab-case; keep provenance (which repo or experiment a lesson came
  from) in the note **body** as a link, not a tag. `scripts/tag_lint.py` reports drift and
  `scripts/tag_apply.py` backfills a rename/merge/removal under review.
- Commit it. That's the whole flow: the **pre-commit** hook embeds the note into
  its `.embed.json` sidecar and the **post-commit** hook refreshes the cache, so a
  committed note is **searchable immediately** — no manual step. (`hydrate_cache.py`
  stays available for a manual/bulk rebuild, e.g. after `embed_vault.py`.) Vault
  sidecars are **derived and git-ignored** (regenerated locally) — do not hand-edit
  or commit them. The only committed sidecars are the deterministic fixtures under
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
  This block is injected and refreshed by project-status:
  https://github.com/cornjacket/project-status

  Do not edit between the begin/end markers — local edits will be
  overwritten on the next `setup-new-repo.sh --update`. To change
  the rules, edit templates/claude-rule.md in project-status
  and re-run `setup-new-repo.sh --update <this-repo-remote>`.

  This block is deliberately a KERNEL: only the rules that would be too
  late if they loaded on demand. Rationale, examples, and the daily-plan
  body structure live in ./project-status-guide.md.
-->
## project-status: commit + daily-plan discipline

This repo is monitored by [`project-status`](https://github.com/cornjacket/project-status): it reconstructs activity from your **git history** and aggregates your `daily-plan.md` across every tracked repo. **Read [`project-status-guide.md`](project-status-guide.md)** (repo root) before writing a daily plan, or whenever a commit message needs more than the rules below.

### Commits

1. Every commit follows this shape. `[Context]` and `[Impact]` are required on any non-trivial commit (a typo or pure formatting may omit them):

   ```
   <domain>(<scope>): <high-level functional summary>
   - [Context]: why this was done / what was learned
   - [Impact]: how it alters the project or system behavior
   ```

2. Title the **system change, not the files**, and write it for a reader who has never seen this repo — these messages are summarized across the whole portfolio. `feat(auth): let users reset a forgotten password by email`, not `add token TTL check to reset handler`.

3. Commit at **task granularity** — never per-prompt — and commit completed work **before the session ends**. Uncommitted work is invisible to the tracker.

4. Immediately after committing, print `✅ <short-hash> — <title>` on its own line.

### Daily plan (`daily-plan.md`, repo root)

5. The first line is exactly `# Daily plan — YYYY-MM-DD` and nothing else — no repo URL. The file is **one** day's plan: always overwritten, never appended.

6. Write the *next* day's plan only when the user explicitly asks to plan ahead — not on an ambiguous "let's stop here". On Friday, write Monday's.

<!-- ai-project-status:end -->
