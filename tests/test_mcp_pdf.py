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

    ``raise_exc`` simulates the request itself failing; ``action`` other than 'accept'
    simulates a decline/cancel. On accept it reads the schema's single field name and returns
    the next queued value under it, exactly as the real ElicitationResult does.

    ``declares`` models what the client announced at initialize (task #40) — the question the
    server must ask *before* eliciting, because a client without the capability returns a
    synthetic cancel that is indistinguishable on the wire from a human pressing Escape.
    """
    def __init__(self, answers=None, action="accept", raise_exc=False,
                 declares=True, client=("test-client", "1.0")):
        self._answers = list(answers or [])
        self._action = action
        self._raise = raise_exc
        caps = types.SimpleNamespace(elicitation={} if declares else None)
        info = types.SimpleNamespace(name=client[0], version=client[1])
        self.session = types.SimpleNamespace(
            client_params=types.SimpleNamespace(capabilities=caps, clientInfo=info))

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

    def _run_guided(self, ctx):
        """Drive add_pdf_guided against a one-PDF inbox; returns (output, ingested-calls)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            inbox = tmp / "inbox"
            inbox.mkdir()
            (inbox / "paper.pdf").write_bytes(b"%PDF-1.4")
            ingested = []
            with mock.patch.object(_add_pdf, "REPO_ROOT", tmp), \
                    mock.patch.object(pdf_config, "inbox_dirs", return_value=[str(inbox)]), \
                    mock.patch.object(_add_pdf, "add_pdf",
                                      side_effect=lambda *a: ingested.append(a)):
                return asyncio.run(M.add_pdf_guided(ctx)), ingested

    # --- task #40: the four failure modes must be DISTINGUISHABLE -------------------------
    # The old code returned one string for all of them and asserted the client lacked
    # elicitation. These tests fail if any two collapse back into the same message.

    def test_unsupported_client_is_named_as_unsupported(self):
        out, ingested = self._run_guided(_FakeCtx(declares=False, client=("cowork", "9.9")))
        self.assertIn("did not declare", out)
        self.assertIn("cowork v9.9", out)              # the client is named, with its version
        self.assertIn("list_inbox_pdfs", out)          # still points at the chat baseline
        self.assertEqual(ingested, [])

    def test_cancel_on_a_supporting_client_is_not_called_unsupported(self):
        """The old bug: pressing Escape told the user their client lacked the feature."""
        out, ingested = self._run_guided(_FakeCtx(action="cancel", declares=True))
        self.assertIn("cancel", out.lower())
        self.assertNotIn("did not declare", out)
        self.assertIn("source folder", out)            # names the step it stopped at
        self.assertEqual(ingested, [])

    def test_error_reports_the_reason_rather_than_guessing(self):
        out, ingested = self._run_guided(_FakeCtx(raise_exc=True, declares=True))
        self.assertIn("failed", out)
        self.assertIn("RuntimeError", out)             # the actual cause is surfaced
        self.assertNotIn("did not declare", out)
        self.assertEqual(ingested, [])

    def test_the_four_outcomes_produce_four_different_messages(self):
        """A single assertion that the diagnostic actually discriminates."""
        msgs = {
            "unsupported": self._run_guided(_FakeCtx(declares=False))[0],
            "cancel": self._run_guided(_FakeCtx(action="cancel"))[0],
            "decline": self._run_guided(_FakeCtx(action="decline"))[0],
            "error": self._run_guided(_FakeCtx(raise_exc=True))[0],
        }
        self.assertEqual(len(set(msgs.values())), 4,
                         f"failure modes collapsed into the same message: {msgs}")


if __name__ == "__main__":
    unittest.main()
