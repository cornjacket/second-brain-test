# Testing strategy

The pipeline is validated on **two orthogonal axes** — *"is the wiring intact?"*
and *"is the output meaningful?"* Neither test subsumes the other; each is only
allowed to assert what it can actually prove.

| | **Structural tier** (byte-diff) | **Semantic tier** (behavioural E2E) |
|---|---|---|
| Embedder | `test` (deterministic hash) | `ollama` (real `nomic-embed-text`) |
| Kind | snapshot / characterization | acceptance / behavioural |
| Proves the **wiring** is intact | ✅ precisely | ⚠️ shallowly, insensitively |
| Proves the output is **meaningful** | ❌ never | ✅ the only thing that can |
| Runs in CI / no model | ✅ | ❌ (needs Ollama) |
| Localizes failures | ✅ pinpoint (which note, which bytes) | ❌ "something's wrong" |
| Sensitive to subtle corruption | ✅ (byte-exact) | ❌ (search is robust, forgives it) |

## Structural tier — `scripts/self_test.py` (the CI gate)

Re-embeds every note in `tests/fixtures/vault/` with the deterministic `test`
backend and **byte-compares** the result to the committed expected sidecar.

- **Hermetic:** no model, network, or Ollama — runs anywhere, every commit, in ms.
- **Diagnostic:** a failure names the exact note and that its bytes drifted.
- **Sensitive:** catches subtle data bugs (byte order, precision, missing
  L2-normalize) that a semantic test is too robust to notice.
- **May assert:** exact bytes of the fixture sidecars; that regeneration is
  reproducible. **May NOT assert:** that embeddings mean anything — the `test`
  backend is deterministic *noise*, so this tier can be green on garbage.
- Ships with every generated brain as its built-in "is my pipeline wired
  correctly on this machine?" check.

Run it:

```bash
python3 scripts/self_test.py
```

Fixtures live in `tests/fixtures/vault/` and are **committed** (they are the
expected output). They are the *only* committed sidecars in the repo.

## Semantic tier — behavioural E2E (opt-in, local)

Embeds a small set of **related and unrelated** notes with the real `ollama`
backend, hydrates, and asserts *behaviour*: a known query ranks the related note
in top-k / above a cosine threshold, and unrelated notes fall below it.

- **Non-hermetic** (needs Ollama), **non-deterministic** across machines, **low
  diagnosticity**, and threshold-sensitive — so it is an *occasional, local* tier,
  **not** the CI gate.
- **May assert:** ranking / similarity behaviour (relative order, thresholds).
  **May NOT assert:** exact vector bytes — real embeddings drift across
  hardware/model versions; byte-asserting them is brittle by design.
- Status: planned. The structural tier is the current gate.

## Why not use the real embedder for the byte-diff?

Because "deterministic on the machine that made the golden" ≠ "reproducible on
every machine that verifies it." Real neural embeddings drift in low-order float
bits across CPU/GPU, BLAS, and model versions, so they cannot anchor a committed
byte-diff. The `test` backend (pure SHA-256 math) is byte-identical everywhere —
which is the entire reason it exists. See the embedding contract (§4) and `OQ-2`
in the `second-brain-devkit`.
