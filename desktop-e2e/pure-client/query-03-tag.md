# Query 03 — retrieve the canary tag in a FRESH session (Session 2)

**Only after** deleting the ingest chat and opening a new one. Paste into Claude Desktop:

```
Use the list_tags tool to list the tags in my second brain.
```

**PASS:** the tag **`zephyr-canary-tag`** appears in the list (from the note seeded in
`ingest-03-tag.md`).

**FAIL:** the tag is absent. The tag vocabulary is derived from committed notes, so its presence in
a fresh session proves the seeded note persisted — not that the model recalls tagging it.
