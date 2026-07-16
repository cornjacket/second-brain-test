#!/usr/bin/env python3
"""Tests for tag_hygiene — the deterministic detector, applier, and near-miss rule.

Synthetic tag vocabularies with *planted* issues (a near-miss split, a near-universal
tag, a leaked-title singleton) let us assert the exact flags and — just as important —
the absence of spurious ones. These fixtures are a development artifact: they are built
in a tempdir at run time, so there is nothing to emission-exclude.

    python3 tests/test_tag_hygiene.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import tag_hygiene  # noqa: E402


def _write_note(vault: Path, rel: str, tags: list[str], body: str = "Body.") -> Path:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    front = f"tags: [{', '.join(tags)}]" if tags else "tags: []"
    path.write_text(f"---\n{front}\n---\n\n# {path.stem}\n\n{body}\n", encoding="utf-8")
    return path


def _planted_vault(tmp: Path) -> Path:
    """A vault with exactly three planted issues and no incidental ones.

    - split          : `agents` (n1,n2) vs `ai-agents` (n3,n4), never co-occurring.
    - near-universal : `ai` on all 5 notes.
    - leaked title   : `create_second_brain` on one note (a singleton with an underscore).
    Every other tag rides two notes and no non-`ai` pair overlaps enough to be flagged.
    """
    vault = tmp / "vault"
    _write_note(vault, "projects/p1.md", ["ai", "agents", "retrieval"])
    _write_note(vault, "areas/a1.md", ["ai", "agents", "memory"])
    _write_note(vault, "resources/r1.md", ["ai", "ai-agents", "retrieval"])
    _write_note(vault, "resources/r2.md", ["ai", "ai-agents", "memory"])
    _write_note(vault, "archive/arc1.md", ["ai", "create_second_brain"])
    return vault


class DetectorTest(unittest.TestCase):
    def test_flags_exactly_the_three_planted_issues(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _planted_vault(Path(td))
            report = tag_hygiene.analyze(vault)

        self.assertEqual(report.near_miss, [["agents", "ai-agents"]])
        self.assertEqual({r["tag"] for r in report.near_universal}, {"ai"})
        self.assertEqual({r["tag"] for r in report.singletons}, {"create_second_brain"})
        self.assertEqual({r["tag"] for r in report.format_lint}, {"create_second_brain"})
        self.assertEqual(report.overlap, [], "no spurious overlap on a small vault")

    def test_clean_vault_is_clean(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            _write_note(vault, "projects/p1.md", ["retrieval", "search"])
            _write_note(vault, "areas/a1.md", ["retrieval", "memory"])
            _write_note(vault, "resources/r1.md", ["search", "memory"])
            report = tag_hygiene.analyze(vault)
        self.assertFalse(report.flagged, report.render())


class NearMissRuleTest(unittest.TestCase):
    def test_case_and_separator_variants(self):
        self.assertTrue(tag_hygiene.is_near_miss("ai-agents", "AI_Agents"))
        self.assertTrue(tag_hygiene.is_near_miss("machine learning", "machine-learning"))

    def test_typo_within_edit_distance_one(self):
        self.assertTrue(tag_hygiene.is_near_miss("agents", "agent"))    # one deletion
        self.assertTrue(tag_hygiene.is_near_miss("memory", "memori"))   # one substitution
        self.assertFalse(tag_hygiene.is_near_miss("retrieval", "retreival"))  # transpose == 2 edits
        self.assertFalse(tag_hygiene.is_near_miss("search", "retrieval"))

    def test_affix_qualification(self):
        self.assertTrue(tag_hygiene.is_near_miss("agents", "ai-agents"))
        self.assertTrue(tag_hygiene.is_near_miss("agents", "agents-framework"))
        self.assertFalse(tag_hygiene.is_near_miss("agents", "ai-agent-tools"))  # two extra tokens

    def test_near_miss_of_write_path(self):
        vocab = {"agents", "retrieval", "memory"}
        self.assertEqual(tag_hygiene.near_miss_of("ai-agents", vocab), "agents")
        self.assertEqual(tag_hygiene.near_miss_of("Agents", vocab), "agents")
        self.assertIsNone(tag_hygiene.near_miss_of("databases", vocab))
        self.assertIsNone(tag_hygiene.near_miss_of("agents", vocab), "exact reuse is not a miss")


class RewriteTagsTest(unittest.TestCase):
    def test_inline_rewrite_preserves_the_rest(self):
        text = "---\ntitle: keep me\ntags: [ai, ai-agents, retrieval]\n---\n\n# H\n\nBody.\n"
        out = tag_hygiene.rewrite_tags(text, {"ai-agents": "agents"})
        self.assertIn("tags: [ai, agents, retrieval]", out)
        self.assertIn("title: keep me", out)
        self.assertTrue(out.endswith("# H\n\nBody.\n"))

    def test_merge_dedupes(self):
        text = "---\ntags: [agents, ai-agents]\n---\n\nBody.\n"
        out = tag_hygiene.rewrite_tags(text, {"ai-agents": "agents"})
        self.assertIn("tags: [agents]", out)

    def test_idempotent_and_no_op_returns_none(self):
        text = "---\ntags: [agents, retrieval]\n---\n\nBody.\n"
        self.assertIsNone(tag_hygiene.rewrite_tags(text, {"ai-agents": "agents"}))
        self.assertIsNone(tag_hygiene.rewrite_tags(text, {"agents": "agents"}))

    def test_no_frontmatter_or_no_tags_key(self):
        self.assertIsNone(tag_hygiene.rewrite_tags("no frontmatter here\n", {"a": "b"}))
        self.assertIsNone(tag_hygiene.rewrite_tags("---\ntitle: x\n---\n\nBody.\n", {"a": "b"}))


class ApplyMappingTest(unittest.TestCase):
    def test_dry_run_changes_nothing_on_disk(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _planted_vault(Path(td))
            before = (vault / "resources/r1.md").read_text(encoding="utf-8")
            changes = tag_hygiene.apply_mapping(vault, {"ai-agents": "agents"}, dry_run=True)
            self.assertEqual({c.note for c in changes},
                             {"resources/r1.md", "resources/r2.md"})
            self.assertEqual((vault / "resources/r1.md").read_text(encoding="utf-8"), before)

    def test_apply_edits_only_carrying_notes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            vault = _planted_vault(Path(td))
            untouched = (vault / "projects/p1.md").read_text(encoding="utf-8")

            changes = tag_hygiene.apply_mapping(vault, {"ai-agents": "agents"}, dry_run=False)
            self.assertEqual({c.note for c in changes},
                             {"resources/r1.md", "resources/r2.md"})
            self.assertEqual(note_tags(vault, "resources/r1.md"),
                             ["ai", "agents", "retrieval"])
            self.assertEqual((vault / "projects/p1.md").read_text(encoding="utf-8"), untouched)

            # Second run is a pure no-op — the split is already merged.
            self.assertEqual(tag_hygiene.apply_mapping(vault, {"ai-agents": "agents"},
                                                       dry_run=False), [])


def note_tags(vault: Path, rel: str) -> list[str]:
    import note_view
    return note_view.frontmatter_tags((vault / rel).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
