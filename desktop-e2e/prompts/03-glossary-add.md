# Scenario 03 — add_glossary_term (controlled-vocabulary write + link cascade)

Paste into Claude Desktop:

```
Use the add_glossary_term tool.
Term: ablation study
Definition: removing a component to measure its contribution to the whole.
Aliases: ablation
```

Expected in Desktop's reply:
- a confirmation the term was defined and committed — e.g. "defined ablation-study in the glossary".
- possibly a note about how many existing notes it linked (the cascade); zero is fine.

Verify:
```
python3 desktop-e2e/verify/verify_03_glossary.py
```
