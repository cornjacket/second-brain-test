#!/usr/bin/env python3
"""Link glossary terms where they appear in note bodies — the controlled vocabulary's
"link on use" pass (task #19).

For every term in `vault/glossary/`, find where it occurs (unlinked) in the body of a PARA
note and turn the first such occurrence into a `[[term]]` wikilink — so a reader clicks
straight from the word to its definition and Obsidian's graph grows the edge.

    python3 scripts/glossary_scan.py            # REPORT unlinked occurrences (dry run)
    python3 scripts/glossary_scan.py --apply    # insert the links

**Report by default, `--apply`-gated** — the same detect-and-instruct stance as
`install_skill.py` / `doctor.py` / `autolink.py`. It is an **on-demand** pass, not a
per-commit hook: `--apply` edits note bodies, which changes their substance and re-embeds
them on the next commit (the link is real content — the deliberate opposite of the
machine-derived `related_auto:` metadata).

**Idempotent** — one link per term per note (the first unlinked occurrence). Once a term is
linked in a note, later runs see the existing link and skip it, so re-running `--apply` is a
no-op.

**Deliberately dumb** (v1): exact whole-phrase, case-insensitive matching; it skips text
already inside a `[[wikilink]]`. Stemming, aliases, and skip-inside-code-fences are follow-ons
only if the dumb pass proves noisy. Pure stdlib.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = REPO_ROOT / "vault"
GLOSSARY_DIR = VAULT_DIR / "glossary"
PARA_ROOTS = ("projects", "areas", "resources", "archive")


def glossary_terms() -> list[tuple[str, str]]:
    """(slug, surface) per glossary term note — surface is the `# Title`, else the slug.

    Skips `README.md` and any `_`-prefixed infra file (e.g. a `_TEMPLATE.md`).
    """
    terms: list[tuple[str, str]] = []
    for p in sorted(GLOSSARY_DIR.glob("*.md")):
        if p.name == "README.md" or p.name.startswith("_"):
            continue
        slug = p.stem
        surface = slug.replace("-", " ")
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                surface = line[2:].strip()
                break
        terms.append((slug, surface))
    return terms


def para_notes() -> list[Path]:
    """Every Markdown note under the four PARA roots (the embedded substance notes)."""
    notes: list[Path] = []
    for root in PARA_ROOTS:
        base = VAULT_DIR / root
        if base.exists():
            notes += base.rglob("*.md")
    return sorted(notes)


def split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter_incl_fences, body). Empty frontmatter string if none — we edit the body only."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[:end + 5], text[end + 5:]
    return "", text


def _wikilink_spans(body: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\[\[[^\]]*\]\]", body)]


def already_linked(body: str, slug: str, surface: str) -> bool:
    """True if the body already has a `[[slug]]`/`[[slug|…]]`/`[[surface]]` link for this term."""
    targets = {slug.lower(), surface.lower()}
    for m in re.finditer(r"\[\[\s*([^\]|]+?)\s*(?:\|[^\]]*)?\]\]", body):
        if m.group(1).lower() in targets:
            return True
    return False


def first_unlinked(body: str, surface: str) -> re.Match | None:
    """First whole-phrase, case-insensitive occurrence of ``surface`` not inside a wikilink."""
    spans = _wikilink_spans(body)
    pattern = re.compile(r"(?<!\w)" + re.escape(surface) + r"(?!\w)", re.IGNORECASE)
    for m in pattern.finditer(body):
        if not any(start <= m.start() < end for start, end in spans):
            return m
    return None


def linked_form(slug: str, matched: str) -> str:
    """`[[slug]]` when the surface text is exactly the slug, else a piped `[[slug|matched]]`."""
    return f"[[{slug}]]" if matched == slug else f"[[{slug}|{matched}]]"


# --- the shared link engine (reused by the pre-commit hook and glossary_new.py) ----------

def link_body(body: str, terms: list[tuple[str, str]]) -> tuple[str, list[tuple[str, str]]]:
    """Link the first unlinked occurrence of each term in ``body``.

    Returns ``(new_body, linked)`` where ``linked`` is the ``(surface, slug)`` pairs inserted.
    Idempotent: a term already linked, or with no unlinked occurrence, is skipped.
    """
    linked: list[tuple[str, str]] = []
    for slug, surface in terms:
        if already_linked(body, slug, surface):
            continue
        m = first_unlinked(body, surface)
        if not m:
            continue
        matched = body[m.start():m.end()]
        body = body[:m.start()] + linked_form(slug, matched) + body[m.end():]
        linked.append((surface, slug))
    return body, linked


def link_note_file(path: Path, terms: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Apply ``link_body`` to a note file in place; return the ``(surface, slug)`` links made."""
    frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8"))
    new_body, linked = link_body(body, terms)
    if linked:
        path.write_text(frontmatter + new_body, encoding="utf-8")
    return linked


def unlinked_in_body(body: str, terms: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Report-only: the ``(surface, slug)`` terms that have an unlinked occurrence in ``body``."""
    return [(surface, slug) for slug, surface in terms
            if not already_linked(body, slug, surface) and first_unlinked(body, surface)]


def scan(apply: bool) -> int:
    terms = glossary_terms()
    if not terms:
        print("glossary_scan: no terms in vault/glossary/ yet — add some with "
              "scripts/glossary_new.py.")
        return 0

    total = 0
    touched_notes = 0
    for note in para_notes():
        rel = note.relative_to(REPO_ROOT)
        if apply:
            linked = link_note_file(note, terms)
            if linked:
                touched_notes += 1
            for surface, slug in linked:
                print(f"  link  {rel}: '{surface}' -> [[{slug}]]")
                total += 1
        else:
            _, body = split_frontmatter(note.read_text(encoding="utf-8"))
            for surface, slug in unlinked_in_body(body, terms):
                print(f"  todo  {rel}: '{surface}' is used but not linked -> [[{slug}]]")
                total += 1

    if total == 0:
        print("glossary_scan: no unlinked term occurrences — vault is fully linked.")
    elif apply:
        print(f"\nglossary_scan: linked {total} occurrence(s) across {touched_notes} note(s). "
              "Commit them — the touched notes re-embed (the links are real content).")
    else:
        print(f"\nglossary_scan: {total} unlinked occurrence(s). Re-run with --apply to insert "
              "the links.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Link glossary terms in note bodies (PARA(G)).")
    ap.add_argument("--apply", action="store_true",
                    help="insert the [[term]] links (default: report only)")
    args = ap.parse_args(argv)
    if not GLOSSARY_DIR.exists():
        print("glossary_scan: no vault/glossary/ — nothing to scan.")
        return 0
    return scan(args.apply)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
