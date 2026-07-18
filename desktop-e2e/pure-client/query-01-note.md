# Query 01 — retrieve the note canary in a FRESH session (Session 2)

**Only after** you have deleted the ingest chat and opened a new one. Paste into Claude Desktop:

```
Use the search_second_brain tool to answer: what is the Zephyr-Q7 ingestion codeword?
```

**PASS:** the reply returns **`marmalade-quasar-19`** (surfaced from the note seeded in
`ingest-01-note.md`).

**FAIL:** the codeword does not come back, or the model says it cannot find it. In a fresh session
the model has no memory of the ingest chat, so a hit can only have come from the brain's index —
which is the whole point.
