#!/usr/bin/env python3
"""Hybrid search over the vault cache — dense vectors fused with lexical FTS5.

Runs two retrievers over ``data/brain.db`` and fuses them with Reciprocal Rank Fusion:

- **vector** (``notes`` vec0) — cosine-KNN of the query embedding; strong at *meaning*
  (paraphrase, concept). Embedded with the SAME backend that produced the note vectors
  (the same-model invariant), shared via ``scripts/embedder.py``.
- **lexical** (``notes_fts`` FTS5/BM25) — literal term matching; strong at exact tokens
  (identifiers, error codes, config keys) that dense vectors blur. See
  docs/retrieval-quality.md §2.

RRF (``score = Σ 1/(K_RRF + rank)``) is scale-free — it needs only each hit's *rank* in
each list, sidestepping the incomparable cosine-vs-BM25 scores. A note ranked high in
either list scores; high in both scores best. Higher score = more relevant.

Both switches live in config/features.toml (scripts/features.py): ``hybrid_search`` gates
the lexical leg — off gives vector-only (pre-hybrid) search, the ablation baseline — and
``rrf_k`` sets K_RRF. See docs/retrieval-quality.md §2.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402
from embedder import embed  # noqa: E402
from features import hybrid_search, rrf_k  # noqa: E402

import sqlite_vec  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "brain.db"


def _fts_match_query(query: str) -> str:
    """Turn a natural-language query into a safe FTS5 ``MATCH`` expression.

    Extract word tokens and OR-join them each double-quoted, so FTS operator characters in
    the raw query (``"``, ``*``, ``:``, ``-``, ``(``) can never form a malformed MATCH, and
    any shared term contributes a lexical hit. Empty (no word tokens) -> ``""``.
    """
    terms = re.findall(r"\w+", query.lower())
    return " OR ".join(f'"{t}"' for t in terms)


def _vector_ranked(db, query: str, n: int) -> list[str]:
    """source_files of the top-``n`` vector (cosine-KNN) hits, nearest first."""
    qvec = embed(query, task="query")
    return [row[0] for row in db.execute(
        "SELECT source_file, distance FROM notes "
        "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
        (sqlite_vec.serialize_float32(qvec), n),
    )]


def _lexical_ranked(db, query: str, n: int) -> list[str]:
    """source_files of the top-``n`` FTS5/BM25 hits, best first.

    Degrades to ``[]`` if the query has no terms, the ``notes_fts`` table is absent (a
    stale pre-hybrid cache), or FTS raises — so search falls back to vector-only, never
    crashes.
    """
    match = _fts_match_query(query)
    if not match:
        return []
    try:
        return [row[0] for row in db.execute(
            "SELECT source_file FROM notes_fts WHERE notes_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (match, n),
        )]
    except Exception:
        return []


def search(query: str, k: int = 5) -> list[tuple[str, float]]:
    """Hybrid (vector + lexical) search of ``query`` against the vault cache.

    Returns ``(source_file, score)`` rows, most relevant first (RRF score, higher = better).
    This is the one shared search implementation — the CLI ``main()``, the skill, and the
    MCP server all call it, so a long-lived server never shells out to itself.
    """
    if not DB_PATH.exists():
        raise SystemExit("cache missing; run scripts/hydrate_cache.py first")

    db = connect(DB_PATH)
    try:
        pool = max(k, 20)  # fuse over a candidate pool wider than k, then trim
        k_rrf = rrf_k()
        # Always the vector leg; add the lexical leg only when hybrid is enabled.
        # Vector-only still flows through RRF — one leg, so the fused order is the
        # vector order and every hit keeps a comparable score.
        legs = [_vector_ranked(db, query, pool)]
        if hybrid_search():
            legs.append(_lexical_ranked(db, query, pool))
        scores: dict[str, float] = {}
        for ranked in legs:
            for rank, source_file in enumerate(ranked, 1):
                scores[source_file] = scores.get(source_file, 0.0) + 1.0 / (k_rrf + rank)
        fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return fused[:k]
    finally:
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid (vector + lexical) search over the vault.")
    ap.add_argument("query", help="natural-language search query")
    ap.add_argument("-k", "--top-k", type=int, default=5)
    args = ap.parse_args()

    # "<score>  <path>" — higher score = more relevant. The two-space shape is a contract
    # the second-brain skill's query.py parses, so keep it.
    for source_file, score in search(args.query, args.top_k):
        print(f"{score:.4f}  {source_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
