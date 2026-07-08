#!/usr/bin/env python3
"""Vector-derived auto-linking (task #8) — compute each note's nearest neighbours.

Auto-linking materialises the brain's vector-space neighbourhoods as Obsidian graph
edges by writing a managed ``related_auto:`` frontmatter block into each note (full
design in docs/auto-linking.md). This runs **on-demand** (not per-commit), by design,
to keep churn on committed notes controlled and deterministic.

**This cut is READ-ONLY — a calibration/preview tool.** It computes the KNN
neighbourhood of every note from the vectors already in ``data/brain.db`` (no
re-embed), reusing the vec0 ``distance_metric=cosine`` KNN so the distances are
**identical to search**. It reports the neighbour distances so the linking cutoff
``t_max`` (and later the hysteresis band + mutual-KNN rule) can be calibrated on real
data *before* any note frontmatter is written. Writing the ``related_auto:`` block —
with the stability rules and manual-link preservation — is the follow-up increment.

    python3 scripts/autolink.py                 # per-note neighbours + distance summary
    python3 scripts/autolink.py --k 8            # consider more neighbours
    python3 scripts/autolink.py --threshold 0.35 # preview which links a t_max would make
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "brain.db"


def note_neighbors(db, k: int) -> dict[str, list[tuple[str, float]]]:
    """Map each note to its ``k`` nearest *other* notes as (source_file, distance).

    Reads each note's stored vector straight back out of the vec0 table and uses it
    as the KNN probe — so no re-embed, and the same cosine metric search uses.
    """
    rows = list(db.execute("SELECT source_file, embedding FROM notes"))
    result: dict[str, list[tuple[str, float]]] = {}
    for src, emb in rows:
        hits = db.execute(
            "SELECT source_file, distance FROM notes "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (emb, k + 1),  # +1: a note is always its own nearest neighbour (~0)
        )
        result[src] = [(s, float(d)) for s, d in hits if s != src][:k]
    return result


def wikilink_target(source_file: str) -> str:
    """The Obsidian wikilink name for a note — its filename stem (no path/extension)."""
    return Path(source_file).stem


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Compute vector-derived note neighbours (read-only calibration)."
    )
    ap.add_argument("--k", type=int, default=5,
                    help="neighbours per note to consider (default 5)")
    ap.add_argument("--threshold", type=float, default=None, metavar="T_MAX",
                    help="preview which neighbours a distance cutoff t_max would link")
    args = ap.parse_args(argv)

    if not DB_PATH.exists():
        raise SystemExit("cache missing; run scripts/hydrate_cache.py first")

    db = connect(DB_PATH)
    try:
        neighbors = note_neighbors(db, args.k)
    finally:
        db.close()
    if not neighbors:
        raise SystemExit("no notes in the cache — embed the vault first")

    print(f"# auto-link calibration (read-only) — {len(neighbors)} note(s), k={args.k}")
    if args.threshold is not None:
        print(f"# preview: would link neighbours with distance < t_max={args.threshold}")
    print()

    distances: list[float] = []
    for src in sorted(neighbors):
        print(f"{wikilink_target(src)}  ({src})")
        for tgt, dist in neighbors[src]:
            distances.append(dist)
            mark = ""
            if args.threshold is not None:
                mark = "  → LINK" if dist < args.threshold else "  → (skip)"
            print(f"    {dist:.4f}  [[{wikilink_target(tgt)}]]{mark}")
        print()

    ds = sorted(distances)
    print("distance summary (all note→neighbour distances, directed):")
    print(f"  count={len(ds)}  min={ds[0]:.4f}  "
          f"median={statistics.median(ds):.4f}  max={ds[-1]:.4f}")
    print("  sorted: " + ", ".join(f"{d:.3f}" for d in ds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
