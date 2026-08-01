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

git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH" || {
    echo "no branch $BRANCH — was this worker ever dispatched?" >&2
    exit 66
}

if [[ -z "$(git -C "$ROOT" rev-list "HEAD..$BRANCH")" ]]; then
    echo "$BRANCH has no commits ahead of HEAD; nothing to integrate." >&2
    exit 0
fi

echo "==> Running tests on $BRANCH"
if [[ -d "$WORKTREE" ]]; then
    ( cd "$WORKTREE" && python3 -m pytest -q ) || {
        echo "TESTS FAILED on $BRANCH — refusing to merge." >&2
        exit 1
    }
fi

echo "==> Merging $BRANCH into $(git -C "$ROOT" branch --show-current)"
git -C "$ROOT" merge --no-ff "$BRANCH" -m "Integrate work from $WORKER"

if [[ "$KEEP" != "--keep-worktree" ]]; then
    git -C "$ROOT" worktree remove "$WORKTREE" --force 2>/dev/null || true
    git -C "$ROOT" branch -d "$BRANCH" 2>/dev/null || true
    rm -f "$ROOT/orchestrator/runs/$WORKER.json" "$ROOT/orchestrator/runs/$WORKER.log"
fi

echo "==> Integrated $WORKER"
