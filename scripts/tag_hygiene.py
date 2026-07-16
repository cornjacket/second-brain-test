#!/usr/bin/env python3
"""Tag-vocabulary hygiene for a living vault — deterministic detection + backfill.

Tag drift is a runtime property of a growing vault, not a one-off cleanup. Near-misses
(`agents` vs `ai-agents`) silently split a group; a broad tag riding nearly every note
(an `ai` tag in an all-AI vault) partitions nothing; a title leaks into the tags
(`create_second_brain`). Left alone, the vocabulary decays as a retrieval surface.

The load-bearing idea: **detection is deterministic; only policy needs a human.** Almost
everything here is string statistics over the tag vocabulary, not LLM work — routing it
through a model would make it non-reproducible. The one genuine judgment is thin and in
the middle (which near-miss form is canonical; whether two overlapping tags merge), so
the pipeline sandwiches it between two mechanical layers:

    detector (read-only)  ->  human picks a {old: new} mapping  ->  applier (backfill)

This module is both mechanical layers plus a shared near-miss helper the write path uses
so a warning at write time and a finding at lint time can never disagree.

Detection passes (`analyze`):
  - near-miss     : normalize (case, - _ space) then flag case/separator variants, typos
                    (edit distance 1), and affix-qualified forms (`agents` vs `ai-agents`).
  - discrimination: per-tag note frequency; flag the near-universal (no partition value)
                    and the singletons (a tag on one note — often a leaked title). This is
                    the IDF intuition from BM25 applied to tags.
  - overlap       : Jaccard co-occurrence; tags that travel together above a threshold are
                    merge *candidates*, not merge *decisions*.
  - format-lint   : tags that look like leaked titles (an underscore where the vocabulary
                    is otherwise kebab-case).

Backfill (`apply_mapping`): rewrite frontmatter `tags:` only, from an explicit mapping —
no inference. Preserves everything else, dedupes on a merge, and is idempotent.

Scope is frontmatter `tags:` in the PARA roots only — the exact surface `list_tags`
enumerates. Never bodies, wikilinks, titles, the glossary, or the note template.

    python3 scripts/tag_hygiene.py            # human-readable report for this vault
    python3 scripts/tag_hygiene.py --json     # machine-readable report

Pure stdlib (difflib is unused; a tiny bounded edit distance keeps the near-miss rule
explicit); reuses note_view.frontmatter_tags so there is one tag parser in the brain.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field, asdict
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import note_view  # noqa: E402  (path set above; one tag parser for the whole brain)

VAULT = REPO_ROOT / "vault"

# The PARA roots — identical to mcp_server.list_tags. The glossary (a controlled
# vocabulary of its own) and templates/ (placeholder tags like `tag-one`) are
# deliberately outside this walk, so neither pollutes the tag statistics.
PARA_ROOTS = ("projects", "areas", "resources", "archive")

# Defaults — all overridable per run. See the module docstring for the reasoning.
NEAR_UNIVERSAL = 0.8       # a tag on >= this fraction of notes partitions almost nothing
OVERLAP_JACCARD = 0.6      # two tags whose note sets overlap this much are merge candidates
OVERLAP_MIN_SUPPORT = 2    # ...but only once their combined note set is this large — a
                           # 100% Jaccard over a single shared note is coincidence, not signal


# --------------------------------------------------------------------------- #
# Vocabulary                                                                   #
# --------------------------------------------------------------------------- #

def scan_notes(vault: Path = VAULT) -> dict[str, list[str]]:
    """Map each tag to the notes that carry it (vault-relative paths, sorted).

    The value is the note *list*, not just a count, because every downstream pass needs
    set membership: discrimination divides by the note total, overlap intersects two tag
    sets, and the applier walks the carrying notes. Reads tags through
    note_view.frontmatter_tags — the brain's single tolerant tags parser.
    """
    carriers: dict[str, list[str]] = {}
    for root in PARA_ROOTS:
        base = vault / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            rel = str(path.relative_to(vault))
            for tag in note_view.frontmatter_tags(path.read_text(encoding="utf-8")):
                carriers.setdefault(tag, [])
                if rel not in carriers[tag]:  # a note listing a tag twice counts once
                    carriers[tag].append(rel)
    return carriers


def note_total(vault: Path = VAULT) -> int:
    """Count the notes in scope — the denominator for the discrimination pass."""
    total = 0
    for root in PARA_ROOTS:
        base = vault / root
        if base.is_dir():
            total += sum(1 for _ in base.rglob("*.md"))
    return total


# --------------------------------------------------------------------------- #
# Near-miss (the deterministic string rule, shared with the write path)        #
# --------------------------------------------------------------------------- #

def normalize(tag: str) -> str:
    """Collapse the cosmetic differences a human never means to distinguish.

    Case and the three separators (`-`, `_`, space) all fold to a single kebab form, so
    `AI_Agents`, `ai agents`, and `ai-agents` are one tag for comparison purposes. This is
    the equivalence the near-miss pass compares *across*, never the value it stores.
    """
    return re.sub(r"[-_\s]+", "-", tag.strip().lower()).strip("-")


def _edit_distance_le1(a: str, b: str) -> bool:
    """True iff `a` and `b` are within Levenshtein distance 1. Bounded, no matrix.

    One length-0 or length-1 gap is all a near-miss typo needs, so we special-case the
    two shapes (equal length -> at most one substitution; off-by-one length -> the shorter
    embeds in the longer with one insertion) rather than build a full DP table.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:  # candidate single substitution
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long = (a, b) if la < lb else (b, a)  # candidate single insertion
    i = j = 0
    edited = False
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
        elif edited:
            return False
        else:
            edited = True
            j += 1  # skip the inserted char in the longer string
    return True


def _affix_variant(a: str, b: str) -> bool:
    """True iff one normalized tag is the other plus one leading/trailing kebab token.

    This is the `agents` -> `ai-agents` case: someone qualified an existing tag and split
    the group. Edit distance misses it (three chars differ), so it needs its own rule:
    split on `-`, and flag when the shorter token sequence is a contiguous prefix or
    suffix of the longer and exactly one token shorter.
    """
    ta, tb = a.split("-"), b.split("-")
    if abs(len(ta) - len(tb)) != 1:
        return False
    short, long = (ta, tb) if len(ta) < len(tb) else (tb, ta)
    return long[: len(short)] == short or long[-len(short):] == short


def is_near_miss(a: str, b: str) -> bool:
    """The full near-miss rule between two raw tags: variant, typo, or affix-qualified."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb or na == nb:
        return na == nb  # normalized collision (case/separator variant) is a near-miss
    return _edit_distance_le1(na, nb) or _affix_variant(na, nb)


def near_miss_of(candidate: str, vocabulary) -> str | None:
    """The existing tag a proposed one is a near-miss of, or None — the write-time hook.

    `add_note` calls this to warn (never block) when a new tag would split an existing
    group. Because it is the same rule the lint pass uses, the warning and the finding
    cannot drift. An exact match is *not* a near-miss — reusing a tag verbatim is the
    goal, not a mistake.
    """
    for existing in vocabulary:
        if existing != candidate and is_near_miss(candidate, existing):
            return existing
    return None


# --------------------------------------------------------------------------- #
# Report                                                                       #
# --------------------------------------------------------------------------- #

@dataclass
class Report:
    """The detector's structured output — JSON via asdict(), human via render()."""
    note_total: int = 0
    tag_total: int = 0
    near_miss: list[list[str]] = field(default_factory=list)        # [[tag_a, tag_b], ...]
    near_universal: list[dict] = field(default_factory=list)        # {tag, count, fraction}
    singletons: list[dict] = field(default_factory=list)           # {tag, note}
    format_lint: list[dict] = field(default_factory=list)          # {tag, reason}
    overlap: list[dict] = field(default_factory=list)              # {tags, jaccard}

    @property
    def flagged(self) -> bool:
        return bool(self.near_miss or self.near_universal or self.singletons
                    or self.format_lint or self.overlap)

    def render(self) -> str:
        """A scannable summary. Empty findings print as a single clean line."""
        out = [f"tag hygiene — {self.tag_total} tags across {self.note_total} notes"]
        if not self.flagged:
            out.append("  clean — no near-misses, no low-discrimination tags, no leaked titles")
            return "\n".join(out)

        def section(title, rows):
            if rows:
                out.append(f"\n{title}")
                out.extend(f"  {r}" for r in rows)

        section("near-miss (candidate splits — pick one canonical form):",
                [f"{a}  ~  {b}" for a, b in self.near_miss])
        section("near-universal (rides most notes — partitions almost nothing):",
                [f"{r['tag']}  ({r['count']}/{self.note_total}, "
                 f"{r['fraction']:.0%})" for r in self.near_universal])
        section("singletons (one note — legitimate, or a leaked title?):",
                [f"{r['tag']}  ({r['note']})" for r in self.singletons])
        section("format (looks like a leaked title):",
                [f"{r['tag']}  — {r['reason']}" for r in self.format_lint])
        section("overlap (travel together — merge candidates, not decisions):",
                [f"{r['tags'][0]} + {r['tags'][1]}  (Jaccard {r['jaccard']:.0%})"
                 for r in self.overlap])
        return "\n".join(out)


def analyze(vault: Path = VAULT, *, near_universal: float = NEAR_UNIVERSAL,
            overlap: float = OVERLAP_JACCARD,
            overlap_min_support: int = OVERLAP_MIN_SUPPORT) -> Report:
    """Run every detection pass over a vault and return a structured Report. No mutation."""
    carriers = scan_notes(vault)
    total = note_total(vault)
    tags = sorted(carriers)
    report = Report(note_total=total, tag_total=len(tags))

    # Discrimination first — near-universal and singleton, both derived from note frequency.
    # It runs before near-miss because a near-universal tag is excluded from that pass below.
    universal: set[str] = set()
    for tag in tags:
        count = len(carriers[tag])
        if total and count / total >= near_universal:
            report.near_universal.append(
                {"tag": tag, "count": count, "fraction": count / total})
            universal.add(tag)
        if count == 1:
            report.singletons.append({"tag": tag, "note": carriers[tag][0]})

    # Near-miss — every unordered pair, deduped by the sorted-pair key so a symmetric rule
    # reports `a ~ b` once. A near-universal tag is skipped: it is a broad umbrella (`ai`),
    # so the affix rule would wrongly read every compound under it (`ai-agents`) as a split
    # of it. That tag already has its own, louder near-universal finding.
    candidates = [t for t in tags if t not in universal]
    for a, b in combinations(candidates, 2):
        if is_near_miss(a, b):
            report.near_miss.append(sorted((a, b)))

    # Format-lint — an underscore in an otherwise kebab vocabulary reads as a leaked
    # identifier (a filename slug, a code symbol) rather than a chosen tag.
    for tag in tags:
        if "_" in tag:
            report.format_lint.append(
                {"tag": tag, "reason": "underscore (house style is kebab-case)"})

    # Overlap — Jaccard over note sets. Union in the denominator is deliberate: a
    # near-universal tag then has *low* overlap with a small tag (it is not a merge
    # candidate for everything), which a min-denominator containment score would get
    # wrong. The near-universal pass already owns the "rides everything" finding.
    for a, b in combinations(tags, 2):
        sa, sb = set(carriers[a]), set(carriers[b])
        union = sa | sb
        if len(union) < overlap_min_support:
            continue
        j = len(sa & sb) / len(union)
        if j >= overlap:
            report.overlap.append({"tags": sorted((a, b)), "jaccard": j})

    return report


# --------------------------------------------------------------------------- #
# Backfill (mutating — the second mechanical layer)                            #
# --------------------------------------------------------------------------- #

@dataclass
class Change:
    note: str
    old: list[str]
    new: list[str]


def _apply_map(tags: list[str], mapping: dict[str, str]) -> list[str]:
    """Rewrite a tag list through `mapping`, preserving order and deduping a merge.

    A merge (`ai-agents` -> `agents` on a note already carrying `agents`) would create a
    duplicate; first-wins dedup collapses it. The result is what makes re-running a no-op:
    a tag already at its mapped value maps to itself and nothing changes.
    """
    out: list[str] = []
    for tag in tags:
        mapped = mapping.get(tag, tag)
        if mapped not in out:
            out.append(mapped)
    return out


def _render_tags_line(indent: str, tags: list[str]) -> str:
    return f"{indent}tags: [{', '.join(tags)}]"


def rewrite_tags(text: str, mapping: dict[str, str]) -> str | None:
    """Return `text` with its frontmatter `tags:` rewritten through `mapping`, or None.

    None means no change — either there is no tags key, or the mapping leaves every tag
    where it is (the idempotency guarantee). Only the tags region is touched; the fence,
    other keys, and the body are preserved byte-for-byte. Supports the three shapes the
    vault uses (inline list, block list, scalar) and normalizes a rewritten multi-tag
    result to the inline form the write path emits.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None
    # Locate the closing fence.
    fence_end = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            fence_end = i
            break
    if fence_end is None:
        return None

    old = note_view.frontmatter_tags(text)
    new = _apply_map(old, mapping)
    if new == old:
        return None

    # Find the tags: key line inside the frontmatter and the shape of its value.
    for i in range(1, fence_end):
        stripped = lines[i].strip()
        if not stripped.startswith("tags:"):
            continue
        indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
        newline = "\n"
        if lines[i].endswith("\r\n"):
            newline = "\r\n"
        rest = stripped[len("tags:"):].strip()
        block_end = i + 1
        if not (rest.startswith("[") or rest):  # block list — consume the `- ` lines
            j = i + 1
            while j < fence_end and lines[j].strip().startswith("- "):
                j += 1
            block_end = j
        rendered = _render_tags_line(indent, new) + newline
        lines[i:block_end] = [rendered]
        return "".join(lines)
    return None


def apply_mapping(vault: Path, mapping: dict[str, str], *,
                  dry_run: bool = True) -> list[Change]:
    """Apply `{old: new}` to every carrying note's frontmatter tags. Dry-run by default.

    Returns the changes it made (or would make). In dry-run nothing is written. No
    inference — it applies exactly the mapping it is given, which is the human's policy
    decision from the report. Notes it does not touch are left exactly as they were.
    """
    changes: list[Change] = []
    for root in PARA_ROOTS:
        base = vault / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            rewritten = rewrite_tags(text, mapping)
            if rewritten is None:
                continue
            old = note_view.frontmatter_tags(text)
            new = note_view.frontmatter_tags(rewritten)
            changes.append(Change(note=str(path.relative_to(vault)), old=old, new=new))
            if not dry_run:
                path.write_text(rewritten, encoding="utf-8")
    return changes


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Report tag-vocabulary hygiene for this vault.")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--near-universal", type=float, default=NEAR_UNIVERSAL,
                        help=f"fraction-of-notes threshold (default {NEAR_UNIVERSAL})")
    parser.add_argument("--overlap", type=float, default=OVERLAP_JACCARD,
                        help=f"Jaccard co-occurrence threshold (default {OVERLAP_JACCARD})")
    parser.add_argument("--overlap-min-support", type=int, default=OVERLAP_MIN_SUPPORT,
                        help=f"min combined note count for an overlap flag (default {OVERLAP_MIN_SUPPORT})")
    args = parser.parse_args(argv)

    report = analyze(near_universal=args.near_universal, overlap=args.overlap,
                     overlap_min_support=args.overlap_min_support)
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(report.render())
    return 0  # read-only: never a failure exit (posture is informational)


if __name__ == "__main__":
    raise SystemExit(main())
