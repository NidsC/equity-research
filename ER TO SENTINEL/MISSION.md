# Mission

**Detect and explain what changed in a company's filings — with every number computed from XBRL
and every claim quoted from source text.**

Not "AI equity research." Not memo generation. **Change detection.**

Agreed 2026-08-09. Extends `PLAN.md` (2026-08-01); does not supersede it. The full product and
learning spec lives alongside this file in `PROJECT_SENTINEL.md` (codename SENTINEL).

---

## The lineage

Three versions of the mission, each fixing the one before.

### v0 — "AI writes research memos"
The model's prose was the product. `PLAN.md` killed this and named the three reasons: mass-produced
model prose is the canonical scaled-content pattern and search was the whole distribution plan;
review capacity caps far below the 10/day the economics needed; and annual 10-Ks do not move with
the news cycle the traffic strategy depended on.

Root cause, in `PLAN.md`'s own words: *treating AI prose as the product.*

### v1 — "computed data public, model analysis paid"
`PLAN.md`'s inversion. The deterministic layer — XBRL financials, extracted sections, year-over-year
diffs — becomes the public indexed surface. Model output moves behind the paywall as the thing
subscribers buy. This was right and stands.

But it still framed the artifact as **a page about a company**, generated on demand, one shot.

### v2 — "the change event is the product"
The unit of value is not the company and not the memo. It is **the filing pair**: this 10-K against
last year's, and the specific set of things that moved.

Nobody wants a page about Microsoft. They want to be told that Item 1A gained a paragraph on
supplier concentration, and to see both versions of the sentence.

---

## Why this was already the answer, unrecognised

`PLAN.md` found the diff and then filed it under cost optimisation. Read build step 1 again:

> **Item 1A structural diff** — the single largest lever, and it serves cost and distribution at
> once: it cuts input 45–55% *and* produces the artifact that makes the best free content.

Two things were already known and measured:

| Evidence | Source | What it means |
|---|---|---|
| Item 1A text changed YoY: **33.1%** MSFT, **40.8%** AAPL | `PLAN.md` measured baseline | Two-thirds of the risk section is unchanged boilerplate. All the signal is in the third that moved |
| `risk_delta` = **37.6K of 65K input tokens (58%)** | `PLAN.md` token breakdown | The system already spends the majority of its money on change detection — and then ships a memo |

So the machine is already mostly a change detector wearing a memo as a costume. The reframe is a
**promotion, not a rewrite**: take the diff from being an input optimisation with a pleasant
by-product, and make it the mission.

---

## What the reframe fixes that v1 didn't

**The news-cycle problem.** `PLAN.md` correctly identified that annual 10-Ks don't move with the
news cycle, then built a plan whose primary artifact is still annual. A change-event product is
event-shaped by construction: 10-Qs land quarterly, 8-Ks land constantly. The trigger stops being
"a user asked" and becomes "a filing landed."

**The defensibility problem.** "AI summarises filings" is a saturated claim every incumbent makes.
"Here are the eleven things that changed, ranked by materiality, with before-and-after quoted" is
narrower, harder to hand-wave, and obviously useful to someone already holding the position.

**The gradeability problem.** A research memo is close to impossible to evaluate objectively — good
and plausible look identical. A change-detection claim is gradable against two documents that both
sit on disk. Ground truth exists, which means an eval suite is possible, which means quality becomes
a number rather than an opinion. This is the single biggest engineering consequence of the reframe.

**The review-capacity problem.** Reviewing a 2,000-word memo is slow. Reviewing "is this flagged
change material, yes or no" is fast. The human gate stops being the bottleneck `PLAN.md` correctly
identified it as.

---

## What does not change

Preserved deliberately. These were right and the reframe makes two of them more load-bearing:

- **Numbers never come from a language model.** Computed in Python from XBRL. Now more important:
  a change-detection product lives entirely on being trusted about specifics.
- **Every claim traces to a filing section.** Evidence fields on every schema.
- **All EDGAR traffic through `EdgarClient`.** Rate limits, tripwire, cache. Untouched.
- **Public computed layer / paid model layer.** Unchanged, and the reframe sharpens where the line
  falls: *the diff is deterministic, so it can be public. The materiality judgement is model output,
  so it is paid.* That is a cleaner boundary than "financials free, analysis paid," because it maps
  exactly onto what the model did or didn't touch.

---

## What changes concretely

| | v1 (`PLAN.md`) | v2 (this document) |
|---|---|---|
| Unit of work | Company | Filing pair — a change event |
| Trigger | `er research TICKER` on demand | A filing lands; the system notices |
| State | None — one-shot CLI | Persistent per-document job state, resumable |
| Primary artifact | Memo | Ranked, quoted, reviewed change set |
| First milestone | S&P 500 backfill | 10-company watchlist that emails **you** weekly |
| Quality measure | Editorial judgement | Precision/recall against hand-labelled filing pairs |

The state row is the real architectural change. A one-shot CLI can afford to have no memory; a
monitor polling companies on a schedule cannot. Job status, retry counts, idempotency and
resume-from-checkpoint become mandatory — and that machinery is the least exercised part of this
codebase, which is why SENTINEL builds it first and without any model involved at all.

---

## Build order, revised against `PLAN.md`

| `PLAN.md` step | Status under v2 |
|---|---|
| 1. Item 1A structural diff | **Unchanged and now central.** Still the first thing to build |
| 2. Review checkpoint | **Reframed.** Time the review of a *change set*, not a memo. Faster, so the cadence answer will differ |
| 3. Gzip the cache | Unchanged. Do it whenever |
| 4. Structured store | **Promoted — now step 2.** A monitor needs persistence from the first run. Add the `document_job` state table alongside the `analysis` table the brief already calls for |
| 5. Public data pages | **Demoted.** Distribution work. Not until something is worth distributing |
| 6. Paid analysis layer / S&P 500 backfill | **Demoted.** A separate bet from the product bet. See below |

Extend the diff beyond Item 1A once it works: MD&A, accounting policy notes, segment definitions
and litigation disclosure are all high-signal on change and near-worthless read cold.

---

## Reality checks

**The reframe narrows the wedge; it doesn't create a market.** AlphaSense and Bloomberg own the
institutional end, Koyfin and Fiscal.ai the retail end. The plausible audience is the serious
individual running 10–30 positions who reads filings but hasn't time to diff them. That's real and
too small for incumbents to bother with. It is not a large market and shouldn't be described as one.

**One assumption is untested and load-bearing: is a 10-Q diff worth an alert?** The 33–41% YoY
change figure is measured on *annual* Item 1A. Quarterly filings are shorter and change less.
If a typical 10-Q diff produces nothing material, the event cadence collapses back to annual and
the news-cycle fix evaporates. **Test this on five companies before building any distribution
layer.** It's a day's work and it gates the entire commercial thesis.

**Don't backfill 500 companies until someone reads the digest.** The backfill is a distribution bet
costing ~$70–200. The product bet costs pennies at ten companies. Settle the product bet first.

**Regulatory line, before any subscriber exists.** Descriptive, never advisory. "The risk factors
added a paragraph on supplier concentration" is description; "this makes the shares less attractive"
is a personal recommendation on a security, which is a regulated activity under FSMA. No price
targets, no buy/sell/hold, no suitability language. Enforce it in the system prompt *and* assert it
in the eval suite — "does the output contain advisory language" is a testable property, so make it
a test.

---

## Corrections to older notes

- **Cost is ~$0.40/memo**, not $0.85. The earlier figure came from an input estimate roughly 2× too
  high. `PLAN.md` measured it.
- **The prompt-caching restructure is rejected, not pending.** The four passes receive disjoint
  slices, so a shared dossier prefix would *increase* billed tokens ~50%. Only a fixed per-pass brief
  is worth caching. Any note describing a "~61% token cut via prompt caching" is stale. *If the pass
  structure changes under v2 — e.g. several questions asked against one shared diff — revisit the
  arithmetic before assuming either way.*

---

## Related

| Document | Contents |
|---|---|
| `PLAN.md` | The v1 plan. Measured baselines, build steps, the "not doing" list. Still the reference for anything not contradicted here |
| `../.claude/CLAUDE.md` | Non-negotiables for workers. Unchanged by this reframe |
| `PROJECT_SENTINEL.md` | Full v2 spec: architecture, schema, six build phases, cost, kill criteria |
| `AI_TOOLING_REFERENCE.md` | Tooling lookup for each phase |
| `STATE_AT_SHELVING.md` | What was actually built before the project was shelved |
