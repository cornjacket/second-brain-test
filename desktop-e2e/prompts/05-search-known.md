# Scenario 05 — search returns the known seed notes

Paste into Claude Desktop:

```
Search the second brain for: how do vector databases work?
```

Expected in Desktop's reply:
- the top hits include the seed notes on **sqlite-vec** and/or **embeddings** — this brain's
  vector-database material.

This scenario is **human-observed**: search *ranking* is non-deterministic (and with a real
`ollama` backend the exact order/scores vary run to run), so confirm the *right notes surface*,
not any exact wording or score. If the connector returns nothing at all, suspect the §11
`outputSchema` drop or that the brain was never embedded (hooks not installed — see the README
setup).

Verify (prints the manual checklist only):
```
python3 desktop-e2e/verify/verify_05_search.py
```
