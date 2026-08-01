#!/usr/bin/env bash
#
# Merge a finished worker's branch into main and tear down its worktree.
#
#   orchestrator/integrate.sh <worker-name> [--keep-worktree]
#
# Runs the test suite before merging. A worker that broke the build does not get
# merged, no matter what its result JSON claims — self-reported success from an
# agent is a claim, not evidence.

set -euo pipefail

WORKER="${1:?usage: $0 <worker-name> [--keep-worktree]}"
KEEP="${2:-}"

ROOT="$(git rev-parse --show-toplevel)"
BRANCH="agent/$WORKER"
WORKTREE="$ROOT/.worktrees/$WORKER"

# The only interpreter with the project's dependencies. Plain `python3` is
# whatever is on PATH — on a machine with Anaconda first, it has pytest but not
# selectolax, so the suite dies during collection and every merge is refused for
# a reason that has nothing to do with the worker's changes.
PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "no interpreter at $PYTHON — cannot verify $BRANCH, refusing to merge." >&2
    exit 70
fi

git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH" || {
    echo "no branch $BRANCH — was this worker ever dispatched?" >&2
    exit 66
}

if [[ -z "$(git -C "$ROOT" rev-list "HEAD..$BRANCH")" ]]; then
    echo "$BRANCH has no commits ahead of HEAD; nothing to integrate." >&2
    exit 0
fi

# Fail closed. A missing worktree used to mean "skip the tests and merge anyway",
# which inverted the one guarantee this script exists to provide.
echo "==> Running tests on $BRANCH"
if [[ ! -d "$WORKTREE" ]]; then
    echo "no worktree at $WORKTREE — cannot verify $BRANCH, refusing to merge." >&2
    echo "re-dispatch the worker, or check out the branch and test it by hand." >&2
    exit 70
fi

( cd "$WORKTREE" && "$PYTHON" -m pytest -q ) || {
    echo "TESTS FAILED on $BRANCH — refusing to merge." >&2
    exit 1
}

# A conflicted merge under `set -e` would abort the script with MERGE_HEAD still
# in place, leaving the repo mid-merge; the next integrate then compounds it.
# Unattended, that wedges every remaining task in the queue.
echo "==> Merging $BRANCH into $(git -C "$ROOT" branch --show-current)"
if ! git -C "$ROOT" merge --no-ff "$BRANCH" -m "Integrate work from $WORKER"; then
    echo "MERGE CONFLICT integrating $BRANCH — rolling back, leaving branch intact." >&2
    git -C "$ROOT" merge --abort 2>/dev/null || true
    exit 1
fi

if [[ "$KEEP" != "--keep-worktree" ]]; then
    git -C "$ROOT" worktree remove "$WORKTREE" --force 2>/dev/null || true
    git -C "$ROOT" branch -d "$BRANCH" 2>/dev/null || true
    rm -f "$ROOT/orchestrator/runs/$WORKER.json" "$ROOT/orchestrator/runs/$WORKER.log"
fi

echo "==> Integrated $WORKER"
