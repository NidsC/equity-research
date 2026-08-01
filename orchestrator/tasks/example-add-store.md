# Task: persistent DuckDB store for filings and financials

## Goal

Add a persistence layer so repeat research runs read from a local store instead of
re-parsing filings.

## Files you own

Create:
- `src/equity_research/store/db.py`
- `tests/test_store.py`

Modify:
- `src/equity_research/store/__init__.py` (exports only)

Do not touch anything under `ingest/`, `parse/`, `analysis/`, or `report/`. Another
worker is editing the parser. If you need a change there, say so in your summary
instead of making it.

## Requirements

1. A `Store` class wrapping DuckDB at a configurable path (default `data/er.duckdb`).
2. Three tables, created idempotently on open:
   - `filings(cik, accession, form, filing_date, report_date, document_url)` — PK
     `(cik, accession)`
   - `financials(cik, fiscal_year, line_item, value)` — PK `(cik, fiscal_year, line_item)`
   - `sections(cik, accession, item, body)` — PK `(cik, accession, item)`
3. `upsert_filings`, `upsert_financials`, `upsert_sections` — idempotent, safe to
   call twice with the same data.
4. `get_financials(cik) -> pandas.DataFrame` returning the same wide shape that
   `parse.financials.annual_financials` produces, so it is a drop-in substitute.
5. Context manager support (`with Store() as store:`).

## Verification

`python3 -m pytest tests/test_store.py -q` passes. Tests must use a temporary
database via `tmp_path`, never the real `data/er.duckdb`, and must not hit the
network.

## Done means

Tests pass, work is committed to your branch, and your final summary states what
you built, what you verified, and any assumption you made about the financials
DataFrame shape that the parser owner should confirm.
