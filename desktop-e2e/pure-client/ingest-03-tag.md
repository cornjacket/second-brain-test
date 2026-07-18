# Ingest 03 — seed a note carrying a canary tag (Session 1)

Paste into Claude Desktop:

```
Use the add_note tool to create a note.
Title: Tangerine index entry
PARA root: resources
Body: A note whose only job is to put a distinctive canary tag into the brain's tag vocabulary.
Tags: zephyr-canary-tag, test-e2e
```

Expected: a confirmation the note was created and committed. The canary tag `zephyr-canary-tag` is
now in the tag vocabulary — `query-03-tag.md` will list the tags in a fresh session and expect it
to appear.
