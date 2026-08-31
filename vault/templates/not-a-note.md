---
embed: false
---

# Title

**This is not a note.** The `embed: false` above keeps this file out of the brain: it is
never embedded, never enters the search cache, and never comes back from a search. It is
ordinary Markdown that happens to live inside a PARA root.

Use it for material that belongs *beside* a note rather than *as* one — a project README,
meeting scratch, a working checklist, a draft, a table you maintain by hand. The point is
colocation: `vault/projects/<project>/` holds the project note and its material together,
so the whole folder archives or deletes as one unit.

<!--
When to reach for this template
-------------------------------
Embedding is the DEFAULT, and that polarity is deliberate. A file nobody marked is
embedded and therefore *visible* — it turns up in a search result, where a wrong inclusion
is obvious and one line fixes it. The opposite default would make a note you forgot to
mark **silently unsearchable**: indistinguishable from a note that was never written, and
discovered on the day you need it and it does not come back.

So the question is not "is this important?" but "would a hit on this be noise?" When
unsure, leave it embedded — a stray search hit is cheap; an invisible note is not.

The key, exactly
----------------
`embed: false` on its own line in the YAML frontmatter (`no` and `off` also work). The
parser fails OPEN: a missing key, a typo, or a value it cannot read all mean *embed*.
Deleting the line puts the file back in the brain on the next commit. Adding it to a file
that was already embedded RETRACTS it — sidecar, vector and search row all go.

There is no `tags:` key here on purpose. Tags are a note's controlled vocabulary; a file
that is not a note has no business adding to it.

Naming, when this lives in a project folder
-------------------------------------------
    vault/projects/algebra/algebra.md            <- the entry note (embedded)
    vault/projects/algebra/algebra--progress.md  <- material (embed: false)
    vault/projects/algebra/practice-test-1.pdf   <- non-Markdown colocates already

The entry note repeats the folder name. It looks redundant and it is the only form that
works: Obsidian resolves [[wikilinks]] by NAME, so [[algebra]] keeps resolving after the
folder moves to vault/archive/, and every note title in the vault stays unique. A
per-folder index.md or README.md would put many identically-named notes in one vault,
breaking wikilink resolution and making search results unreadable.

Everything else in the folder is named {folder}--{descriptor}.md. Folder names carry no
`project-` prefix: the folder ends up in archive/, and a prefix naming its old status
would go stale there.

What does NOT belong in a project folder is a durable lesson that outlives the project.
That is a resource — vault/resources/, flat. Burying it in a folder headed for archive/
is how it becomes unfindable.

Subfolders are for projects/. areas/ does not end and resources/ is filed by topic, so
neither has the "archive as one unit" motive that justifies nesting. Recommended, never
enforced — no script checks any of this.

How to use this template
------------------------
1. Copy it into the folder the material belongs to and rename it.
2. Keep the `embed: false` key; delete this comment; write the file.
3. Commit it. The pre-commit hook will report it as excluded rather than embedding it.

This file lives in vault/templates/, which is not a PARA root, so nothing here is
embedded either way — the key above only starts doing work once you copy this into
projects/, areas/, resources/ or archive/.
-->
