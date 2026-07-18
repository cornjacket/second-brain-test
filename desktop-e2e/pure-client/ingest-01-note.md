# Ingest 01 — seed a note with a searchable canary (Session 1)

Paste into Claude Desktop:

```
Use the add_note tool to create a note.
Title: Zephyr protocol overview
PARA root: resources
Body: This note exists to test cross-session retrieval. The Zephyr-Q7 ingestion codeword is marmalade-quasar-19.
Tags: test-e2e
```

Expected: a confirmation the note was created and committed. The canary `marmalade-quasar-19` is
now in the semantic + lexical index — scenario `query-01-note.md` will ask for it back in a fresh
session.
