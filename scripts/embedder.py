"""Embedding backends for the Second Brain pipeline.

Two backends, selected by the ``SECOND_BRAIN_EMBEDDER`` env var:

- ``test`` (default): a deterministic, dependency-free pseudo-embedder. The same
  text maps to an identical 768-dim unit vector on every machine, so the golden
  reference's sidecars are byte-stable and diffable. It is **not** semantic — it
  proves the plumbing, not retrieval quality.
- ``ollama``: real ``nomic-embed-text`` embeddings via a local Ollama server.
  This is the production path and the only one that yields meaningful search.

Both return an L2-normalized list of ``EMBED_DIM`` floats. The SAME backend must
embed both the committed note vectors and the search query — mismatched models
produce incomparable vectors (the same-model invariant).
"""
from __future__ import annotations

import hashlib
import math
import os

EMBED_DIM = 768
ROUND_NDIGITS = 6  # fixed precision -> byte-stable JSON sidecars across machines


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def embed_test(text: str) -> list[float]:
    """Deterministic, hash-seeded pseudo-embedding. Stable, not semantic."""
    data = text.encode("utf-8")
    raw: list[float] = []
    counter = 0
    while len(raw) < EMBED_DIM:
        digest = hashlib.sha256(data + counter.to_bytes(4, "big")).digest()
        for i in range(0, len(digest), 4):
            u = int.from_bytes(digest[i:i + 4], "big")
            raw.append((u / 2**32) * 2.0 - 1.0)  # map uint32 -> [-1, 1)
            if len(raw) >= EMBED_DIM:
                break
        counter += 1
    return _l2_normalize(raw)


def embed_ollama(text: str) -> list[float]:
    """Real embeddings via a local Ollama server (``nomic-embed-text``)."""
    import json
    import urllib.request

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("SECOND_BRAIN_EMBED_MODEL", "nomic-embed-text")
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
    vec = body["embedding"]
    if len(vec) != EMBED_DIM:
        raise ValueError(
            f"Ollama returned {len(vec)} dims; expected {EMBED_DIM}. A model "
            "mismatch between note and query embeddings corrupts search."
        )
    return _l2_normalize(vec)


_BACKENDS = {"test": embed_test, "ollama": embed_ollama}


def backend_name() -> str:
    """The active backend selector (``test`` by default)."""
    return os.environ.get("SECOND_BRAIN_EMBEDDER", "test")


def backend_id() -> str:
    """Stable identifier for the active embedder, stamped into sidecars as ``type``.

    ``test`` for the deterministic backend; ``ollama:<model>`` for the semantic
    one — so a note vector always records which embedder produced it and mixing
    backends becomes detectable.
    """
    name = backend_name()
    if name == "ollama":
        model = os.environ.get("SECOND_BRAIN_EMBED_MODEL", "nomic-embed-text")
        return f"ollama:{model}"
    return name


def is_deterministic() -> bool:
    """Only the ``test`` backend is byte-reproducible across machines/versions."""
    return backend_name() == "test"


def embed(text: str) -> list[float]:
    """Embed ``text`` with the configured backend, rounded for stable output."""
    backend = os.environ.get("SECOND_BRAIN_EMBEDDER", "test")
    try:
        fn = _BACKENDS[backend]
    except KeyError:
        raise SystemExit(
            f"Unknown SECOND_BRAIN_EMBEDDER={backend!r}; "
            f"expected one of {sorted(_BACKENDS)}."
        )
    return [round(x, ROUND_NDIGITS) for x in fn(text)]
