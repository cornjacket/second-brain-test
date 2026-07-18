#!/usr/bin/env bash
# Desktop e2e — setup: isolate a run of the Desktop test suite on a disposable git
# branch so it can hit THIS brain with your existing Claude Desktop connection (ZERO
# reconfiguration), then be torn down to a byte-identical brain.
#
#   desktop-e2e/setup.sh [--brain PATH] [--branch NAME]
#
# Defaults: --brain = the brain this script ships in  --branch e2e-run
#
# Claude Desktop's MCP server operates on whatever is checked out in this brain, so a
# fresh branch IS a throwaway brain: every note the scenarios create commits onto that
# branch, never onto your working branch. If this brain has a remote, add_note DOES push
# the disposable branch there (it runs `git push origin <branch>`, which needs no upstream)
# — so the test branch surfaces on the remote for the duration of the run. That is harmless
# and intended: teardown deletes the disposable branch on the remote too, so nothing lingers.
#
# This asserts a known-good baseline before branching (clean tree + doctor green) so a
# later teardown failure can never be blamed on pre-existing drift, and records the base
# branch + HEAD for teardown to restore to.
set -euo pipefail

# The brain this suite ships in: the directory above this script (the brain root).
BRAIN="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="e2e-run"
while [ $# -gt 0 ]; do
  case "$1" in
    --brain)  BRAIN="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "setup: unknown argument: $1" >&2; exit 2 ;;
  esac
done

BRAIN="$(cd "$BRAIN" 2>/dev/null && pwd)" || { echo "setup: no such brain directory" >&2; exit 1; }
[ -d "$BRAIN/vault" ] && [ -d "$BRAIN/scripts" ] || { echo "setup: not a brain: $BRAIN (expected vault/ and scripts/)" >&2; exit 1; }
cd "$BRAIN"

STATE="$BRAIN/.git/desktop-e2e.state"

# Refuse to start on top of a prior run — the state file / branch must be clean first.
if [ -f "$STATE" ]; then
  echo "setup: a prior e2e run is still recorded ($STATE) — run teardown.sh first." >&2
  exit 1
fi
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "setup: branch '$BRANCH' already exists — run teardown.sh (or delete it) first." >&2
  exit 1
fi

# Baseline 1: a clean tree, so nothing uncommitted is carried onto the branch.
if [ -n "$(git status --porcelain)" ]; then
  echo "setup: working tree is not clean — commit or stash first:" >&2
  git status --short >&2
  exit 1
fi

BASE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
BASE_HEAD="$(git rev-parse HEAD)"

# Baseline 2: the derived search index already matches the vault. Restoring to a
# known-good target is only meaningful if the target was good to begin with.
echo "setup: verifying baseline (doctor.py) …"
if ! python3 scripts/doctor.py; then
  echo "setup: doctor is not green on '$BASE_BRANCH' — fix the baseline (e.g. doctor.py --repair) before running e2e." >&2
  exit 1
fi

# Record what to restore to, then branch. Written under .git/ so it is per-brain and
# never dirties the tree (git status ignores everything inside .git/).
printf 'base_branch=%s\nbase_head=%s\n' "$BASE_BRANCH" "$BASE_HEAD" > "$STATE"
git checkout -b "$BRANCH"

cat <<EOF

setup: ready. On disposable branch '$BRANCH' (base '$BASE_BRANCH' @ ${BASE_HEAD:0:7}).

Now, with NO Desktop reconfiguration (your Desktop is already connected to this brain):
  1. Paste the prompts from desktop-e2e/prompts/NN-*.md into Claude Desktop, in order.
  2. Verify:   python3 desktop-e2e/verify/run_all.py
  3. Tear down: desktop-e2e/teardown.sh

Every note the scenarios write commits onto '$BRANCH'; teardown deletes it and
rebuilds the index so '$BASE_BRANCH' comes back byte-identical.
EOF
