# Scenario 01 — add_note (write path + commit)

Paste into Claude Desktop (connected to this brain):

```
Use the add_note tool to create a note.
Title: Planning agents
PARA root: resources
Body: A note about planning agents, written for the Desktop e2e test.
Tags: ai-agents, planning
```

Expected in Desktop's reply:
- a confirmation the note was created and committed — e.g. "created resources/planning-agents.md".

This scenario also seeds `ai-agents` into the vocabulary, which scenario 02 relies on.

Verify:
```
python3 desktop-e2e/verify/verify_01_add_note.py
```
