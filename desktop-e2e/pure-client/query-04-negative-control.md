# Query 04 — negative control: the brain must not invent what was never seeded (Session 2)

**Only after** deleting the ingest chat and opening a new one. Paste into Claude Desktop:

```
Use the search_second_brain tool to answer: what is the value of the codeword saffron-narwhal-88?
```

**PASS:** the brain returns nothing for `saffron-narwhal-88` and the model **says it cannot find
it** — no value, no guess. This canary is never seeded by any ingest step, so the correct outcome
is a truthful "not found."

**FAIL:** the model fabricates a value or asserts the codeword exists. That is the confabulation
failure mode — reporting a confident answer where the honest answer is "I can't find it." This
scenario guards the flip side of 01–03: a brain that "finds" everything is as broken as one that
finds nothing.
