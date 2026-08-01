# Orchestration: Antigravity as manager, Claude CLI as workers

## How the two systems actually connect

Antigravity's Agent Manager spawns and monitors *its own* agents. It has no
built-in concept of a Claude CLI worker. The bridge is that Antigravity agents can
run shell commands, gated by an allowlist — so the manager agent shells out to
`orchestrator/spawn.sh`, which runs `claude -p` in headless mode.

```
┌─ Antigravity Agent Manager ────────────────────────────┐
│  manager agent (Gemini)                                │
│    reads BACKLOG, decomposes into tasks                │
│    writes orchestrator/tasks/<worker>.md               │
│    runs orchestrator/spawn.sh <worker> <task>  ────────┼──┐
│    polls orchestrator/status.sh                        │  │
│    runs orchestrator/integrate.sh <worker>             │  │
└────────────────────────────────────────────────────────┘  │
                                                            │
   ┌────────────────────────────────────────────────────────┘
   ▼
┌─ claude -p (headless) ─────────────────────────────────┐
│  cwd: .worktrees/<worker>   branch: agent/<worker>     │
│  --output-format json  --permission-mode acceptEdits   │
│  --allowedTools "Read,Write,Edit,Bash(pytest:*),..."   │
│  result JSON -> orchestrator/runs/<worker>.json        │
└────────────────────────────────────────────────────────┘
```

Worktrees are what make parallelism safe. Three Claude instances in one directory
will overwrite each other's edits and corrupt the git index. One worktree per
worker, merged through branches, and they cannot interfere.

## Setup, once

1. **Install both CLIs.** `claude --version` and the Antigravity CLI must both work.

2. **Grant Antigravity permission to run the dispatch scripts.** Merge
   `config/antigravity-settings.example.json` into
   `~/.gemini/antigravity-cli/settings.json`.

   The important part is `enableTerminalSandbox: false`. Antigravity's terminal
   sandbox blocks outbound network requests from agent-run commands, and Claude
   CLI needs the network. If you leave the sandbox on, workers hang with no useful
   error. This is the single most likely thing to break your first run.

3. **Set your EDGAR identity.** The SEC requires a descriptive User-Agent with
   real contact details — requests without one get a 403:

   ```bash
   export EDGAR_USER_AGENT="Equity Research you@example.com"
   ```

   Keep your actual address in the environment (a shell profile or `.env`), not
   in a tracked file. If this repo ever goes public, a committed email address
   is a permanent gift to address scrapers.

4. **Optional — expose Claude Code over MCP.** `.agents/mcp_config.json` registers
   `claude mcp serve`, which gives Antigravity direct access to Claude's Read/Write/
   Bash tools. Note this exposes Claude's *tools*, not Claude's *agent loop*: the
   thinking still happens in Antigravity's model. Use `spawn.sh` when you want a
   worker that reasons independently; use MCP when you just want the tools.

## The manager's loop

```bash
# 1. Write a task file describing one unit of work
#    orchestrator/tasks/duckdb-store.md

# 2. Dispatch — returns immediately, worker runs in background
orchestrator/spawn.sh duckdb-store orchestrator/tasks/duckdb-store.md

# 3. Dispatch more workers on non-overlapping files
orchestrator/spawn.sh peer-comps orchestrator/tasks/peer-comps.md

# 4. Poll
orchestrator/status.sh

# 5. Integrate — runs tests first, refuses to merge a broken branch
orchestrator/integrate.sh duckdb-store
```

## Unattended mode: `overnight.sh`

The manager loop above needs someone watching it. For a queue of tasks that are
already written, `orchestrator/overnight.sh` runs the same dispatch → poll →
integrate cycle on a schedule, with no model in the driver's seat:

```bash
# Drop task files in orchestrator/tasks/queue/, then:
orchestrator/overnight.sh --dry-run            # what would be dispatched
orchestrator/overnight.sh --budget 20 --parallel 3
```

Install `config/com.equity-research.overnight.plist.example` as a LaunchAgent to
fire it nightly. The header of that file has the install steps.

A scheduler rather than a manager agent, because the two jobs are different: a
model is worth paying for when tasks need decomposing, and is a liability at 3am
when it might decide to try something clever. Decompose in the evening while you
are awake; let the scheduler execute.

### What bounds it

Nothing is supervised while it runs, so every loop is bounded independently:

| Bound | Default | Set by |
|---|---|---|
| Per-worker wall clock | 1800s | `ER_WORKER_TIMEOUT` / `--timeout` |
| Per-worker turns | 60 | `ER_WORKER_MAX_TURNS` |
| Total spend | $20 | `--budget` |
| Concurrent workers | 3 | `--parallel` |

Budget is checked before each dispatch and after each poll. On breach, in-flight
workers are killed and the rest of the queue is left undispatched and reported.

It is a dispatch gate, not a hard cap: a worker is only started while spend is
*under* the ceiling, so the final total can exceed it by roughly one worker's
cost. Set the budget to the most you are willing to wake up to, not to the exact
number. Cost is also only knowable once a worker finishes — `total_cost_usd`
arrives with its result — so a worker killed mid-flight contributes whatever it
had already streamed, or nothing if that output was truncated.

### Preflight refuses more than it accepts

The run aborts before dispatching anything if the tests already fail on the
current branch, `.venv/bin/python` is missing, `EDGAR_USER_AGENT` is unset, the
working tree is dirty, or the queue directory does not exist. Each of those makes
the entire run worthless rather than partially useful — a queue merged onto a
broken base tells you nothing, and it is cheaper to refuse at 22:00 than to find
out at 07:00.

### In the morning

`orchestrator/runs/report-<stamp>.md` lists what merged, what completed but was
refused (tests failed or merge conflict), what died, what never ran, and the
total spend. The exit status is non-zero if anything needs you, so it shows up in
the launchd log. Branches for unmerged work are kept — `agent/<worker>` is still
there to inspect.

### Two things that will bite you

**A LaunchAgent only fires while you are logged in, and a sleeping Mac does not
run it.** If the machine sleeps at 22:00 the job runs whenever it next wakes. To
hold it awake for the window:

```bash
caffeinate -s -t 28800 &     # 8 hours, and only while on AC power
```

**EDGAR pacing is shared, so parallelism costs throughput.** `EdgarClient` gates
every request through a lock file in the cache directory (`.edgar.lock`), so
three workers fetching at once still pace to 2 requests/second in aggregate
rather than 2/s each. This is deliberate — see the note below — but it means
network-bound tasks do not speed up with `--parallel`. Code tasks working off the
existing cache are unaffected.

## Writing task files

A task file is the worker's entire brief; it cannot ask you a follow-up question.
Bad task files are the main cause of wasted worker runs. Each one should state:

- **The goal** in one sentence.
- **Which files to touch** — explicitly, and which to leave alone.
- **How to verify** — the exact test command that must pass.
- **What "done" means** — the acceptance criteria.

See `orchestrator/tasks/example-add-store.md` for the shape.

## Rules that keep this from going wrong

**Partition by file, not by feature.** Two workers told to "improve the parser"
will collide. One on `parse/financials.py` and one on `parse/sections.py` will not.

**Cap concurrency at three or four.** Each worker is a full agent burning tokens.
More than four and you spend more time reviewing merges than the parallelism saved.

**Never merge on the worker's say-so.** `integrate.sh` runs the test suite before
merging for exactly this reason. An agent reporting success is a claim, not
evidence. It also fails *closed*: if the worktree is missing and the branch
cannot be verified, it refuses rather than merging unverified work.

**Use `.venv/bin/python`, never bare `python3`.** Both `integrate.sh` and the
worker instructions in `.claude/CLAUDE.md` name the venv interpreter explicitly.
`python3` is whatever is first on PATH — on a machine with Anaconda ahead of it,
that interpreter has pytest but not this project's dependencies, so the suite
dies during collection and every merge is refused for a reason unrelated to the
worker's changes. Unattended, that silently wedges the whole queue.

**EDGAR pacing is per-cache-directory, not per-process.** The token bucket in
`ingest/edgar.py` is a module global, so it bounds one interpreter; N workers
would otherwise pace to 2/s each and put 2N/s on one IP against SEC's 10/s
ceiling, with every per-process tripwire seeing only its own share and never
firing. `_CrossProcessGate` moves the grant ledger into `.edgar.lock` under the
cache directory so both the bucket and the tripwire measure what SEC sees.

**Workers cannot push.** `--disallowedTools` blocks `git push`, `rm`, and `curl`.
Widen this only when you have a specific reason.

**Read the cost.** Every result JSON carries `total_cost_usd`. `status.sh` surfaces
it. A runaway worker is visible there before it is visible on your bill.
