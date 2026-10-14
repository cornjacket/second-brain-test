#!/usr/bin/env python3
"""Keep ``vault/dashboard-index.md`` honest: find rows that went stale and projects with none.

The dashboard is curated by hand, and that is deliberate — its next-action and blocked-on
columns are judgment, which nothing can generate. But *curated* has a failure mode of its
own: nothing forces the curation. Work lands on a project, its row still says three weeks
ago; a new project collects twenty open checkboxes and never gets a row at all. The file
is then not merely stale but **lying**, and it is the one file an agent is told to trust
for "where did we leave off".

Two drifts are mechanical enough to detect, so this module detects them:

- **Stale row** — git says the project's files changed after the row's *Last touched* date.
- **Missing row** — a project under ``vault/projects/`` has open ``- [ ]`` items but no
  row links to it. A project with nothing open needs no row, so it is not reported.
- **Finished row** — a row links a note now under ``vault/archive/``, the "finished project
  never got its row removed" case the dashboard itself warns about.

Used by ``doctor.py`` (the standing audit) and by the post-commit hook with
``--from-commit HEAD`` (the in-the-moment nudge: this commit touched a project and left its
row alone). Neither writes the dashboard — the fix is a judgment call, so it stays a human
or agent edit. Encrypted brains are skipped: their vault is not in git, so git cannot date it.

    python3 scripts/dashboard_audit.py                    # audit the whole dashboard
    python3 scripts/dashboard_audit.py --from-commit HEAD  # only what one commit touched
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = "vault/dashboard-index.md"
PROJECTS = "vault/projects"
ARCHIVE = "vault/archive"

_LINK = re.compile(r"\[\[([^\]|#]+)")
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_OPEN = re.compile(r"^\s*- \[ \]", re.M)


@dataclass(frozen=True)
class Row:
    name: str
    touched: str | None  # YYYY-MM-DD from the last cell, or None if the row has no date


@dataclass(frozen=True)
class Finding:
    kind: str  # "stale" | "missing" | "finished"
    name: str
    message: str


def parse_rows(text: str) -> list[Row]:
    """Table rows that link a note: the first ``[[link]]`` names it, the last cell dates it."""
    rows = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        m = _LINK.search(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        d = _DATE.search(cells[-1]) if cells else None
        rows.append(Row(m.group(1).strip(), d.group(1) if d else None))
    return rows


def _note_index(root: Path) -> dict[str, Path]:
    """Note name → path, vault-wide. Names are unique (the pre-commit hook enforces it)."""
    return {p.stem: p for p in (root / "vault").rglob("*.md")}


def scope(note: Path) -> Path:
    """What a link stands for: a folder's entry note means the whole folder."""
    return note.parent if note.stem == note.parent.name else note


def projects(root: Path) -> dict[str, Path]:
    """Each top-level project: a folder (named by its entry note) or a flat note."""
    base = root / PROJECTS
    if not base.is_dir():
        return {}
    out = {}
    for p in sorted(base.iterdir()):
        if p.is_dir():
            out[p.name] = p
        elif p.suffix == ".md":
            out[p.stem] = p
    return out


def open_items(path: Path) -> int:
    files = path.rglob("*.md") if path.is_dir() else [path]
    n = 0
    for f in files:
        try:
            n += len(_OPEN.findall(f.read_text(encoding="utf-8")))
        except OSError:
            pass
    return n


def last_commit_date(root: Path, path: Path) -> str | None:
    """Committer date (YYYY-MM-DD) of the newest commit touching ``path``, or None."""
    r = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(path.relative_to(root))],
                       cwd=root, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    out = r.stdout.strip()
    return out or None


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def audit(root: Path = REPO_ROOT, only: set[str] | None = None) -> list[Finding]:
    """Every drift between the dashboard and the vault. ``only`` limits it to those names."""
    dash = root / DASHBOARD
    if not dash.is_file():
        return []
    rows = parse_rows(dash.read_text(encoding="utf-8"))
    notes = _note_index(root)
    findings = []

    linked = set()
    for row in rows:
        note = notes.get(row.name)
        if note is None:
            continue  # a placeholder or a typo; not this check's business
        target = scope(note)
        linked.add(_rel(root, target))
        if only is not None and row.name not in only:
            continue
        if _rel(root, note).startswith(ARCHIVE + "/"):
            findings.append(Finding("finished", row.name,
                                    f"[[{row.name}]] is archived but still has a dashboard row "
                                    f"— delete the row"))
            continue
        changed = last_commit_date(root, target)
        if changed and row.touched and changed > row.touched:
            findings.append(Finding("stale", row.name,
                                    f"[[{row.name}]] changed {changed} but its row says "
                                    f"{row.touched} — update its next action and Last touched"))

    for name, path in projects(root).items():
        if only is not None and name not in only:
            continue
        if _rel(root, path) in linked:
            continue
        n = open_items(path)
        if n:
            findings.append(Finding("missing", name,
                                    f"[[{name}]] has {n} open item(s) but no dashboard row "
                                    f"— add one, or close the items"))
    return findings


def touched_projects(root: Path, commit: str) -> set[str]:
    """Names of the projects a commit changed (the first path segment under projects/)."""
    r = subprocess.run(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit],
                       cwd=root, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    names = set()
    for line in r.stdout.splitlines():
        if line.startswith(PROJECTS + "/") and line.endswith(".md"):
            first = line[len(PROJECTS) + 1:].split("/", 1)[0]
            names.add(first[:-3] if first.endswith(".md") else first)
    return names


def _encrypted() -> bool:
    try:
        from features import encryption
        return encryption()
    except Exception:
        return False


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Report drift between the dashboard and the vault.")
    ap.add_argument("--from-commit", metavar="REV",
                    help="only the projects this commit touched (the post-commit nudge)")
    args = ap.parse_args(argv)

    if _encrypted():
        return 0
    only = None
    if args.from_commit:
        only = touched_projects(REPO_ROOT, args.from_commit)
        if not only:
            return 0
    for f in audit(REPO_ROOT, only):
        print(f"second-brain: dashboard: {f.message}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
