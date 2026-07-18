# Pure-client cross-session retrieval test — Desktop only, no verifier scripts

Proves this brain actually **retrieves and persists** through the real Claude Desktop client —
not that it merely *wrote* a note (the sibling `../verify/` suite covers writes), and not that the
model is just **remembering the conversation**. You seed distinctive *canary* values in one chat,
**throw that chat away**, then ask for them back in a **fresh** chat. If a canary comes back, it
came from the brain — there is no conversation left to remember it. The **only oracle is you
reading Desktop's reply**; there is no script to run.

## Why the canaries are nonsense words

Each seed carries an invented token (`marmalade-quasar-19`, `cobalt-pelican-7`, …). A hit on a
token the model has never seen can only mean the brain returned it — it cannot be guessed or
recited from training data. That is what makes a black-box eyeball into a real result. **You hold
the ground truth**, so a miss is an unambiguous FAIL, not "maybe it's just unfindable."

## Aim each query at the right retrieval layer

This brain has **distinct retrieval substrates with distinct blind spots**, so each scenario
queries the layer its seed actually lives in — querying the wrong one falsely reads as "not found":

| Scenario | Seeded via | Retrieved via | Layer |
|---|---|---|---|
| 01 note | `add_note` (canary in the body) | `search_second_brain` | semantic + lexical index |
| 02 glossary | `add_glossary_term` | `lookup_glossary_term` | glossary — **embedding-excluded**, so `search` will NOT find it |
| 03 tag | `add_note` (canary tag) | `list_tags` | tag vocabulary |
| 04 negative control | *(never seeded)* | `search_second_brain` | must return nothing — no fabrication |

Scenario 02 is the subtle one: a glossary term is deliberately kept out of the semantic index, so
you must retrieve it with `lookup_glossary_term`, not `search_second_brain`.

## Run it

**Do it on a disposable branch** — the ingest steps write real notes, and teardown wipes them so a
repeat run starts clean (that is also why fixed canaries are safe to reuse):

```
desktop-e2e/setup.sh              # throwaway branch; asserts a clean, doctor-green baseline
```

1. **Session 1 — ingest.** Open a **new** Desktop chat. Paste each `ingest-NN-*.md` prompt, in
   order. Confirm each write is acknowledged ("created …", "defined …").
2. **Delete that chat.** This is the load-bearing step — it removes the only place the model could
   still be holding the canaries. (Starting a new chat is enough; deleting is strongest.)
3. **Session 2 — retrieve.** Open a **fresh** chat. Paste each `query-NN-*.md` prompt. Check the
   reply against the expected canary listed in the file.

```
desktop-e2e/teardown.sh           # delete the branch, rebuild the index, restore byte-identical
```

## Pass / fail

| # | Expected in the fresh-session reply |
|---|---|
| 01 | the codeword **`marmalade-quasar-19`** is returned |
| 02 | the constant **`cobalt-pelican-7`** is returned (via glossary lookup) |
| 03 | the tag **`zephyr-canary-tag`** appears in the tag list |
| 04 | **nothing** — the brain has no `saffron-narwhal-88`, and the model says so rather than inventing one |

All four holding means retrieval + persistence work end-to-end through Desktop, uncontaminated by
chat memory. This is human-driven release/installation acceptance, **not** a CI gate.
