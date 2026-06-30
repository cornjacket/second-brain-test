---
tags: [meta, project]
---

# Second Brain

Building a dual-interface knowledge graph: humans write Markdown in Obsidian; an
AI queries a local SQLite cache built from the same notes. Notes are organized
with PARA and indexed by [[sqlite-vec]] using [[embeddings]] from a local model.

The goal is a single plain-text source of truth that stays human-friendly while
remaining cheap and deterministic for an AI to read.
