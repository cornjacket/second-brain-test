---
name: second-brain
description: Consult the user's personal second-brain — a local vault of conventions, prior decisions, architecture notes, and hard-won tribal knowledge — BEFORE designing systems, choosing conventions/naming, or answering "how do we do X / what did we decide about Y" in a project. Use proactively at the start of a build or design task, and whenever the user references past decisions or team lore.
---

# Second Brain — consult before designing

The user keeps durable knowledge — team conventions, past architectural decisions,
lessons learned — in a personal **second-brain**: a PARA Markdown vault indexed for
semantic search. It is **separate from the current project** you're working in.
Before designing a system, picking a convention or naming scheme, or answering a
"how do we usually…" question, **query the brain first** and build on what it knows.

## Query it

```bash
python3 "${CLAUDE_SKILL_DIR}/query.py" "<natural-language question>"
```

- Prints the brain's location, then up to 5 matches as `distance  <absolute-path>`
  (lower distance = closer match). Add `-k N` for more results.
- Then **read the returned note files** (the paths are absolute) for full content
  before relying on them — a match is a pointer, not the answer.

## When to use (proactively)

- At the **start of a build or design task** — check for existing conventions or prior art.
- When the user references "how we usually…", a past decision, or project lore.
- Before proposing an architecture, naming scheme, or pattern the user may already
  have a standard for.

If nothing relevant comes back, proceed normally — and consider suggesting the user
capture the new decision as a brain note so it's there next time.

## Requirements

The brain embeds queries with a local **Ollama** server. If a query fails with a
connection error, tell the user to start Ollama (`ollama serve`).
