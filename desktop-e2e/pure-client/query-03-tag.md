# Query 03 — retrieve the canary tag in a FRESH session (Session 2)

**Only after** deleting the ingest chat and opening a new one. Paste into Claude Desktop:

```
Use the list_tags tool with match="zephyr" to list the matching tags in my second brain.
```

**PASS:** the tag **`zephyr-canary-tag`** appears in the list (from the note seeded in
`ingest-03-tag.md`).

**FAIL:** the tag is absent. The tag vocabulary is derived from committed notes, so its presence in
a fresh session proves the seeded note persisted — not that the model recalls tagging it.

> Why `match=`: `list_tags` returns the most-used tags first and **caps** the list (default 50). The
> canary tag has a count of 1, so on a brain with a large vocabulary it would fall off the tail of an
> unfiltered list. The `match="zephyr"` substring filter is applied before the cap, so this test
> stays robust no matter how many tags the brain already holds.
