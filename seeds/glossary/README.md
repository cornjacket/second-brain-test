# Glossary — the brain's controlled vocabulary (the **G** in PARA(G))

This folder is a **controlled-vocabulary layer**: one atomic note per **pre-identified**
term, and every use of that term across the vault links back to its definition. It is a
*different axis* from PARA — not a fifth actionability bucket, but an orthogonal note **type**,
a sibling of `templates/`. Hence **PARA(G)**: **P**rojects · **A**reas · **R**esources ·
**A**rchive, plus a **G**lossary.

## What earns a glossary note

A term earns a `glossary/<term>.md` note only when it is **pre-identified** as
glossary-worthy — **reused** across notes, or **non-obvious** enough that future-you will want
the definition. A word used once does not get a node (that is how a vault fills with stubs).
The set of glossary terms *is* your controlled vocabulary.

## How glossary notes differ from PARA notes

- **Not semantically searchable — by design.** Glossary notes are **excluded from the vector
  index** (`data/brain.db`): they never get an `.embed.json` sidecar and never appear in
  `search_vault.py` results. A one-line definition is keyword-dense and would rank too high for
  its own term, crowding out richer notes. Their value is carried by **how they are
  referenced** (the link graph), not by embedding proximity — the **symbolic** retrieval layer,
  not the semantic one. This falls out for free: `glossary/` is not a PARA root, and the whole
  embed/cache pipeline scopes to PARA roots (exactly like `templates/`).
- **The inline `[[term]]` links _are_ embedded** — and that is correct. A link written into
  another note's *body* is genuine substance, so it is embedded as part of that note. Only the
  definition note itself is excluded.
- **`type: glossary` is the tool-facing marker.** The folder is for humans; the frontmatter
  `type: glossary` key is what tools (the scan, flashcards, graph coloring) key off.

## Adding a term

Run the scaffolder — it slugifies the name, refuses to overwrite an existing term, and writes
the shape below (fill in the definition, then commit):

```bash
python3 scripts/glossary_new.py "retrieval substrates"   # -> glossary/retrieval-substrates.md
```

Prefer to hand-write it? Create `<term>.md` here (lowercase-kebab-case) with this shape:

```markdown
---
type: glossary
aliases: []          # optional surface forms the MCP lookup should also match
tags: [glossary]
---

# retrieval substrates

retrieval substrates ? A one-line, atomic definition.

#flashcards/glossary
```

The `type: glossary` marker is what tools key off. The `Term ? <definition>` card + the
`#flashcards/…` deck tag make it a valid **Spaced Repetition** plugin card out of the box, so
your glossary doubles as a flashcard deck. Glossary notes aren't embedded, so there is no
sidecar to manage.

### Aliases and tags

- **Acronyms and alternate surface forms go in `aliases:`**, never in the title or as a tag —
  `aliases: [DDL, data definition language]`. Aliases are what `lookup_glossary_term` resolves and
  what auto-linking matches; a bare `# DDL` title or a `ddl` tag would not.
- **Tags are topical and shared, not per-term.** A tag buckets a term by domain (`sql`,
  `retrieval`, `embeddings`), so several terms carry the same one; the scaffold seeds
  `tags: [glossary]` and you add a topical tag or two by hand. Never mint a per-term tag (`ddl`,
  `rrf`) — a tag on a single note is a hygiene singleton, and a near-duplicate splits the
  vocabulary exactly like a near-miss tag.

### Adding a term from Claude Desktop

The MCP tool `add_glossary_term(term, definition, aliases)` does all of this from Claude Desktop:
it writes the same scaffold, runs the link-on-use sweep, then commits and pushes. It lands the
term with `tags: [glossary]` only (topical tags stay a hand step, by design). One thing to know —
**Claude Desktop sees only a tool's *description*, never this README** — so the "what earns a
term" bar Desktop follows lives in that tool's docstring in `scripts/mcp_server.py`, which is the
place to change what Desktop is told.

## Linking terms across the vault

Wherever a glossary term appears in another note's body, link it to its definition with
`[[term]]` — that inline link is what carries the term's meaning (and draws the graph edge).
There are three ways to get the links in, all using the same engine (first unlinked occurrence
per note, **idempotent**, so nothing is ever double-linked):

```bash
python3 scripts/glossary_new.py "corpus"     # scaffolds AND links the new term (--no-relink to skip)
python3 scripts/glossary_scan.py             # report unlinked occurrences across the vault (dry run)
python3 scripts/glossary_scan.py --apply     # insert the links across the vault
```

- **Adding a term** with `glossary_new.py` links it wherever it already appears — the automatic path.
- **`glossary_scan.py`** is the on-demand whole-vault pass (e.g. for terms you hand-wrote).
- **Automatic on commit:** set `glossary_autolink = true` in `config/features.toml` and the
  pre-commit hook links known terms in each **staged** note before embedding it (off by default —
  it edits your note bodies). All three edit bodies, so the touched notes re-embed on commit.

**Relate two terms with a `[[wikilink]]` in the body, not a shared tag** — e.g.
`[[data-definition-language]]` ↔ `[[data-manipulation-language]]`. The wikilink is the graph edge
between them; a tag is only the topical bucket they might share.


## What ships in a fresh brain

Just this README and the term template — **no pre-filled terms**. The vocabulary is yours to
curate. In Obsidian's graph view, color the whole layer at once with a `tag:#glossary` color
group — every term carries the tag, so it selects the terms without also coloring this README,
and it does not depend on where you opened the vault (a `path:` query changes with the root).
