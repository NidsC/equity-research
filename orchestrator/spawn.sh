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
#
# Nothing here is supervised while it runs overnight, so a worker that wedges or
# loops must stop on its own rather than bill until morning. The bound is a
# wall-clock timeout; overnight.sh adds a spend ceiling across the whole queue.

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: $0 <worker-name> <task-file> [--fg]" >&2
    exit 64
fi

WORKER="$1"
TASK_FILE="$2"
MODE="${3:---bg}"

# Wall-clock bound. Override per-dispatch through the environment.
#
# There is deliberately no turn cap: `--max-turns` is not in this CLI's
# documented flag surface, and its argument parser accepts unknown flags without
# complaint, so a typo'd bound would look like it was working right up until it
# wasn't. An unattended run should not rest on a flag that cannot be verified.
TIMEOUT="${ER_WORKER_TIMEOUT:-1800}"

ROOT="$(git rev-parse --show-toplevel)"
WORKTREE="$ROOT/.worktrees/$WORKER"
BRANCH="agent/$WORKER"
RUNS="$ROOT/orchestrator/runs"
RESULT="$RUNS/$WORKER.json"
LOG="$RUNS/$WORKER.log"
PIDFILE="$RUNS/$WORKER.pid"

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
#
# `.venv/bin/python` is listed explicitly: it is the only interpreter with the
# project's dependencies installed, and `Bash(python3:*)` does not match a path.
ALLOWED_TOOLS='Read,Write,Edit,Glob,Grep,TodoWrite,Bash(.venv/bin/python:*),Bash(python:*),Bash(python3:*),Bash(pytest:*),Bash(uv:*),Bash(ruff:*),Bash(git add:*),Bash(git commit:*),Bash(git diff:*),Bash(git status:*),Bash(git log:*),Bash(ls:*),Bash(mkdir:*)'

# No `timeout(1)` on macOS and no `gtimeout` unless coreutils is installed, so
# fall back to perl: a pending alarm survives execve, and SIGALRM's default
# action terminates the process. Exit status is 124 (timeout) or 142 (SIGALRM).
_with_timeout() {
    local secs="$1"; shift
    if command -v timeout >/dev/null 2>&1; then
        timeout "$secs" "$@"
    elif command -v gtimeout >/dev/null 2>&1; then
        gtimeout "$secs" "$@"
    elif command -v perl >/dev/null 2>&1; then
        perl -e 'my $t = shift; alarm $t; exec @ARGV or die "exec failed: $!\n";' "$secs" "$@"
    else
        echo "no timeout mechanism available; running unbounded" >&2
        "$@"
    fi
}

# status.sh reads an empty or unparseable result as "still running". A worker
# that died therefore has to leave behind a result that says so, or the poller
# waits on it forever.
_write_failure() {
    local reason="$1"
    [[ -s "$RESULT" ]] && mv "$RESULT" "$RESULT.partial"
    python3 - "$RESULT" "$reason" <<'PY'
import json, sys
path, reason = sys.argv[1], sys.argv[2]
with open(path, "w") as fh:
    json.dump({
        "is_error": True,
        "subtype": "dispatch_error",
        "result": reason,
        "total_cost_usd": None,
    }, fh)
PY
}

run_worker() {
    cd "$WORKTREE"
    local rc=0
    _with_timeout "$TIMEOUT" claude -p "$(cat "$TASK_FILE")" \
        --output-format json \
        --permission-mode acceptEdits \
        --allowedTools "$ALLOWED_TOOLS" \
        --disallowedTools 'Bash(git push:*),Bash(rm:*),Bash(curl:*),WebFetch' \
        > "$RESULT" 2> "$LOG" || rc=$?

    if [[ $rc -ne 0 ]]; then
        case $rc in
            124|142) _write_failure "timed out after ${TIMEOUT}s (partial output in $(basename "$RESULT").partial)" ;;
            *)       _write_failure "worker exited $rc; see $(basename "$LOG")" ;;
        esac
    fi
    rm -f "$PIDFILE"
}

if [[ "$MODE" == "--fg" ]]; then
    run_worker
    echo "worker '$WORKER' finished -> $RESULT"
else
    # Re-invoke ourselves in foreground mode under nohup rather than serialising
    # the worker function into a subshell. The worktree setup above is
    # idempotent, so the second pass is a no-op up to this point.
    #
    # nohup, not setsid: macOS has no setsid, and without it a worker dies with
    # the terminal session that launched it. The recorded PID is this wrapper's;
    # killing it needs the descendants too (see kill_tree in overnight.sh).
    nohup "$ROOT/orchestrator/spawn.sh" "$WORKER" "$TASK_FILE" --fg >/dev/null 2>&1 &
    echo $! > "$PIDFILE"
    echo "worker '$WORKER' started (pid $(cat "$PIDFILE")) -> $RESULT"
fi
