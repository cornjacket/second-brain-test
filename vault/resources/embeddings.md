---
tags: [tech, ml]
---

# Embeddings

Dense vector representations of text where semantic similarity maps to geometric
closeness. We use `nomic-embed-text` (768 dimensions) served locally by Ollama,
and compare vectors with cosine distance.

The same model must embed both the stored notes and the search query — mixing
models yields incomparable vectors and meaningless results.
