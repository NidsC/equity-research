# State at shelving — 2026-08-11

What exists, what doesn't, measured rather than remembered. Written the day the project was
put down so that nothing has to be reconstructed from memory later.

**Headline: SENTINEL is specification only. No SENTINEL code was ever written.**

The repo contains the v1 memo generator, complete and passing. The v2 reframe
(`MISSION.md`, `PROJECT_SENTINEL.md`) was agreed on 2026-08-09 and shelved on 2026-08-11
before a single line was implemented.

---

## What is built and working

`.venv/bin/python -m pytest -q` → **29 passed**, verified 2026-08-11.

| Module | LOC | What it does |
|---|---:|---|
| `ingest/edgar.py` | 415 | EDGAR client. Token bucket at 4 req/2s, tripwire latching at 8 req/s, disk cache, mandatory User-Agent |
| `analysis/passes.py` | 216 | Four schema-enforced passes: `business_model`, `risk_delta`, `earnings_quality`, `mda_vs_numbers` |
| `parse/financials.py` | 208 | XBRL → `annual_financials`, `derived_metrics` |
| `report/memo.py` | 178 | Markdown memo renderer |
| `parse/sections.py` | 136 | `html_to_text`, `split_items`, `extract_sections` |
| `analysis/runner.py` | 121 | Headless Claude CLI runner — `--allowedTools ""` tool denial, timeouts, per-call cost capture |
| `pipeline.py` | 117 | `build_dossier` → `run_analysis` → `research` |
| `cli.py` | 73 | `er research TICKER` |
| `orchestrator/` | — | Unattended overnight dispatch, worker budget ledger |
| `tests/` | 412 | 29 tests across sections, financials, rate limiting |

Total application code: **1,879 LOC**.

## What is not built

Every build step in `PLAN.md` and every phase in `PROJECT_SENTINEL.md` is unstarted.

| Item | Source | Status |
|---|---|---|
| **Item 1A structural diff** | `PLAN.md` step 1 | **Not built.** `sections.py` imports no `difflib`. `risk_delta()` still takes two *full* Item 1A bodies |
| Review checkpoint (time a real review) | `PLAN.md` step 2 | Never run |
| Gzip the cache layer | `PLAN.md` step 3 | Not done |
| Structured store | `PLAN.md` step 4 | `store/__init__.py` exists and is **0 bytes** |
| Public data pages | `PLAN.md` step 5 | Not started |
| Paid analysis layer / S&P 500 backfill | `PLAN.md` step 6 | Not started |
| Phase 1 — `document_job` state machine, EDGAR polling, watchlist | SENTINEL | **Nothing.** No table, no poller, no watchlist |
| Phase 2 — diff, triage, weekly digest | SENTINEL | Nothing |
| Phase 3 — pgvector, chunking, hybrid search, chat | SENTINEL | Nothing |
| Phase 4 — 30 hand-labelled pairs, eval suite | SENTINEL | Nothing |
| Phase 5 — tracing, cost, latency | SENTINEL | Nothing |
| Phase 6 — MCP server | SENTINEL | Nothing |

The dossier still carries `item_1a` and `item_1a_prior` as full text. That is the exact seam
the diff was to be inserted at — see `PLAN.md` step 1 for the three-file change.

## Measurements worth keeping

These cost real tokens to obtain. Do not re-derive them.

- Item 1A text changed year over year: **33.1% MSFT, 40.8% AAPL** (annual only)
- `risk_delta` consumes **37.6K of 65K input tokens — 58%** of the run
- **~$0.40 per memo** at Opus 5 rates. The older ~$0.85 figure is wrong; it came from an
  input estimate roughly 2× too high
- MSFT 10-K as served: 8.59 MB, **95.8% markup**. AAPL: 1.52 MB, 85.4% markup
- Cache: 7.4 GB raw / 0.45 GB gzipped at S&P 500 scale — **16.4× reduction**

## The question that gates the whole thesis

**Is a 10-Q diff worth an alert?** Untested, load-bearing, roughly a day's work on five companies.

The 33–41% change figure is measured on *annual* Item 1A. Quarterly filings are shorter and change
less. If a typical 10-Q diff yields nothing material, the event cadence collapses back to annual,
the news-cycle argument for SENTINEL evaporates, and v2 loses its main advantage over v1.

Answer this before building any distribution layer. It is the cheapest possible test of the
most expensive assumption.

## Rejected, with reasons — do not revisit

- **Prompt-caching the dossier.** The four passes receive disjoint slices, so a shared prefix
  would *increase* billed tokens ~50%. Only a fixed per-pass brief is worth caching. Any note
  claiming a "~61% token cut via prompt caching" is stale. Revisit the arithmetic only if the
  pass structure changes — e.g. several questions asked against one shared diff.
- **Restricting financials to 3 years.** Saves ~3% of tokens, discards the cheapest and most
  valuable data. Token cost is narrative, not numeric.
- **Discarding raw filings after extraction.** Gzip makes retention nearly free; re-fetching
  costs an EDGAR round trip that cannot be cheaply repeated.
- **Publishing AI prose as the SEO surface.** The root cause that killed v0.

## Local state destroyed on shelving

- **EDGAR cache** — 10 files, AAPL + MSFT only, ~28 MB. Regenerates on first run.
- **`.venv`** — 226 MB. Rebuild per the tested sequence in `../SENTINEL_SHELVED.md`; note it
  needs Python 3.12 explicitly and a pip upgrade before the editable install.

Nothing else was lost. All source and history is on GitHub.
