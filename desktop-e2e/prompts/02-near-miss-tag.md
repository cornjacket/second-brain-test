# Scenario 02 — write-time near-miss TAG HINT (task #32)

**Run scenario 01 first** — it puts `ai-agents` into the vocabulary, which this scenario's
near-miss compares against.

Paste into Claude Desktop:

```
Use the add_note tool to create a note.
Title: Reactive agents
PARA root: resources
Body: A note about reactive agents, written for the Desktop e2e test.
Tags: ai-agent, planning
```

Expected in Desktop's reply — **both**:
- the note was created and committed; **and**
- a line beginning `TAG HINT:` stating that `ai-agent` is close to the existing `ai-agents`.

**This is the point of the whole suite.** The `TAG HINT` proves the write-time near-miss warning
(task #32) reaches the model *inside Desktop* — something the Python-client harness (G6) cannot
demonstrate. If the note lands but no hint appears, the warning is not surviving the Desktop
round-trip even though the server emits it.

Verify:
```
python3 desktop-e2e/verify/verify_02_near_miss.py
```
