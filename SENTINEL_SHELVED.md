# Shelved — 2026-08-11

## What happened

Built a working memo generator over SEC filings (1,879 LOC, 29 tests green). Then decided the
memo was the wrong product: the real unit of value is **the filing pair** — what changed between
this 10-K and last year's, ranked, quoted, traceable. That reframe is codenamed SENTINEL.

**It was specified in full and never built.** Not one line. See `ER TO SENTINEL/`.

## Why it was closed

Time, not doubt. Competing priorities — all of them with either users or deadlines — outrank a
project whose only user is its author. The thesis still looks right; there is just no room for it.

## How to restart

```bash
git clone https://github.com/NidsC/equity-research.git
cd equity-research
python3.12 -m venv .venv               # NOT bare `python3` -- see below
.venv/bin/pip install --upgrade pip    # hatchling editable install needs modern pip
.venv/bin/pip install -e ".[dev]"      # [dev] is what carries pytest and ruff
.venv/bin/python -m pytest -q          # expect 29 passed
```

Verified from a clean clone on 2026-08-11: 29 passed, `er --help` works.

Two traps, both hit while testing the above. The project requires Python >=3.11, but bare
`python3` on this Mac is **3.9.6** — always name the version. And the pip bundled with a fresh
venv is too old for a hatchling editable install; upgrade it first or the install fails with a
misleading "requires a setuptools-based build".

The EDGAR cache and `.venv` were deleted; both regenerate. Everything else is in git history.

Then, in order:

1. Read `ER TO SENTINEL/STATE_AT_SHELVING.md`. It has the measured baselines so you don't
   re-derive them, and the list of what's genuinely absent.
2. **Answer the one open question before writing any code: is a 10-Q diff worth an alert?**
   A day's work across five companies. The 33–41% year-over-year change figure is measured on
   *annual* Item 1A; quarterly filings are shorter and change less. If a typical 10-Q diff turns
   up nothing material, SENTINEL's whole advantage over the v1 plan is gone and you should build
   `PLAN.md` instead. Do not skip this.
3. If it survives: build the Item 1A structural diff (`PLAN.md` step 1, three files). It is the
   first step of both plans, so it is never wasted work.

## Before restarting, reread

The kill criterion in `ER TO SENTINEL/PROJECT_SENTINEL.md` — *if three weeks after the digest
ships you aren't reading it, stop and say so*. Shelving here at the spec stage, having spent
nothing, is that criterion working rather than failing.
