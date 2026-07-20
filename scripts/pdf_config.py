#!/usr/bin/env python3
"""The ``[pdf]`` config block for PDF ingestion (task #7 M5).

Reads the optional ``[pdf]`` table in ``config/features.toml`` (same file and tomllib
pattern as scripts/features.py), falling back to built-in defaults so ingestion works
before the block is written. Keys (docs/pdf-ingestion.md §3):

- ``inbox_dirs``      — source folders to import from, priority order (first shown first)
- ``list_sort``       — how a folder's PDFs are ordered: ``"newest"`` | ``"alphabetical"``
- ``list_page_size``  — how many entries to show before paginating
- ``chunk_tokens``    — target chunk size, in whitespace-word tokens
- ``chunk_overlap``   — fractional overlap between adjacent chunks
- ``result_mode``     — passage shaping: ``"best_per_source"`` | ``"all_chunks"``
- ``move_from_inbox`` — move (vs copy) the file out of its source folder on ingest

NOT emitted into a brain yet (task #7 M6); the ``[pdf]`` block is added to the emitted
config then. Until then these defaults apply.
"""
from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "features.toml"

DEFAULTS = {
    "inbox_dirs": ["vault/inbox", "~/Downloads"],
    "list_sort": "newest",
    "list_page_size": 20,
    "chunk_tokens": 512,
    "chunk_overlap": 0.15,
    "result_mode": "best_per_source",
    "move_from_inbox": True,
}


@lru_cache(maxsize=1)
def _pdf_table() -> dict:
    """The ``[pdf]`` table from features.toml (empty if the file or table is missing)."""
    try:
        with _CONFIG_PATH.open("rb") as fh:
            return tomllib.load(fh).get("pdf", {}) or {}
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _get(key):
    """Config value for ``key`` if the right type, else the built-in default."""
    val = _pdf_table().get(key)
    default = DEFAULTS[key]
    # bool is an int subclass — guard so `move_from_inbox` isn't read as an int and vice versa.
    if isinstance(val, bool) != isinstance(default, bool):
        return default
    return val if isinstance(val, type(default)) else default


def inbox_dirs() -> list[str]:
    val = _pdf_table().get("inbox_dirs")
    if isinstance(val, list) and all(isinstance(x, str) for x in val) and val:
        return val
    return DEFAULTS["inbox_dirs"]


def list_sort() -> str:
    val = _get("list_sort")
    return val if val in ("newest", "alphabetical") else DEFAULTS["list_sort"]


def list_page_size() -> int:
    val = _get("list_page_size")
    return val if val > 0 else DEFAULTS["list_page_size"]


def chunk_tokens() -> int:
    return _get("chunk_tokens")


def chunk_overlap() -> float:
    return _get("chunk_overlap")


def result_mode() -> str:
    val = _get("result_mode")
    return val if val in ("best_per_source", "all_chunks") else DEFAULTS["result_mode"]


def move_from_inbox() -> bool:
    return _get("move_from_inbox")
