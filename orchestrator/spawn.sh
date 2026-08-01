#!/usr/bin/env bash
#
# Dispatch one Claude CLI worker against a task file, in its own git worktree.
#
#   orchestrator/spawn.sh <worker-name> <task-file> [--fg]
#
# Antigravity's manager agent calls this. Each worker gets an isolated worktree
# and its own branch, so N workers can run at once without fighting over the
# index or each other's edits. The worker's JSON result lands in
# orchestrator/runs/<worker-name>.json for the manager to read.
#
# By default the worker runs in the background and this script returns
# immediately with the PID. Pass --fg to block until it finishes.

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: $0 <worker-name> <task-file> [--fg]" >&2
    exit 64
fi

WORKER="$1"
TASK_FILE="$2"
MODE="${3:---bg}"

ROOT="$(git rev-parse --show-toplevel)"
WORKTREE="$ROOT/.worktrees/$WORKER"
BRANCH="agent/$WORKER"
RUNS="$ROOT/orchestrator/runs"
RESULT="$RUNS/$WORKER.json"
LOG="$RUNS/$WORKER.log"

if [[ ! -f "$ROOT/$TASK_FILE" && ! -f "$TASK_FILE" ]]; then
    echo "task file not found: $TASK_FILE" >&2
    exit 66
fi
[[ -f "$TASK_FILE" ]] || TASK_FILE="$ROOT/$TASK_FILE"

command -v claude >/dev/null 2>&1 || { echo "claude CLI not on PATH" >&2; exit 69; }

mkdir -p "$RUNS"

# Reuse the worktree if this worker already has one — resuming a task should not
# throw away its work in progress.
if [[ ! -d "$WORKTREE" ]]; then
    git -C "$ROOT" worktree add -B "$BRANCH" "$WORKTREE" HEAD >/dev/null
fi

# Tools the worker is allowed to use without asking. Bash is scoped to specific
# commands rather than opened wholesale — an unattended agent with unrestricted
# shell is not something you want running while you are away from the keyboard.
ALLOWED_TOOLS='Read,Write,Edit,Glob,Grep,TodoWrite,Bash(python:*),Bash(python3:*),Bash(pytest:*),Bash(uv:*),Bash(ruff:*),Bash(git add:*),Bash(git commit:*),Bash(git diff:*),Bash(git status:*),Bash(git log:*),Bash(ls:*),Bash(mkdir:*)'

run_worker() {
    cd "$WORKTREE"
    claude -p "$(cat "$TASK_FILE")" \
        --output-format json \
        --permission-mode acceptEdits \
        --allowedTools "$ALLOWED_TOOLS" \
        --disallowedTools 'Bash(git push:*),Bash(rm:*),Bash(curl:*),WebFetch' \
        > "$RESULT" 2> "$LOG"
}

if [[ "$MODE" == "--fg" ]]; then
    run_worker
    echo "worker '$WORKER' finished -> $RESULT"
else
    run_worker &
    echo "worker '$WORKER' started (pid $!) -> $RESULT"
fi
