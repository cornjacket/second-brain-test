# Query 02 — retrieve the glossary canary in a FRESH session (Session 2)

**Only after** deleting the ingest chat and opening a new one. Paste into Claude Desktop:

```
Use the lookup_glossary_term tool to look up the term flumbnaxis.
```

**PASS:** the reply returns the definition containing **`cobalt-pelican-7`** (from
`ingest-02-glossary.md`).

**FAIL:** the term is not found. Note the substrate: the glossary is **embedding-excluded**, so
`search_second_brain` would legitimately return nothing here — that is not a bug, it is the wrong
tool. This scenario deliberately uses `lookup_glossary_term`. If you want to see the blind spot for
yourself, try `search_second_brain` for `cobalt-pelican-7`: a miss there is expected, and is the
reason the glossary has its own lookup path.
