# Dashboard — what is live and what is next

**The one file that answers "where am I?"** Open this first; everything else in the
vault is reached from it or from search.

It holds **status**, which is the one thing the rest of the brain cannot tell you.
Folders say what archives together. Tags say what a note is about. Embeddings say
what is similar. None of them knows that an item is unchecked, or that a project has
been waiting three weeks on somebody else's reply.

## Why this file is not a note

It sits at `vault/dashboard-index.md` — the **vault root, outside every PARA root**.
The indexer walks `vault/projects`, `vault/areas`, `vault/resources` and
`vault/archive`, so a file here is never embedded, never cached, never returned by a
search. That is deliberate and it is structural: there is no `embed: false` to
forget, because nothing here is opted out — it was never in scope.

**You never need to *search* for a file whose path is a constant.** Search earns its
keep on notes whose location you have forgotten. This one has a fixed address, and
an agent is told that address in `CLAUDE.md`. Embedding it would also be actively
harmful: it churns on every status change, and a vector of "what is next this week"
competes in results against the notes that hold the actual knowledge.

## The rule: point, don't copy

**Link to the note that owns a task. Never mirror its checklist here.**

A copied checkbox has two homes and drifts the first time the wrong one is ticked —
and then this file is not merely stale, it is lying, which is worse than empty. The
checkbox also needs the context around it: the dates, the reasoning, the draft email
underneath. Stripped to a single line it stops being usable.

So what earns a row here is the thing that exists **nowhere else**:

- **Next action** — your judgment about which of a note's open items comes first.
  That is a decision, not a copy.
- **Blocked on** — who or what you are waiting for. This is invisible inside the
  notes; you cannot see it without re-reading a whole file, and it is the single
  most useful column here.
- **Last touched** — how cold a project has gone.

## How to use it

One row per **active** effort. When a project goes inactive, delete its row — this
file is the live set, and the note it pointed to keeps the history.

| Project | Next action | Blocked on | Last touched |
| --- | --- | --- | --- |
| [[example-project]] | *what you would do if you had an hour* | nobody — mine to do | 2026-01-01 |

Keep it short enough to read in one screen. If it does not fit, the problem is
usually that a finished project never got its row removed.

## Finding open items mechanically

This file is curated, not generated — but the exhaustive list is one command away,
so there is no reason to keep a copy of it here:

```bash
grep -rn '^- \[ \]' vault
```

Counting them per note ranks your projects by how much is outstanding:

```bash
for f in $(grep -rl '^- \[ \]' vault); do
  printf '%3s open  %s\n' "$(grep -c '^- \[ \]' "$f")" "$f"
done | sort -rn
```

Tracking tasks as `- [ ]` checkboxes **inside** the note that owns them is the
intended pattern, not a workaround. Dated `- [x]` lines keep *why* and *when* beside
the decision, which a separate task app throws away. Put a volatile checklist inside
a `<!-- second-brain:lexical-only:begin/end -->` fence and ticking a box re-indexes
without re-embedding.
