"""dashboard_audit: stale rows, missing rows and finished rows, against a real git repo."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dashboard_audit as da  # noqa: E402

DASH = """# Dashboard

| Project | Next action | Blocked on | Last touched |
| --- | --- | --- | --- |
| [[alpha]] | do a thing | nobody | {alpha} |
| [[bravo]] | do a thing | nobody | 2026-01-01 |
| [[example-project]] | placeholder | nobody | 2026-01-01 |
"""


def _git(root: Path, *args: str, date: str | None = None) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{date}T12:00:00"
    return subprocess.run(["git", *args], cwd=root, env=env, check=True,
                          capture_output=True, text=True).stdout


class DashboardAudit(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "core.hooksPath", "/dev/null")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self, date: str) -> None:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "c", date=date)

    def kinds(self, only=None):
        return sorted((f.kind, f.name) for f in da.audit(self.root, only))

    def base(self, alpha_row: str = "2026-02-01"):
        self.write("vault/dashboard-index.md", DASH.format(alpha=alpha_row))
        self.write("vault/projects/alpha/alpha.md", "# Alpha\n- [ ] one\n")
        self.write("vault/projects/bravo.md", "# Bravo\n- [x] done\n")
        self.commit("2026-01-01")

    def test_rows_are_parsed_link_and_date(self):
        rows = da.parse_rows(DASH.format(alpha="2026-02-01"))
        self.assertEqual([(r.name, r.touched) for r in rows],
                         [("alpha", "2026-02-01"), ("bravo", "2026-01-01"),
                          ("example-project", "2026-01-01")])

    def test_an_aliased_link_in_a_table_names_the_note(self):
        rows = da.parse_rows("| [[alpha\\|Alpha, aliased]] | x | y | 2026-02-01 |\n"
                             "| [[bravo|Bravo]] | x | y | 2026-01-01 |\n")
        self.assertEqual([r.name for r in rows], ["alpha", "bravo"])

    def test_current_dashboard_reports_nothing(self):
        self.base()
        self.assertEqual(self.kinds(), [])

    def test_work_after_the_row_date_is_stale(self):
        self.base()
        self.write("vault/projects/alpha/alpha--notes.md", "# Notes\n")
        self.commit("2026-03-01")
        self.assertEqual(self.kinds(), [("stale", "alpha")])

    def test_folder_entry_note_covers_the_whole_folder(self):
        # The change is to a sibling, not to alpha.md itself — still alpha's row.
        self.base()
        self.write("vault/projects/alpha/alpha--more.md", "# More\n")
        self.commit("2026-03-01")
        self.assertIn(("stale", "alpha"), self.kinds())

    def test_project_with_open_items_and_no_row_is_missing(self):
        self.base()
        self.write("vault/projects/charlie.md", "# Charlie\n- [ ] a\n- [ ] b\n")
        self.commit("2026-01-01")
        found = [f for f in da.audit(self.root) if f.kind == "missing"]
        self.assertEqual([f.name for f in found], ["charlie"])
        self.assertIn("2 open item(s)", found[0].message)

    def test_project_with_nothing_open_needs_no_row(self):
        self.base()
        self.write("vault/projects/delta.md", "# Delta\n- [x] done\n")
        self.commit("2026-01-01")
        self.assertEqual(self.kinds(), [])

    def test_archived_project_with_a_row_is_finished(self):
        self.base()
        (self.root / "vault/archive").mkdir(parents=True)
        _git(self.root, "mv", "vault/projects/bravo.md", "vault/archive/bravo.md")
        self.commit("2026-01-01")
        self.assertEqual(self.kinds(), [("finished", "bravo")])

    def test_unresolved_link_is_ignored(self):
        # The seeded dashboard ships an [[example-project]] placeholder; a fresh brain is clean.
        self.base()
        self.assertNotIn("example-project", [n for _, n in self.kinds()])

    def test_no_dashboard_no_findings(self):
        self.write("vault/projects/charlie.md", "- [ ] a\n")
        self.commit("2026-01-01")
        self.assertEqual(da.audit(self.root), [])

    def test_from_commit_limits_to_touched_projects(self):
        self.base()
        self.write("vault/projects/charlie.md", "- [ ] a\n")  # missing, but not touched below
        self.commit("2026-01-01")
        self.write("vault/projects/alpha/alpha.md", "# Alpha\n- [ ] one\n- [ ] two\n")
        self.commit("2026-03-01")
        touched = da.touched_projects(self.root, "HEAD")
        self.assertEqual(touched, {"alpha"})
        self.assertEqual(self.kinds(touched), [("stale", "alpha")])

    def test_touched_projects_names_flat_notes_by_stem(self):
        self.base()
        self.write("vault/projects/bravo.md", "# Bravo\n- [ ] new\n")
        self.commit("2026-01-01")
        self.assertEqual(da.touched_projects(self.root, "HEAD"), {"bravo"})


if __name__ == "__main__":
    unittest.main()
