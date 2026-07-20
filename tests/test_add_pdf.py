#!/usr/bin/env python3
"""Tests for add_pdf — folder-first selection + the end-to-end ingest chain (task #7 M5).

Selection is pure logic and always runs. The full ingest (move -> extract -> chunk -> embed
-> load -> searchable) needs pypdf, so that test skips cleanly when the optional dep is absent
(as in CI). It builds a real PDF in a tempdir and drives the whole chain against a temp vault
+ cache, ending in a search + passage fetch.

    python3 tests/test_add_pdf.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ["SECOND_BRAIN_EMBEDDER"] = "test"

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "tests"))
import add_pdf  # noqa: E402
import pdf_config  # noqa: E402
import pdf_search  # noqa: E402
from test_pdf_extract import _make_pdf  # noqa: E402  (pure minimal-PDF writer, no pypdf)

try:
    import pypdf  # noqa: F401
    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False


class SelectionTest(unittest.TestCase):
    def test_list_pdfs_keeps_only_pdfs_and_handles_missing_folder(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / "a.pdf").write_bytes(b"%PDF-1.4")
            (folder / "b.pdf").write_bytes(b"%PDF-1.4")
            (folder / "notes.txt").write_text("x")
            names = {p.name for p in add_pdf.list_pdfs(folder)}
            self.assertEqual(names, {"a.pdf", "b.pdf"})
            self.assertEqual(add_pdf.list_pdfs(folder / "nope"), [])

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permissions")
    def test_unreadable_folder_raises_instead_of_looking_empty(self):
        """A denied folder must NOT be reported as an empty one (task #38).

        The bug this pins: ``Path.glob`` swallows ``PermissionError`` and yields nothing, so a
        folder holding PDFs we may not read returned ``[]`` — the same answer as a genuinely
        empty folder. The fixture is a directory the test process really cannot enumerate;
        an empty-folder fixture would reproduce the blind spot rather than catch it.
        """
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "denied"
            folder.mkdir()
            (folder / "secret.pdf").write_bytes(b"%PDF-1.4")   # present but unreachable
            os.chmod(folder, 0o000)
            try:
                self.assertFalse(add_pdf.folder_readable(folder))
                with self.assertRaises(PermissionError):
                    add_pdf.list_pdfs(folder)
                # …and the two cases stay distinguishable: readable-and-empty still returns [].
                empty = Path(td) / "empty"
                empty.mkdir()
                self.assertTrue(add_pdf.folder_readable(empty))
                self.assertEqual(add_pdf.list_pdfs(empty), [])
            finally:
                os.chmod(folder, 0o700)  # let TemporaryDirectory clean up

    def test_folder_readable_is_false_for_absent_folder(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(add_pdf.folder_readable(Path(td) / "nope"))

    def test_list_pdfs_alphabetical_and_paginated(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(pdf_config, "list_sort", return_value="alphabetical"):
            folder = Path(td)
            for name in ("gamma.pdf", "alpha.pdf", "beta.pdf"):
                (folder / name).write_bytes(b"%PDF-1.4")
            self.assertEqual([p.name for p in add_pdf.list_pdfs(folder)],
                             ["alpha.pdf", "beta.pdf", "gamma.pdf"])
            self.assertEqual([p.name for p in add_pdf.list_pdfs(folder, offset=1, limit=1)],
                             ["beta.pdf"])

    def test_inbox_folders_resolve_relative_to_repo_and_expand_absolute(self):
        with mock.patch.object(pdf_config, "inbox_dirs",
                               return_value=["vault/inbox", "/tmp/elsewhere"]), \
                mock.patch.object(add_pdf, "REPO_ROOT", Path("/brain")):
            folders = add_pdf.inbox_folders()
            self.assertEqual(folders[0], Path("/brain/vault/inbox"))
            self.assertEqual(folders[1], Path("/tmp/elsewhere"))


@unittest.skipUnless(HAVE_PYPDF, "pypdf not installed (optional dep, requirements-pdf.txt)")
class IngestTest(unittest.TestCase):
    def test_ingest_makes_a_pdf_searchable_without_committing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "vault").mkdir()
            inbox = tmp / "inbox"
            inbox.mkdir()
            pdf = inbox / "paper.pdf"
            pdf.write_bytes(_make_pdf(["alpha zephyr overview", "beta gamma details"]))

            with mock.patch.object(add_pdf, "REPO_ROOT", tmp), \
                    mock.patch.object(add_pdf, "VAULT_DIR", tmp / "vault"), \
                    mock.patch.object(add_pdf, "CACHE_DIR", tmp / "data"), \
                    mock.patch.object(add_pdf, "DB_PATH", tmp / "data" / "brain.db"), \
                    mock.patch.object(pdf_search, "DB_PATH", tmp / "data" / "brain.db"):
                summary = add_pdf.add_pdf(pdf, "resources")

                dest = tmp / "vault" / "resources" / "paper.pdf"
                self.assertTrue(dest.exists(), "PDF moved into the vault")
                self.assertFalse(pdf.exists(), "source removed (moved, not copied)")
                self.assertTrue((dest.parent / ".paper.pdf.embed.json").exists(), "sidecar written")
                self.assertGreaterEqual(summary["chunks"], 1)
                self.assertEqual(summary["source_file"], "vault/resources/paper.pdf")

                # no git side effects: ingest never created a repo here
                self.assertFalse((tmp / ".git").exists())

                # the passage is now searchable, and fetchable in full
                hits = pdf_search.search_pdf("zephyr", k=5, result_mode="all_chunks")
                self.assertTrue(hits)
                self.assertEqual(hits[0].source_file, "vault/resources/paper.pdf")
                passage = pdf_search.get_passage("vault/resources/paper.pdf", hits[0].chunk_id)
                self.assertIsNotNone(passage)
                self.assertIn("zephyr", passage["text"])

    def test_refuses_unknown_para_root_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "vault" / "resources").mkdir(parents=True)
            src = tmp / "paper.pdf"
            src.write_bytes(_make_pdf(["hello world"]))
            with mock.patch.object(add_pdf, "REPO_ROOT", tmp), \
                    mock.patch.object(add_pdf, "VAULT_DIR", tmp / "vault"), \
                    mock.patch.object(add_pdf, "CACHE_DIR", tmp / "data"), \
                    mock.patch.object(add_pdf, "DB_PATH", tmp / "data" / "brain.db"):
                with self.assertRaises(ValueError):
                    add_pdf.add_pdf(src, "nonsense")
                # pre-create the destination -> refuse overwrite
                (tmp / "vault" / "resources" / "paper.pdf").write_bytes(b"%PDF-1.4")
                with self.assertRaises(ValueError):
                    add_pdf.add_pdf(src, "resources", move=False)


if __name__ == "__main__":
    unittest.main()
