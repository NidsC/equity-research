# Plan: S&P 500 research site — data public, analysis paid

**Status:** agreed 2026-08-01. Supersedes the ad-hoc backlog in the project notes.
Figures here are measured from the local cache unless marked as estimates.

## Context

The platform ingests SEC EDGAR filings, computes financials from XBRL in Python,
and runs four narrow Claude passes over verified inputs. The original plan was to
publish AI-written analysis of ~1,000s of companies as the SEO surface, generated
via a Claude Max seat at ~10/day.

Three problems made that unworkable: mass-produced model prose is the canonical
scaled-content pattern and search exposure was the entire distribution plan;
review capacity caps out far below 10/day, and unreviewed output forfeits the
quality claim that justifies a subscription; and annual 10-Ks do not move with
the news cycle the traffic strategy depended on.

All three trace to one cause — treating AI prose as the product. The fix is to
invert it: the **computed** layer (XBRL financials, extracted sections,
deterministic year-over-year diffs) becomes the public, indexed surface, and the
model output moves behind the paywall as the thing subscribers buy. Scope is the
S&P 500.

## Measured baseline

From the local cache (AAPL + MSFT). Token figures are char/4 estimates and likely
*under*-count — filings are dense with numerals and tables, which tokenize less
efficiently than prose. Re-baseline with `messages.count_tokens` before relying
on them.

| | MSFT | AAPL |
|---|---:|---:|
| 10-K primary document as served | 8.59 MB | 1.52 MB |
| Of which is markup | 95.8% | 85.4% |
| Input tokens, all 4 passes | ~65K | ~46K |
| Cached bytes / gzipped | 21.8 / ~1.2 MB | 7.0 / ~0.5 MB |
| Item 1A text changed YoY | 33.1% | 40.8% |

**Where the tokens are (MSFT):** risk_delta 37.6K (58%), mda 14.7K,
business_model 10.8K, earnings_quality 1.8K.

**Cost:** ~$0.40/memo at Opus 5 rates. S&P 500 backfill ~$200 today, ~$70–140
after the diff plus Batch API. Storage: 7.4 GB raw, 0.45 GB gzipped.

Neither cost nor storage is a binding constraint at this scale — review capacity
is. Note ~$0.40/memo supersedes the ~$0.85 figure in earlier notes, which derived
from an input estimate roughly 2× too high.

## Architecture: three layers

**Public, indexed, no model involved.** One page per company: financials, derived
ratios, ten-year trends, and what changed in the risk factors since last year.
All computed in Python. Not scaled content because nothing is generated. Can be
statically generated — the data only changes when a filing lands — so it is cheap
to host and fast to serve.

**Public, editorial, human-reviewed.** Short write-ups published when a company
files. Cadence set by the checkpoint in step 2, not assumed.

**Paid, behind login.** The four analysis passes for all 500 companies, plus
filing alerts. Not indexed, so it never touches search policy, and it is
delivered as a service to subscribers rather than published as content.

## Build order

### 1. Item 1A structural diff

The single largest lever, and it serves cost and distribution at once: it cuts
input 45–55% *and* produces the artifact that makes the best free content.

- `parse/sections.py` — add a diff function over two Item 1A bodies using
  `difflib.SequenceMatcher` at word granularity, returning changed hunks with
  surrounding context plus counts of added/removed/reworded material. Reuse the
  existing `html_to_text` / `extract_sections` output; no new parsing.
- `pipeline.py` — compute it inside `build_dossier` (the deterministic phase,
  which must complete before any model runs) and carry it on `CompanyDossier`
  as a new field alongside `item_1a` / `item_1a_prior`.
- `analysis/passes.py` — `risk_delta` takes the diff instead of two full
  sections. `RISK_DELTA_SCHEMA` is unchanged; evidence still traces to Item 1A,
  since the diff is derived deterministically from the two filings.

Keep the raw sections on the dossier — the diff is what the model sees, but the
full text is what the public page cites.

### 2. Review checkpoint — before committing to any cadence

Generate three memos across different sizes (one mega-cap, one mid, one financial
with a long risk section). Time how long a genuine review takes. Set the
editorial cadence and the publishing model from that measurement.

Cost: ~$1. This exists because the publishing cadence is currently a guess, and
everything downstream depends on it.

### 3. Gzip the cache layer

`ingest/edgar.py` — compress in `EdgarClient.get` / `_cache_path`. 16.4×
reduction, transparent to callers. Must stay compatible with the existing
uncompressed cache or migrate it cleanly. Do not discard raw filings: retention
is what allows re-deriving when the parser improves, without an EDGAR round trip.

### 4. Structured store

Follow the existing brief at `orchestrator/tasks/example-add-store.md`, with one
amendment: it specifies `filings` / `financials` / `sections`, and the paid layer
also needs an `analysis` table holding **structured pass output with its evidence
fields** — not rendered markdown. `report/memo.py` then becomes one renderer over
stored data rather than the only artifact, which keeps the presentation layer
replaceable.

### 5. Public data pages

Static generation over the store: financials, ratios, and a risk-diff summary per
company. No model output on these pages. Reuse `parse.financials.derived_metrics`
and the shaping in `to_markdown_table`, rendering to HTML rather than markdown.

### 6. Paid analysis layer

Move generation to the API (Max stays for development and research). Unlocks the
Batch API for the backfill at 50% off and `output_config.effort` for per-pass
cost control, neither of which the CLI exposes well. Backfill 500 companies
unattended via `orchestrator/overnight.sh`.

## Not doing, and why

- **Restricting financials to 3 years** — saves ~3% of tokens and discards the
  cheapest, most valuable data in the dossier. The financials table is 3,536
  tokens at 10 years against ~65K total; token cost is narrative, not numeric.
- **Discarding raw filings after extraction** — gzip makes retention nearly free,
  and re-fetching costs an EDGAR round trip that cannot be cheaply repeated.
- **Prompt-caching the dossier** — the four passes receive disjoint slices, so a
  shared prefix would *increase* billed tokens ~50%. Only a fixed per-pass brief
  is worth caching, and only inside the TTL during a continuous backfill.
- **Publishing AI prose as the SEO surface** — the root cause above.

## Verification

- Re-baseline both tickers with `messages.count_tokens` against `claude-opus-5`;
  confirm the 46–65K figures before claiming any reduction.
- After the diff: `.venv/bin/python -m pytest -q` passes with new tests covering
  a filing with no material change, one with a wholly new risk, and one with a
  dropped risk. `er research MSFT` must still name specific new and dropped risks
  with evidence pointing at Item 1A.
- Compare summed `total_cost_usd` across the four passes for the same ticker
  before and after, to measure the realised saving rather than the predicted one.
- After gzip: confirm cache hits still short-circuit the network and that the
  existing cache is readable or migrated without re-fetching.
- Confirm no public page renders model-generated prose — the separation is this
  plan's main safeguard and should be enforced by a test, not by convention.
