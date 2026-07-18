#!/usr/bin/env bash
# Desktop e2e — teardown: delete the disposable branch and restore THIS brain to a
# byte-identical state.
#
#   desktop-e2e/teardown.sh [--brain PATH] [--branch NAME]
#
# Defaults: --brain = the brain this script ships in  --branch e2e-run
#
# The search layer is DERIVED state git does not version: the per-note .embed.json
# vectors and the data/brain.db index. A branch swap changes the .md files but not
# this layer, so deleting the branch alone would leave a corrupted brain — phantom
# hits (test-note vectors still in the db), orphan sidecars (the test notes' gitignored
# .embed.json survive the delete), or missing embeddings. So this owns the derived
# layer too: doctor.py --repair drops the orphan sidecars and rebuilds data/brain.db
# from the restored vault, then a plain doctor.py must come back green.
#
# Fails LOUDLY if HEAD moved, the tree is dirty, or the index does not match — it
# never claims a clean-up it did not achieve. That assertion doubles as a standalone
# "did it clean up?" check.
set -euo pipefail

# The brain this suite ships in: the directory above this script (the brain root).
BRAIN="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="e2e-run"
while [ $# -gt 0 ]; do
  case "$1" in
    --brain)  BRAIN="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "teardown: unknown argument: $1" >&2; exit 2 ;;
  esac
done

BRAIN="$(cd "$BRAIN" 2>/dev/null && pwd)" || { echo "teardown: no such brain directory" >&2; exit 1; }
[ -d "$BRAIN/vault" ] && [ -d "$BRAIN/scripts" ] || { echo "teardown: not a brain: $BRAIN (expected vault/ and scripts/)" >&2; exit 1; }
cd "$BRAIN"

STATE="$BRAIN/.git/desktop-e2e.state"
[ -f "$STATE" ] || { echo "teardown: no recorded run ($STATE missing) — was setup.sh run against this brain?" >&2; exit 1; }
# shellcheck disable=SC1090
. "$STATE"
: "${base_branch:?teardown: state file missing base_branch}"
: "${base_head:?teardown: state file missing base_head}"

# Return to the base branch, then delete the disposable one. Checking out first is
# required — you cannot delete the branch you are standing on. gitignored derived
# files (orphan sidecars, brain.db) never block the checkout; a tracked-file conflict
# would, and that is a genuine surprise worth stopping on.
git checkout "$base_branch"
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git branch -D "$BRANCH"
else
  echo "teardown: branch '$BRANCH' already gone — restoring the index anyway."
fi

# add_note pushes on every commit, and `git push origin <branch>` needs no upstream — so if
# this brain has a remote, the disposable branch was created there too. A throwaway branch
# must not linger on the remote, so delete it there. Best-effort: a network/permission failure
# must not block the local restore below, but say so loudly so it gets cleaned up by hand.
if git remote get-url origin >/dev/null 2>&1 &&
   git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  echo "teardown: deleting disposable branch from origin …"
  if git push origin --delete "$BRANCH"; then
    echo "teardown: removed origin/$BRANCH."
  else
    echo "teardown: WARNING — could not delete origin/$BRANCH (network/permission?). Remove it by hand: git push origin --delete $BRANCH" >&2
  fi
fi

# Resync the derived layer to the restored vault: drop orphan sidecars + rebuild the cache.
echo "teardown: rebuilding the derived index (doctor.py --repair) …"
python3 scripts/doctor.py --repair

# Assert byte-identical restore, loudly.
fail=0
now_head="$(git rev-parse HEAD)"
if [ "$now_head" != "$base_head" ]; then
  echo "teardown: FAIL — HEAD is $now_head, expected $base_head (base moved during the run)." >&2
  fail=1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "teardown: FAIL — working tree is not clean after restore:" >&2
  git status --short >&2
  fail=1
fi
echo "teardown: verifying restored brain (doctor.py) …"
if ! python3 scripts/doctor.py; then
  echo "teardown: FAIL — doctor is not green after restore (phantom/orphan/stale index)." >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "teardown: brain is NOT restored — investigate before trusting it. State kept at $STATE." >&2
  exit 1
fi

rm -f "$STATE"
echo "teardown: done. '$base_branch' restored byte-identical @ ${base_head:0:7} — index clean, doctor green."
