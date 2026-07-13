"""Query-time retrieval feature toggles for the Second Brain search path.

Read by scripts/search_vault.py so a brain's search behavior is set once, in
config/features.toml, with the usual precedence — mirrors scripts/embedder.py:

    env var  >  config/features.toml  >  built-in default

An env var overrides the file for a single command; a missing file or key falls
back to the safe default, so an old brain without config/features.toml still
searches (hybrid on, K=60).

- ``hybrid_search`` (bool, default ``True``): fuse lexical FTS5/BM25 with vector
  KNN via Reciprocal Rank Fusion. ``False`` gives vector-only (pre-hybrid) search
  — the ablation baseline (tools/ablation.py) and a fallback when FTS is absent.
  Env: ``SECOND_BRAIN_HYBRID_SEARCH`` (``1``/``0``/``true``/``false``/``on``/``off``).
- ``rrf_k`` (int, default ``60``): the RRF damping constant; larger flattens the
  rank weighting. Env: ``SECOND_BRAIN_RRF_K``.
- ``glossary_autolink`` (bool, default ``False``): when set, the pre-commit hook
  links known glossary terms in each staged note before embedding it. Off by
  default (a hook that edits your prose should be opt-in). Env:
  ``SECOND_BRAIN_GLOSSARY_AUTOLINK``.
"""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "features.toml"

_DEFAULT_HYBRID = True
_DEFAULT_RRF_K = 60
_DEFAULT_GLOSSARY_AUTOLINK = False

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


@lru_cache(maxsize=1)
def _config() -> dict:
    """This brain's features.toml as a dict (empty if missing/unreadable).

    Cached per process. A missing/unreadable/malformed file yields ``{}`` so every
    key falls back to its built-in default.
    """
    try:
        with _CONFIG_PATH.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _parse_bool(raw: str) -> bool | None:
    """Parse a truthy/falsy env string; ``None`` if it names neither."""
    val = raw.strip().lower()
    if val in _TRUE:
        return True
    if val in _FALSE:
        return False
    return None


def hybrid_search() -> bool:
    """Whether search fuses lexical FTS5 with vectors: env > config > default (True)."""
    env = os.environ.get("SECOND_BRAIN_HYBRID_SEARCH")
    if env is not None:
        parsed = _parse_bool(env)
        if parsed is not None:
            return parsed
    val = _config().get("hybrid_search")
    if isinstance(val, bool):
        return val
    return _DEFAULT_HYBRID


def rrf_k() -> int:
    """RRF damping constant: env > config > default (60)."""
    env = os.environ.get("SECOND_BRAIN_RRF_K")
    if env is not None:
        try:
            return int(env)
        except ValueError:
            pass
    val = _config().get("rrf_k")
    # bool is an int subclass — reject it so `rrf_k = true` isn't read as 1.
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    return _DEFAULT_RRF_K


def glossary_autolink() -> bool:
    """Whether the pre-commit hook links glossary terms in staged notes: env > config > default (False)."""
    env = os.environ.get("SECOND_BRAIN_GLOSSARY_AUTOLINK")
    if env is not None:
        parsed = _parse_bool(env)
        if parsed is not None:
            return parsed
    val = _config().get("glossary_autolink")
    if isinstance(val, bool):
        return val
    return _DEFAULT_GLOSSARY_AUTOLINK
