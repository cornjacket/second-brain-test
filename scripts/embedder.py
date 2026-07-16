"""Embedding backends for the Second Brain pipeline.

Two backends, selected by the ``SECOND_BRAIN_EMBEDDER`` env var:

- ``test`` (default): a deterministic, dependency-free pseudo-embedder. The same
  text maps to an identical 768-dim unit vector on every machine, so the golden
  reference's sidecars are byte-stable and diffable. It is **not** semantic — it
  proves the plumbing, not retrieval quality.
- ``ollama``: real ``nomic-embed-text`` embeddings via a local Ollama server.
  This is the production path and the only one that yields meaningful search.

Both return an L2-normalized list of ``EMBED_DIM`` floats. The SAME backend AND the
SAME task-prefix scheme must be used on both sides of any comparison — mismatched
models or prefixes produce incomparable vectors (the same-model invariant, extended
to prefixes; see docs/retrieval-quality.md §1).

``embed(text, task=...)`` carries the caller's role: ``"document"`` for text being
stored/indexed (a note) and ``"query"`` for a search query. Only the ``ollama``
backend uses it — nomic-embed-text is instruction-tuned and expects a task prefix;
the deterministic ``test`` backend ignores it. Note↔note similarity (auto-linking)
is the **symmetric** case: ``"document"`` on both sides.
"""
from __future__ import annotations

import hashlib
import math
import os
import tomllib
from functools import lru_cache
from pathlib import Path

EMBED_DIM = 768
ROUND_NDIGITS = 6  # fixed precision -> byte-stable JSON sidecars across machines

# nomic-embed-text task prefixes, keyed by the caller's role. Only the ``ollama``
# backend uses these; ``test`` ignores the task (see the module docstring).
_OLLAMA_TASK_PREFIX = {
    "document": "search_document: ",  # text being stored/indexed (a note)
    "query": "search_query: ",        # text being searched with (a query)
}

# This brain's default backend, set once in config/embedder.toml so the brain is
# usable with no environment variable. The env var still overrides per-command.
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "embedder.toml"


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def embed_test(text: str, task: str) -> list[float]:
    """Deterministic, hash-seeded pseudo-embedding. Stable, not semantic.

    ``task`` is accepted for a uniform backend signature but **ignored**: the test
    backend is not a real model, so it has no task prefixes. This keeps the
    committed fixtures byte-stable regardless of the caller's role.
    """
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


def embed_ollama(text: str, task: str) -> list[float]:
    """Real embeddings via a local Ollama server (``nomic-embed-text``).

    ``nomic-embed-text`` is instruction-tuned: it expects a task prefix so that a
    query and the document that answers it land in a shared space. ``task`` selects
    the prefix — ``document`` for notes (and both sides of a note↔note comparison),
    ``query`` for a search query. See docs/retrieval-quality.md §1.
    """
    import json
    import urllib.request

    try:
        prefix = _OLLAMA_TASK_PREFIX[task]
    except KeyError:
        raise ValueError(f"unknown embed task {task!r}; expected one of "
                         f"{sorted(_OLLAMA_TASK_PREFIX)}")
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("SECOND_BRAIN_EMBED_MODEL", "nomic-embed-text")
    payload = json.dumps({"model": model, "prompt": prefix + text}).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    # A timeout is load-bearing: without one, urlopen waits forever. A stalled Ollama (the usual
    # cause is a cold model load) would then hang the caller indefinitely — and the caller may be
    # the long-lived MCP server, so one bad embed freezes every tool. Bound it; a slow brain must
    # degrade to an error, never to silence. Generous default (cold loads are slow but finite),
    # env-overridable.
    timeout = float(os.environ.get("SECOND_BRAIN_EMBED_TIMEOUT", "120"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(
            f"Ollama did not respond within {timeout:.0f}s at {host} ({reason}). "
            "Is it running (`ollama serve`) and the model pulled? "
            "Raise SECOND_BRAIN_EMBED_TIMEOUT if a cold model load needs longer."
        ) from exc
    vec = body["embedding"]
    if len(vec) != EMBED_DIM:
        raise ValueError(
            f"Ollama returned {len(vec)} dims; expected {EMBED_DIM}. A model "
            "mismatch between note and query embeddings corrupts search."
        )
    return _l2_normalize(vec)


_BACKENDS = {"test": embed_test, "ollama": embed_ollama}


@lru_cache(maxsize=1)
def _configured_backend() -> str | None:
    """This brain's default backend from ``config/embedder.toml`` (``None`` if unset).

    Cached per process. A missing/unreadable/omitted key falls back to ``None`` so
    the caller uses the safe ``test`` default — an old brain without the config
    still works.
    """
    try:
        with _CONFIG_PATH.open("rb") as fh:
            backend = tomllib.load(fh).get("backend")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return backend or None


def backend_name() -> str:
    """The active backend: env override > this brain's config > ``test`` fallback.

    So a generated brain is usable out of the box (its config pins the real
    backend) while ``SECOND_BRAIN_EMBEDDER`` still overrides for one command — the
    devkit's self-test and CI force ``test`` this way.
    """
    env = os.environ.get("SECOND_BRAIN_EMBEDDER")
    if env:
        return env
    return _configured_backend() or "test"


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


def embed(text: str, task: str = "document") -> list[float]:
    """Embed ``text`` for ``task`` with the active backend, rounded for stable output.

    ``task`` is ``"document"`` (default — text being stored/indexed) or ``"query"``
    (a search query). It only affects the semantic ``ollama`` backend (mapped to a
    nomic task prefix); the deterministic ``test`` backend ignores it. Note↔note
    similarity (auto-linking) uses ``"document"`` on both sides.
    """
    backend = backend_name()
    try:
        fn = _BACKENDS[backend]
    except KeyError:
        raise SystemExit(
            f"Unknown embedder {backend!r} (from SECOND_BRAIN_EMBEDDER or "
            f"config/embedder.toml); expected one of {sorted(_BACKENDS)}."
        )
    return [round(x, ROUND_NDIGITS) for x in fn(text, task)]
