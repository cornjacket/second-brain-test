# Ingest 02 — seed a glossary term with a canary definition (Session 1)

Paste into Claude Desktop:

```
Use the add_glossary_term tool.
Term: flumbnaxis
Definition: A test-only term for cross-session retrieval. The flumbnaxis constant equals cobalt-pelican-7.
Aliases: flumb
```

Expected: a confirmation the term was defined and committed. Note the glossary is **embedding-
excluded** — the canary `cobalt-pelican-7` will NOT be reachable by semantic search, only by
`lookup_glossary_term` (that is exactly what `query-02-glossary.md` checks).
