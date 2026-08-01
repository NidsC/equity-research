# equity-research

AI equity research over SEC filings. Financials come from XBRL and are computed
in Python; language models read narrative sections only and never produce a
number that reaches a report.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# The SEC requires a descriptive User-Agent identifying you.
export EDGAR_USER_AGENT="Equity Research you@example.com"
```

## Use

```bash
er facts AAPL              # verified financials + ratios, no model calls
er sections AAPL           # narrative sections located in the latest 10-K
er research AAPL -o memo.md   # full memo (runs Claude analysis passes)
```

`facts` and `sections` are free and offline-after-first-fetch. Only `research`
spends tokens.

## How it works

```
EDGAR ──► XBRL company facts ──► normalized table ──► ratios     (Python, 0 tokens)
     └──► 10-K HTML ──────────► Item 1 / 1A / 7 ────┐
                                                    ▼
                              4 analysis passes (Claude, headless, tools denied)
                                                    │
                                                    ▼
                                              research memo
```

The four passes are business model and moat, risk-factor delta year over year,
earnings quality, and MD&A narrative versus reported figures. Each returns
schema-validated JSON with evidence fields, so every claim in the memo traces
back to a filing section or a computed metric.

## EDGAR access rules

Free, no API key. Two hard constraints, both handled by `EdgarClient`:

- A descriptive `User-Agent` with contact details is mandatory (403 without it).
- 10 requests/second per IP is the ceiling. We run at 4 requests per 2 seconds
  and abort the process outright if 8/s is ever observed.

Every response is cached to `data/cache/`. Filings are immutable once filed, so
the cache is safe indefinitely.

## Orchestration

`ORCHESTRATION.md` covers the Antigravity-as-manager setup: dispatching Claude
CLI workers into isolated git worktrees, polling their status, and merging only
after tests pass.

## Layout

| Path | Contents |
|---|---|
| `src/equity_research/ingest/` | EDGAR client, rate limiting, caching |
| `src/equity_research/parse/` | XBRL normalization, 10-K section extraction |
| `src/equity_research/analysis/` | Prompts, schemas, headless Claude runner |
| `src/equity_research/report/` | Memo rendering |
| `orchestrator/` | Manager dispatch scripts |

## Tests

```bash
.venv/bin/python -m pytest -q      # 23 tests, fully offline
.venv/bin/ruff check src tests
```
