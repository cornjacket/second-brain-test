---
tags: [tech, search]
---

# sqlite-vec

A SQLite extension that adds vector search via `vec0` virtual tables. Stores
embeddings alongside ordinary relational data and supports KNN queries with a
configurable distance metric (we use cosine).

Local-first and dependency-light: no external vector database, just a flat-file
`.db`. Loading it requires a Python/SQLite build with loadable-extension support,
or the `apsw` connector as a fallback.
