#!/usr/bin/env bash
#
# Report the state of every dispatched worker.
#
#   orchestrator/status.sh
#
# The manager agent polls this instead of tailing logs. Output is one line per
# worker: name, state, cost, and the first line of its summary.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
RUNS="$ROOT/orchestrator/runs"

shopt -s nullglob
results=("$RUNS"/*.json)

if [[ ${#results[@]} -eq 0 ]]; then
    echo "No workers dispatched."
    exit 0
fi

printf '%-22s %-10s %-9s %s\n' WORKER STATE COST SUMMARY
printf '%-22s %-10s %-9s %s\n' "----------------------" "----------" "---------" "-------"

for result in "${results[@]}"; do
    worker="$(basename "$result" .json)"
    branch="agent/$worker"

    if [[ ! -s "$result" ]]; then
        printf '%-22s %-10s %-9s %s\n' "$worker" "running" "-" "in progress"
        continue
    fi

    state="$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("running|-|output not yet valid JSON"); raise SystemExit
err = d.get("is_error") or d.get("subtype") not in (None, "success")
cost = d.get("total_cost_usd")
summary = (d.get("result") or "").strip().splitlines()
print("|".join([
    "failed" if err else "done",
    f"${cost:.2f}" if isinstance(cost, (int, float)) else "-",
    summary[0][:60] if summary else "",
]))' "$result")"

    IFS='|' read -r st cost summary <<< "$state"
    ahead="$(git -C "$ROOT" rev-list --count "HEAD..$branch" 2>/dev/null || echo 0)"
    [[ "$ahead" != "0" ]] && summary="[$ahead commits] $summary"
    printf '%-22s %-10s %-9s %s\n' "$worker" "$st" "$cost" "$summary"
done
