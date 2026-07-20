#!/usr/bin/env python3
"""An ingested PDF must really be git-ignored, not merely untracked (task #39).

`add_pdf` tells the user "Not committed (PDFs are git-ignored)" and docs/pdf-ingestion.md
decision 2 says the same. That claim shipped for the whole of task #7 while no `.gitignore`
rule matched `*.pdf` — the PDF was *untracked*, which looks identical in casual use and is
not the same thing at all: one `git add -A` commits a multi-megabyte binary into the brain.

The check runs `git check-ignore`, so it tests the behaviour a user actually gets rather
than the presence of a string in a file — a pattern that is present but wrong (bad anchor,
wrong glob) would still fail here.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git_available() -> bool:
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=REPO_ROOT,
                       capture_output=True, check=True, timeout=10)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _ignored(rel: str) -> bool:
    """Does git ignore ``rel``? (exit 0 = ignored, 1 = not ignored)"""
    return subprocess.run(["git", "check-ignore", "-q", rel], cwd=REPO_ROOT,
                          capture_output=True, timeout=10).returncode == 0


@unittest.skipUnless(_git_available(), "needs a git work tree")
class PdfGitignoreTest(unittest.TestCase):
    def test_vault_pdfs_are_ignored_at_every_para_root(self):
        for para in ("projects", "areas", "resources", "archive"):
            with self.subTest(para=para):
                self.assertTrue(_ignored(f"vault/{para}/paper.pdf"),
                                f"an ingested PDF under vault/{para}/ is not git-ignored — "
                                f"`git add -A` would commit a binary into the brain")

    def test_pdf_sidecar_is_ignored(self):
        """The derived chunk sidecar is covered too (by the existing sidecar rule)."""
        self.assertTrue(_ignored("vault/resources/.paper.pdf.embed.json"))

    def test_notes_are_still_committed(self):
        """The guard must not over-reach: Markdown notes are the thing we DO commit."""
        self.assertFalse(_ignored("vault/resources/some-note.md"))
