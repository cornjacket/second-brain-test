---
tags: [tag-one, tag-two]
---

# Note Title

A durable note captures **one idea** — a lesson, a decision, or a piece of
reference worth keeping. State it clearly in the opening lines so both semantic
search and a skimming human get the gist fast.

Link related notes with `[[wikilinks]]`, e.g. [[embeddings]]. If a note grows past
~300 lines, split it into smaller ones.

<!--
Before you write: does this deserve to be a note?
-------------------------------------------------
[what-earns-a-note: BEGIN]
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
[what-earns-a-note: END]

If it doesn't clear that bar, don't write it — an easy-to-write note is exactly how a
brain fills with things nobody will ever search for.

How to use this template
------------------------
1. Copy it into the right PARA root and rename to lowercase-kebab-case.md:
     vault/projects/   a goal-bound effort with an end
     vault/areas/      an ongoing responsibility
     vault/resources/  durable reference material
     vault/archive/    inactive
2. Frontmatter: `tags: [...]` is the ONLY required key. Add others freely
   (e.g. aliases, created) — extra keys are ignored by the pipeline.
3. Delete this comment, write the note, and commit it — the pre-commit hook
   embeds it locally so it becomes searchable.

This file lives in vault/templates/, which is NOT a PARA root, so the template
itself is never embedded or returned by search.
-->
