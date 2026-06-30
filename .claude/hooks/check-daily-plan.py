#!/usr/bin/env python3
"""SessionStart hook: prompt for a fresh daily-plan.md when stale or missing.

Installed by ai-project-status' setup-new-repo.sh. Stdout is automatically
injected as a system reminder before Claude sees the user's first prompt;
silent (no output, exit 0) when the plan is fresh, so successful sessions
are unaffected.

Staleness rule: plan_date < most_recent_weekday(today). Weekend tolerance —
a Friday plan stays fresh through Sunday and gets re-prompted on Monday.
"""
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path


def most_recent_weekday(today: date) -> date:
    if today.weekday() < 5:
        return today
    return today - timedelta(days=today.weekday() - 4)


def repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(out.stdout.strip())


def main() -> int:
    today = date.today()
    try:
        plan = repo_root() / "daily-plan.md"
    except subprocess.CalledProcessError:
        return 0  # not in a git repo; do nothing

    today_iso = today.isoformat()
    fresh_template = (
        "Before doing other work, ask the user for today's plan and "
        "overwrite `daily-plan.md` with this header:\n\n"
        f"    # Daily plan — {today_iso}\n\n"
        "Body: one short paragraph of intent plus a small ASCII diagram "
        "of the day's shape (timeline, flow, milestones). "
        "ai-project-status aggregates this across tracked repos."
    )

    if not plan.exists():
        print("There is no `daily-plan.md` in this repo. " + fresh_template)
        return 0

    text = plan.read_text()
    first_line = text.splitlines()[0] if text else ""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", first_line)
    if not m:
        print(
            "`daily-plan.md` exists but its first line is not in the "
            "expected `# Daily plan — YYYY-MM-DD` format. " + fresh_template
        )
        return 0

    try:
        plan_date = date.fromisoformat(m.group(1))
    except ValueError:
        print("`daily-plan.md` header has an invalid date. " + fresh_template)
        return 0

    if plan_date < most_recent_weekday(today):
        print(
            f"`daily-plan.md` is stale (last updated {plan_date.isoformat()}). "
            + fresh_template
        )
        return 0

    return 0  # fresh; silent


if __name__ == "__main__":
    sys.exit(main())
