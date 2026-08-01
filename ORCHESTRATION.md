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
merging for exactly this reason. An agent reporting success is a claim, not evidence.

**Workers cannot push.** `--disallowedTools` blocks `git push`, `rm`, and `curl`.
Widen this only when you have a specific reason.

**Read the cost.** Every result JSON carries `total_cost_usd`. `status.sh` surfaces
it. A runaway worker is visible there before it is visible on your bill.
