# ER TO SENTINEL

The full paper trail of this project's redefinition, from "AI writes equity research memos"
to "a system that detects what changed between two filings."

Archived 2026-08-11 when the project was shelved. **The reframe was agreed and never built** —
see `STATE_AT_SHELVING.md`.

## Reading order

| # | Document | What it is |
|---|---|---|
| 1 | `STATE_AT_SHELVING.md` | **Start here.** What exists, what doesn't, measured baselines, the one untested assumption |
| 2 | `PLAN.md` | v1, agreed 2026-08-01. Killed "AI prose as the product"; inverted it to computed-data-public / model-analysis-paid. Carries the measured token and cost baselines |
| 3 | `MISSION.md` | v2, agreed 2026-08-09. Promotes the filing diff from cost optimisation to the mission. Extends `PLAN.md`, does not supersede it |
| 4 | `PROJECT_SENTINEL.md` | The full v2 spec: architecture, schema, six build phases, cost, kill criteria |
| 5 | `AI_TOOLING_REFERENCE.md` | Tooling lookup per phase. Written Aug 2026 against knowledge to ~May 2026 — treat every entry as a search starting point, not a settled fact |

## The three-line version

- **v0** — the model's prose was the product. Killed: scaled content, review capacity below what
  the economics needed, and annual 10-Ks that don't move with the news cycle.
- **v1** — invert it. The deterministic layer (XBRL, sections, diffs) goes public and indexed;
  model output goes behind the paywall. Right, and it stands.
- **v2** — the unit of value is not the company, it's **the filing pair**. Nobody wants a page
  about Microsoft; they want to be told Item 1A gained a paragraph on supplier concentration,
  with both versions of the sentence quoted.

## Notes on this folder

`PROJECT_SENTINEL.md` and `AI_TOOLING_REFERENCE.md` are snapshots copied from
`~/alpha/applied-ai/`, which is not a git repository. The originals remain there and may have
moved on since 2026-08-11.

Both documents reference `PROFILE_APPLIED_AI.md` and a `quiz-log/`. Those are deliberately not
in this public repo — they are a personal capability assessment and study log, and they stay
local in `~/alpha/applied-ai/`. Nothing in them is needed to restart the project.

## Constraints that survive the shelving

These are not preferences. They are the reason the output can be trusted at all, and they are
enforced in `.claude/CLAUDE.md`.

1. **Numbers never come from a language model.** Figures are computed in Python from XBRL facts.
   A model-generated figure is uncitable, and any code path where one reaches a report is a bug.
2. **Every claim traces to a filing section.** That is what the evidence fields on every analysis
   schema are for.
3. **All EDGAR traffic goes through `EdgarClient`.** The SEC ceiling is 10 req/s per IP with a
   mandatory descriptive User-Agent. The client throttles to 4 requests per 2 seconds and caches
   to disk. The 8 req/s tripwire inherits from `BaseException` on purpose — if it ever fires, the
   throttle has been bypassed, and that is the bug to fix rather than route around.
4. **Descriptive, never advisory.** Under FSMA, a personal recommendation on a security is a
   regulated activity. No price targets, no buy/sell/hold, no suitability language. Enforce it in
   the system prompt *and* assert it in the eval suite — it is a testable property.
