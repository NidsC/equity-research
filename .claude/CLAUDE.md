# Working rules for this repo

You are one of several Claude workers dispatched by an Antigravity manager agent.
You are working in a git worktree on branch `agent/<your-name>`. Other workers are
editing other parts of this repo at the same time.

## Non-negotiables

**Numbers never come from a language model.** Financial figures are computed in
Python from XBRL facts. If you are writing analysis code, your job is to hand the
model a verified table and forbid it from doing arithmetic. Any code path where a
model produces a figure that reaches a report is a bug.

**Every claim in a memo traces to a filing section.** Analysis schemas carry
evidence fields for this reason. Do not add a research output that cannot be
attributed back to source text or a computed metric.

**All EDGAR traffic goes through `EdgarClient`.** No exceptions — not a bare
`httpx.get`, not a `curl`, not a "quick test script". The SEC ceiling is 10
requests/second per IP and a descriptive `User-Agent` is mandatory;
`src/equity_research/ingest/edgar.py` throttles to 4 requests per 2 seconds and
caches every response to disk.

There is a tripwire at 8 observed requests/second that latches permanently and
kills the run. The token bucket makes 8/s unreachable, so **if it fires, the
throttle has been bypassed** — that is the bug to go fix, not an inconvenience
to route around. `RateLimitTripwire` inherits from `BaseException` on purpose:
do not catch it, do not add it to an `except` clause, do not call
`_limiter.reset()` outside tests.

## Scope discipline

Stay inside the files your task names. If you find a real problem elsewhere, note
it in your final summary rather than fixing it — another worker may be mid-edit in
that file, and a merge conflict costs the manager more than the fix saves.

## Before you finish

1. `.venv/bin/python -m pytest -q` must pass.

   Use that interpreter, not a bare `python3`. `python3` resolves to whatever is
   first on PATH — often a system or Anaconda build without this project's
   dependencies, where the suite dies during collection on a missing import. That
   failure is not yours; do not try to fix it by adding dependencies or editing
   imports. If `.venv/bin/python` is missing, say so and stop.

2. Commit your work with a clear message. Do not push.
3. Your final message is read by the manager agent, not a human. Make it a terse
   status report: what you changed, what you verified, what you deliberately left
   alone, and anything the manager needs to decide.

## Layout

- `src/equity_research/ingest/` — EDGAR client, rate limiting, caching
- `src/equity_research/parse/` — XBRL normalization, 10-K section extraction
- `src/equity_research/analysis/` — prompts, schemas, headless Claude runner
- `src/equity_research/report/` — memo rendering
- `orchestrator/` — the manager's dispatch scripts. Do not edit unless told to.
