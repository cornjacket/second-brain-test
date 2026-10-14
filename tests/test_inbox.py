"""doctor's inbox count: only ``- `` lines under ``## Messages`` are messages."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import doctor  # noqa: E402


class InboxMessages(unittest.TestCase):
    def test_the_shipped_seed_is_empty(self):
        # The seed's explanatory bullets sit under other headings and must not count.
        seed = (ROOT / "seeds" / "inbox.md").read_text(encoding="utf-8")
        self.assertEqual(doctor.inbox_messages(seed), [])

    def test_lines_under_messages_count(self):
        text = ("# Inbox\n\n## How\n\n- not a message\n\n## Messages\n\n"
                "<!-- comment -->\n- 2026-10-14: file the article\n- 2026-10-15: check email\n")
        self.assertEqual(doctor.inbox_messages(text),
                         ["- 2026-10-14: file the article", "- 2026-10-15: check email"])

    def test_a_later_heading_ends_the_section(self):
        text = "## Messages\n- one\n## Later\n- not one\n"
        self.assertEqual(doctor.inbox_messages(text), ["- one"])


if __name__ == "__main__":
    unittest.main()
