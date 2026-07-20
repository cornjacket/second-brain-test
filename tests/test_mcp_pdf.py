#!/usr/bin/env python3
"""Tests for the PDF MCP tools (task #7 M6).

The tools are thin wrappers over add_pdf/pdf_search (both tested elsewhere), so this focuses
on what the wrapper adds: the ingest **security boundary** (refuse a file outside the
configured source folders) and the end-to-end list -> add -> search -> fetch flow through the
tool functions. Skips when the optional `mcp`/`pypdf` deps are absent (as in core CI).

    python3 tests/test_mcp_pdf.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

os.environ["SECOND_BRAIN_EMBEDDER"] = "test"

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

try:
    import mcp_server as M
    HAVE_MCP = True
except ImportError:
    HAVE_MCP = False

try:
    import pypdf  # noqa: F401
    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False

if HAVE_MCP:
    import add_pdf as _add_pdf
    import pdf_config
    import pdf_search as _pdf_search
    from test_pdf_extract import _make_pdf


def _point_at(tmp: Path, inbox: Path):
    """Patchers that repoint the MCP server + PDF modules at a throwaway brain."""
    return [
        mock.patch.object(M, "BRAIN", tmp),
        mock.patch.object(_add_pdf, "REPO_ROOT", tmp),
        mock.patch.object(_add_pdf, "VAULT_DIR", tmp / "vault"),
        mock.patch.object(_add_pdf, "CACHE_DIR", tmp / "data"),
        mock.patch.object(_add_pdf, "DB_PATH", tmp / "data" / "brain.db"),
        mock.patch.object(_pdf_search, "DB_PATH", tmp / "data" / "brain.db"),
        mock.patch.object(pdf_config, "inbox_dirs", return_value=[str(inbox)]),
    ]


@unittest.skipUnless(HAVE_MCP, "mcp not installed (optional dep, requirements-mcp.txt)")
class SecurityTest(unittest.TestCase):
    def test_add_pdf_refuses_a_file_outside_the_source_folders(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            inbox = tmp / "inbox"
            inbox.mkdir()
            (tmp / "vault").mkdir()
            outside = tmp / "secret.pdf"          # NOT under the configured inbox
            outside.write_bytes(b"%PDF-1.4")
            with mock.patch.multiple(_add_pdf, REPO_ROOT=tmp, VAULT_DIR=tmp / "vault"), \
                    mock.patch.object(M, "BRAIN", tmp), \
                    mock.patch.object(pdf_config, "inbox_dirs", return_value=[str(inbox)]):
                with self.assertRaises(ValueError):
                    M.add_pdf(str(outside), "resources")

    def test_list_inbox_pdfs_lists_folders_then_files(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            inbox = tmp / "inbox"
            inbox.mkdir()
            (inbox / "a.pdf").write_bytes(b"%PDF-1.4")
            with mock.patch.object(_add_pdf, "REPO_ROOT", tmp), \
                    mock.patch.object(pdf_config, "inbox_dirs", return_value=[str(inbox)]):
                folders = M.list_inbox_pdfs()
                self.assertEqual(folders,
                                 [{"folder": str(inbox), "exists": True, "readable": True}])
                files = M.list_inbox_pdfs(str(inbox))
                self.assertEqual([f["filename"] for f in files], ["a.pdf"])

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permissions")
    def test_list_inbox_pdfs_reports_denied_rather_than_empty(self):
        """An unreadable source folder must be visibly denied, never silently empty (task #38)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            denied = tmp / "denied"
            denied.mkdir()
            (denied / "a.pdf").write_bytes(b"%PDF-1.4")
            os.chmod(denied, 0o000)
            try:
                with mock.patch.object(_add_pdf, "REPO_ROOT", tmp), \
                        mock.patch.object(pdf_config, "inbox_dirs", return_value=[str(denied)]):
                    self.assertEqual(
                        M.list_inbox_pdfs(),
                        [{"folder": str(denied), "exists": True, "readable": False}])
                    # listing it must fail loudly rather than return an empty file list
                    with self.assertRaises(ValueError) as cm:
                        M.list_inbox_pdfs(str(denied))
                    self.assertIn("permission denied", str(cm.exception).lower())
            finally:
                os.chmod(denied, 0o700)


@unittest.skipUnless(HAVE_MCP and HAVE_PYPDF, "needs mcp + pypdf")
class FlowTest(unittest.TestCase):
    def test_add_then_search_then_fetch(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "vault").mkdir()
            inbox = tmp / "inbox"
            inbox.mkdir()
            pdf = inbox / "paper.pdf"
            pdf.write_bytes(_make_pdf(["alpha zephyr overview", "beta gamma details"]))

            patchers = _point_at(tmp, inbox)
            for p in patchers:
                p.start()
            try:
                msg = M.add_pdf(str(pdf), "resources")
                self.assertIn("searchable", msg)
                self.assertFalse(pdf.exists())          # moved out of the inbox

                hits = M.search_pdf_passages("zephyr", k=5)
                self.assertTrue(hits)
                self.assertTrue(hits[0]["source_file"].endswith("vault/resources/paper.pdf"))
                self.assertIn("page", hits[0])

                full = M.get_pdf_passage(hits[0]["source_file"], hits[0]["chunk_id"])
                self.assertIn("zephyr", full)
            finally:
                for p in patchers:
                    p.stop()


class _FakeCtx:
    """A stand-in Context whose ``elicit`` returns queued accepted answers — or refuses.

    ``raise_exc`` simulates a client without elicitation (errors); ``action`` other than
    'accept' simulates a decline/cancel. On accept it reads the schema's single field name and
    returns the next queued value under it, exactly as the real ElicitationResult does.
    """
    def __init__(self, answers=None, action="accept", raise_exc=False):
        self._answers = list(answers or [])
        self._action = action
        self._raise = raise_exc

    async def elicit(self, message, schema):
        if self._raise:
            raise RuntimeError("client does not support elicitation")
        field = next(iter(schema.model_fields))
        if self._action != "accept":
            return types.SimpleNamespace(action=self._action, data=None)
        value = self._answers.pop(0)
        return types.SimpleNamespace(action="accept",
                                     data=types.SimpleNamespace(**{field: value}))


@unittest.skipUnless(HAVE_MCP, "mcp not installed (optional dep, requirements-mcp.txt)")
class GuidedElicitTest(unittest.TestCase):
    def test_guided_drives_the_three_picks_and_ingests(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            inbox = tmp / "inbox"
            inbox.mkdir()
            (inbox / "paper.pdf").write_bytes(b"%PDF-1.4")
            captured = {}

            def fake_add(path, para):
                captured["path"], captured["para"] = Path(path), para
                return {"source_file": "vault/resources/paper.pdf", "pages": 2,
                        "chunks": 3, "moved": True}

            ctx = _FakeCtx(answers=[str(inbox), "paper.pdf", "resources"])
            with mock.patch.object(_add_pdf, "REPO_ROOT", tmp), \
                    mock.patch.object(pdf_config, "inbox_dirs", return_value=[str(inbox)]), \
                    mock.patch.object(_add_pdf, "add_pdf", side_effect=fake_add):
                out = asyncio.run(M.add_pdf_guided(ctx))
            self.assertIn("searchable", out)
            self.assertEqual(captured["para"], "resources")
            self.assertEqual(captured["path"], inbox / "paper.pdf")

    def test_guided_falls_back_when_elicitation_is_unsupported(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            inbox = tmp / "inbox"
            inbox.mkdir()
            (inbox / "paper.pdf").write_bytes(b"%PDF-1.4")
            ingested = []
            ctx = _FakeCtx(raise_exc=True)  # client with no elicitation
            with mock.patch.object(_add_pdf, "REPO_ROOT", tmp), \
                    mock.patch.object(pdf_config, "inbox_dirs", return_value=[str(inbox)]), \
                    mock.patch.object(_add_pdf, "add_pdf", side_effect=lambda *a: ingested.append(a)):
                out = asyncio.run(M.add_pdf_guided(ctx))
            self.assertIn("list_inbox_pdfs", out)     # points at the chat baseline
            self.assertEqual(ingested, [])            # nothing ingested


if __name__ == "__main__":
    unittest.main()
