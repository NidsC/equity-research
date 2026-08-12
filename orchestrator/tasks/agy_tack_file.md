# Task: peer comparison table
## Goal
Add a `peer_comps(tickers, years=5)` function to `src/equity_research/parse/financials.py`
that fetches XBRL financials for a list of tickers and returns a single DataFrame
with a MultiIndex (ticker, fiscal_year) for side-by-side comparison.
## Files you own
Modify:
- `src/equity_research/parse/financials.py`
- `tests/test_financials.py` (add tests for the new function)
Do not touch anything else.
## Requirements
1. Reuse `annual_financials()` internally — no new EDGAR calls.
2. Return a DataFrame with columns identical to `annual_financials()` output plus a `ticker` column.
3. Function must be importable from `equity_research.parse.financials`.
## Verification
`.venv/bin/python -m pytest tests/test_financials.py -q` passes.
`.venv/bin/ruff check src tests` returns no errors.
## Done means
Tests pass, work committed to your branch, summary states what was built
and any assumptions made about the DataFrame shape.
