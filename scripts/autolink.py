#!/usr/bin/env python3
"""Vector-derived auto-linking (task #8) — write each note's neighbours as Obsidian links.

Auto-linking materialises the brain's vector-space neighbourhoods as Obsidian graph
edges by writing a managed ``related_auto:`` block into each note's **frontmatter**
(full design in docs/auto-linking.md). It runs **on-demand** (not per-commit), by
design, to keep churn on committed notes controlled and deterministic.

Three modes:

    python3 scripts/autolink.py --calibrate     # distance report — tune t_max (read-only)
    python3 scripts/autolink.py                 # DRY RUN — diff of the links it would write
    python3 scripts/autolink.py --apply         # write the related_auto: blocks

**How links are chosen** (stability rules, docs/auto-linking.md §2): a note links a
neighbour only if it is within the top-N nearest, closer than ``--t-max``, **and** the
link is *mutual* (each is in the other's top-N) — mutual-KNN kills hub notes. The block
is written **inside frontmatter**, delimited by YAML-comment markers so we splice only
our own region (via marked_block) and **never touch** a hand-set ``related:`` or an
inline body ``[[link]]`` (namespace partition, §3). Neighbour names are sorted so an
unchanged link set renders byte-identically → no spurious diffs.
"""
from __future__ import annotations

import argparse
import difflib
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from marked_block import remove_block, splice_block  # noqa: E402
# NB: `db` (which imports sqlite_vec) is imported lazily inside main(), so the pure
# text helpers here (apply_links etc.) can be imported without sqlite-vec — e.g. by the
# devkit's hermetic Obsidian-format acceptance check.

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "brain.db"

# YAML-comment markers — valid frontmatter comments, so related_auto: stays a real
# Obsidian property while we own exactly the region between them.
BEGIN = "# second-brain:related_auto:begin"
END = "# second-brain:related_auto:end"


# --------------------------------------------------------------------------- #
# vectors -> neighbours -> chosen links
# --------------------------------------------------------------------------- #

def note_neighbors(db, k: int) -> dict[str, list[tuple[str, float]]]:
    """Map each note to its ``k`` nearest *other* notes as (source_file, distance).

    Reads each note's stored vector straight back out of the vec0 table and uses it
    as the KNN probe — no re-embed, and the same cosine metric search uses.
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


def select_links(neighbors, t_max: float, mutual: bool) -> dict[str, list[str]]:
    """Chosen links per note: within t_max, and (if ``mutual``) reciprocal top-N.

    ``neighbors`` is already capped at top-N (the ``k`` passed to note_neighbors).
    """
    topset = {src: {t for t, _ in lst} for src, lst in neighbors.items()}
    chosen: dict[str, list[str]] = {}
    for src, lst in neighbors.items():
        picks = []
        for tgt, dist in lst:
            if dist >= t_max:
                continue
            if mutual and src not in topset.get(tgt, frozenset()):
                continue
            picks.append(tgt)
        chosen[src] = picks
    return chosen


def wikilink_target(source_file: str) -> str:
    """The Obsidian wikilink name for a note — its filename stem (no path/extension)."""
    return Path(source_file).stem


# --------------------------------------------------------------------------- #
# writing the managed frontmatter block
# --------------------------------------------------------------------------- #

def _split_frontmatter(text: str):
    """Return {open, inner, close, body} for a leading ``---`` … ``---`` block, or None.

    ``inner`` is the YAML between the fences; ``body`` is everything after. Line
    endings of the fences are preserved so an unchanged note round-trips exactly.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return {
                "open": lines[0],
                "inner": "".join(lines[1:i]),
                "close": lines[i],
                "body": "".join(lines[i + 1:]),
            }
    return None  # unterminated fence — treat as no frontmatter


def _render_block_body(names: list[str]) -> str:
    """The YAML that lives *between* the markers: the related_auto: list."""
    return "\n".join(["related_auto:"] + [f'  - "[[{n}]]"' for n in names])


def apply_links(text: str, names: list[str]) -> str:
    """Return ``text`` with its ``related_auto:`` managed block set to ``names``.

    Empty ``names`` removes the block. Only the marked region inside the frontmatter
    is ever touched — ``tags:``, a hand-set ``related:``, and the body are preserved.
    Idempotent: re-applying the same names returns byte-identical text.
    """
    names = sorted(set(names))
    fm = _split_frontmatter(text)
    synthesized = False
    if fm is None:
        if not names:
            return text
        fm = {"open": "---\n", "inner": "", "close": "---\n", "body": text}
        synthesized = True
    new_inner = (splice_block(fm["inner"], BEGIN, END, _render_block_body(names))
                 if names else remove_block(fm["inner"], BEGIN, END))
    if not synthesized and new_inner == fm["inner"]:
        return text
    return fm["open"] + new_inner + fm["close"] + fm["body"]


# --------------------------------------------------------------------------- #
# modes
# --------------------------------------------------------------------------- #

def calibrate(neighbors, k: int, t_max) -> int:
    print(f"# auto-link calibration (read-only) — {len(neighbors)} note(s), k={k}")
    if t_max is not None:
        print(f"# preview: would link neighbours with distance < t_max={t_max}")
    print()
    distances: list[float] = []
    for src in sorted(neighbors):
        print(f"{wikilink_target(src)}  ({src})")
        for tgt, dist in neighbors[src]:
            distances.append(dist)
            mark = ""
            if t_max is not None:
                mark = "  → LINK" if dist < t_max else "  → (skip)"
            print(f"    {dist:.4f}  [[{wikilink_target(tgt)}]]{mark}")
        print()
    ds = sorted(distances)
    print("distance summary (all note→neighbour distances, directed):")
    print(f"  count={len(ds)}  min={ds[0]:.4f}  "
          f"median={statistics.median(ds):.4f}  max={ds[-1]:.4f}")
    print("  sorted: " + ", ".join(f"{d:.3f}" for d in ds))
    return 0


def write_pass(chosen, apply: bool) -> int:
    changed = 0
    for src in sorted(chosen):
        path = REPO_ROOT / src
        old = path.read_text(encoding="utf-8")
        names = sorted(wikilink_target(t) for t in chosen[src])
        new = apply_links(old, names)
        if new == old:
            continue
        changed += 1
        if apply:
            path.write_text(new, encoding="utf-8")
            print(f"  updated {src} ({len(names)} link(s))")
        else:
            sys.stdout.writelines(difflib.unified_diff(
                old.splitlines(keepends=True), new.splitlines(keepends=True),
                fromfile=f"a/{src}", tofile=f"b/{src}"))
    if apply:
        print(f"\nauto-link: updated {changed} note(s). Review, then commit.")
    else:
        print(f"\nauto-link DRY RUN: {changed} note(s) would change. "
              f"Re-run with --apply to write.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Vector-derived Obsidian auto-linking.")
    ap.add_argument("--top-n", type=int, default=5,
                    help="max neighbours considered/linked per note (default 5)")
    ap.add_argument("--t-max", type=float, default=0.45,
                    help="link only neighbours closer than this cosine distance (default 0.45)")
    ap.add_argument("--no-mutual", action="store_true",
                    help="disable the mutual-KNN (reciprocal) requirement")
    ap.add_argument("--calibrate", action="store_true",
                    help="print the distance distribution instead of linking (read-only)")
    ap.add_argument("--apply", action="store_true",
                    help="write the related_auto: blocks (default: dry-run diff)")
    args = ap.parse_args(argv)

    if not DB_PATH.exists():
        raise SystemExit("cache missing; run scripts/hydrate_cache.py first")
    from db import connect  # lazy: sqlite-vec only needed to actually read the cache
    db = connect(DB_PATH)
    try:
        neighbors = note_neighbors(db, args.top_n)
    finally:
        db.close()
    if not neighbors:
        raise SystemExit("no notes in the cache — embed the vault first")

    if args.calibrate:
        return calibrate(neighbors, args.top_n, args.t_max)
    chosen = select_links(neighbors, args.t_max, mutual=not args.no_mutual)
    return write_pass(chosen, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
