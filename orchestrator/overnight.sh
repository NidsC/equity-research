#!/usr/bin/env bash
#
# Run a queue of tasks to completion, unattended.
#
#   orchestrator/overnight.sh [--queue DIR] [--budget USD] [--parallel N]
#                             [--timeout SECS] [--dry-run]
#
# This is the loop a human would otherwise sit in: dispatch, poll, integrate,
# repeat. It replaces the Antigravity manager for scheduled runs — a manager
# agent is useful when tasks need decomposing, but a queue of already-written
# task files needs a scheduler, not a model, and a shell script cannot decide
# at 3am to try something clever.
#
# Everything it does is bounded. Workers have a wall-clock timeout and a turn
# cap (see spawn.sh); the run as a whole has a dollar ceiling. When the ceiling
# is hit, in-flight workers are killed and nothing further is dispatched.
#
# Written for bash 3.2 — the macOS system shell. No associative arrays.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
RUNS="$ROOT/orchestrator/runs"
PYTHON="$ROOT/.venv/bin/python"

QUEUE_DIR="$ROOT/orchestrator/tasks/queue"
BUDGET_USD="20"
PARALLEL="3"
POLL_SECONDS="20"
DRY_RUN=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --queue)    QUEUE_DIR="$2"; shift 2 ;;
        --budget)   BUDGET_USD="$2"; shift 2 ;;
        --parallel) PARALLEL="$2"; shift 2 ;;
        --timeout)  export ER_WORKER_TIMEOUT="$2"; shift 2 ;;
        --dry-run)  DRY_RUN="1"; shift ;;
        *) echo "unknown argument: $1" >&2; exit 64 ;;
    esac
done

STAMP="$(date +%Y%m%d-%H%M)"
REPORT="$RUNS/report-$STAMP.md"
mkdir -p "$RUNS"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

# ---- preflight ---------------------------------------------------------
#
# Every check here is something that, if wrong, makes the entire run worthless
# rather than partially successful. Cheaper to refuse at 22:00 than to discover
# at 07:00 that nothing could ever have merged.

preflight() {
    local failed=""

    command -v claude >/dev/null 2>&1 || { echo "  - claude CLI not on PATH"; failed=1; }

    if [[ ! -x "$PYTHON" ]]; then
        echo "  - no interpreter at $PYTHON (create the venv first)"
        failed=1
    elif ! ( cd "$ROOT" && "$PYTHON" -m pytest -q >/dev/null 2>&1 ); then
        echo "  - test suite is already failing on $(git -C "$ROOT" branch --show-current)"
        echo "    a queue merged onto a broken base is not worth running"
        failed=1
    fi

    if [[ -z "${EDGAR_USER_AGENT:-}" ]]; then
        echo "  - EDGAR_USER_AGENT is unset; any task touching the network will 403"
        echo '    export EDGAR_USER_AGENT="Equity Research you@example.com"'
        failed=1
    fi

    if [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
        echo "  - working tree is dirty; commit or stash before an unattended run"
        failed=1
    fi

    if [[ ! -d "$QUEUE_DIR" ]]; then
        echo "  - queue directory not found: $QUEUE_DIR"
        failed=1
    fi

    [[ -z "$failed" ]]
}

log "Preflight"
if ! preflight; then
    log "Preflight failed — nothing dispatched."
    exit 78
fi
log "Preflight OK"

# ---- queue -------------------------------------------------------------

queue=()
for task in "$QUEUE_DIR"/*.md; do
    [[ -e "$task" ]] || continue
    # The queue's own README lives here; it is documentation, not a brief.
    [[ "$(basename "$task")" == "README.md" ]] && continue
    queue+=("$task")
done

if [[ ${#queue[@]} -eq 0 ]]; then
    log "Queue is empty; nothing to do."
    exit 0
fi

log "Queued ${#queue[@]} task(s), parallel=$PARALLEL, budget=\$$BUDGET_USD"

if [[ -n "$DRY_RUN" ]]; then
    for task in "${queue[@]}"; do
        echo "  would dispatch: $(basename "$task" .md)  <- $task"
    done
    exit 0
fi

# ---- helpers -----------------------------------------------------------

# Total spend across every result file this run has produced.
spend_so_far() {
    python3 - "$RUNS" <<'PY'
import glob, json, os, sys
total = 0.0
for path in glob.glob(os.path.join(sys.argv[1], "*.json")):
    try:
        with open(path) as fh:
            cost = json.load(fh).get("total_cost_usd")
    except Exception:
        continue
    if isinstance(cost, (int, float)):
        total += cost
print(f"{total:.4f}")
PY
}

over_budget() {
    python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) >= float(sys.argv[2]) else 1)' \
        "$(spend_so_far)" "$BUDGET_USD"
}

# done | failed | running, matching status.sh's reading of a result file.
worker_state() {
    local result="$RUNS/$1.json"
    [[ -s "$result" ]] || { echo running; return; }
    python3 - "$result" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        d = json.load(fh)
except Exception:
    print("running")           # still being written
    raise SystemExit
err = d.get("is_error") or d.get("subtype") not in (None, "success")
print("failed" if err else "done")
PY
}

# Background workers share this script's process group (job control is off in a
# non-interactive shell), so killing the group would take the scheduler with it.
# Walk the tree instead.
kill_tree() {
    local pid="$1" child
    for child in $(pgrep -P "$pid" 2>/dev/null || true); do
        kill_tree "$child"
    done
    kill -TERM "$pid" 2>/dev/null || true
}

kill_worker() {
    local pidfile="$RUNS/$1.pid"
    [[ -f "$pidfile" ]] || return 0
    kill_tree "$(cat "$pidfile")"
    rm -f "$pidfile"
}

# ---- dispatch / reap loop ---------------------------------------------

running=()
done_workers=()
failed_workers=()
merged_workers=()
unmerged_workers=()
skipped_tasks=()
next=0
halted=""

# `set -u` plus bash 3.2 errors on "${arr[@]}" when arr is empty.
expand() { eval "printf '%s\n' \"\${$1[@]+\${$1[@]}}\""; }

while [[ $next -lt ${#queue[@]} || ${#running[@]} -gt 0 ]]; do

    # Dispatch up to the parallelism cap.
    while [[ ${#running[@]} -lt $PARALLEL && $next -lt ${#queue[@]} && -z "$halted" ]]; do
        if over_budget; then
            log "Budget \$$BUDGET_USD reached (spent \$$(spend_so_far)); no further dispatch."
            halted="budget"
            break
        fi
        task="${queue[$next]}"
        worker="$(basename "$task" .md)"
        next=$((next + 1))
        log "Dispatch $worker"
        if "$ROOT/orchestrator/spawn.sh" "$worker" "$task" >/dev/null; then
            running+=("$worker")
        else
            log "  dispatch failed for $worker"
            failed_workers+=("$worker")
        fi
    done

    [[ ${#running[@]} -eq 0 ]] && break

    sleep "$POLL_SECONDS"

    # Reap. Integration is serial by nature — every merge touches the same HEAD.
    still=()
    for worker in $(expand running); do
        case "$(worker_state "$worker")" in
            running)
                still+=("$worker")
                ;;
            done)
                log "$worker finished; integrating"
                done_workers+=("$worker")
                if "$ROOT/orchestrator/integrate.sh" "$worker" >>"$RUNS/$worker.log" 2>&1; then
                    log "  merged $worker"
                    merged_workers+=("$worker")
                else
                    log "  NOT merged (tests failed or conflict); branch agent/$worker kept"
                    unmerged_workers+=("$worker")
                fi
                ;;
            failed)
                log "$worker failed; leaving branch agent/$worker for inspection"
                failed_workers+=("$worker")
                ;;
        esac
    done
    running=(${still[@]+"${still[@]}"})

    if [[ -z "$halted" ]] && over_budget; then
        log "Budget \$$BUDGET_USD exceeded; stopping in-flight workers."
        for worker in $(expand running); do
            kill_worker "$worker"
        done
        halted="budget"
    fi
done

# Anything never dispatched, because the budget ran out first.
while [[ $next -lt ${#queue[@]} ]]; do
    skipped_tasks+=("$(basename "${queue[$next]}" .md)")
    next=$((next + 1))
done

# ---- report ------------------------------------------------------------

section() {
    local title="$1" arr="$2" line
    printf '\n## %s\n\n' "$title" >> "$REPORT"
    local any=""
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        printf -- '- %s\n' "$line" >> "$REPORT"
        any=1
    done < <(expand "$arr")
    [[ -z "$any" ]] && printf -- '- none\n' >> "$REPORT"
    return 0
}

{
    echo "# Overnight run $STAMP"
    echo
    echo "- Queue: \`$QUEUE_DIR\` (${#queue[@]} task(s))"
    echo "- Spend: \$$(spend_so_far) of \$$BUDGET_USD budget"
    echo "- Halted early: ${halted:-no}"
} > "$REPORT"

section "Merged into $(git -C "$ROOT" branch --show-current)" merged_workers
section "Completed but NOT merged (tests failed or merge conflict)" unmerged_workers
section "Failed, timed out, or killed" failed_workers
section "Never dispatched" skipped_tasks

{
    printf '\n## Commits landed\n\n'
    printf '```\n'
    git -C "$ROOT" log --oneline --since="6 hours ago" || true
    printf '```\n'
    printf '\nPer-worker detail: `orchestrator/runs/<worker>.json` and `.log`.\n'
} >> "$REPORT"

log "Report written to $REPORT"
log "Spend: \$$(spend_so_far)"

# Non-zero if anything needs a human, so launchd surfaces it in the log.
[[ ${#unmerged_workers[@]} -eq 0 && ${#failed_workers[@]} -eq 0 && -z "$halted" ]]
