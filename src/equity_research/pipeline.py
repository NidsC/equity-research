"""Ticker in, research memo out.

Deterministic work (fetch, parse, compute) happens first and completely. Only
then do the analysis passes run, in parallel, each over a slice of verified
input. If the deterministic half fails we stop — a memo built on half-parsed
financials is worse than no memo.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Any

from .analysis import passes
from .ingest.edgar import EdgarClient, Filing
from .parse import sections
from .parse.financials import annual_financials, derived_metrics, to_markdown_table
from .report.memo import render_memo


@dataclass
class CompanyDossier:
    """Everything deterministic we know before any model runs."""

    ticker: str
    cik: str
    entity_name: str
    filings: list[Filing]
    financials_markdown: str
    item_1: str = ""
    item_1a: str = ""
    item_1a_prior: str = ""
    item_7: str = ""
    warnings: list[str] = field(default_factory=list)


def build_dossier(ticker: str, *, years: int = 10) -> CompanyDossier:
    with EdgarClient() as client:
        cik = client.cik_for_ticker(ticker)
        facts = client.company_facts(cik)
        entity_name = facts.get("entityName", ticker)

        financials = annual_financials(facts, years=years)
        metrics = derived_metrics(financials)
        financials_markdown = to_markdown_table(financials, metrics)

        filings = client.filings(cik, forms=("10-K",), limit=2)
        if not filings:
            raise RuntimeError(f"No 10-K filings found for {ticker} (CIK {cik})")

        warnings: list[str] = []
        current = sections.extract_sections(client.filing_document(filings[0]))

        prior: dict[str, str] = {}
        if len(filings) > 1:
            prior = sections.extract_sections(client.filing_document(filings[1]))
        else:
            warnings.append("Only one 10-K available; risk-factor delta skipped.")

    for item in ("1", "1A", "7"):
        if item not in current:
            warnings.append(f"Item {item} could not be located in the latest 10-K.")

    return CompanyDossier(
        ticker=ticker.upper(),
        cik=cik,
        entity_name=entity_name,
        filings=filings,
        financials_markdown=financials_markdown,
        item_1=current.get("1", ""),
        item_1a=current.get("1A", ""),
        item_1a_prior=prior.get("1A", ""),
        item_7=current.get("7", ""),
        warnings=warnings,
    )


def run_analysis(dossier: CompanyDossier) -> dict[str, Any]:
    """Run every applicable analysis pass concurrently."""
    jobs: dict[str, Any] = {}

    if dossier.item_1:
        jobs["business_model"] = lambda: passes.business_model(dossier.ticker, dossier.item_1)
    if dossier.item_1a and dossier.item_1a_prior:
        jobs["risk_delta"] = lambda: passes.risk_delta(
            dossier.ticker, dossier.item_1a, dossier.item_1a_prior
        )
    jobs["earnings_quality"] = lambda: passes.earnings_quality(
        dossier.ticker, dossier.financials_markdown
    )
    if dossier.item_7:
        jobs["mda_vs_numbers"] = lambda: passes.mda_vs_numbers(
            dossier.ticker, dossier.item_7, dossier.financials_markdown
        )

    results: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): name for name, fn in jobs.items()}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:  # noqa: BLE001 - see below
                # Deliberately broad: one failed lens should not sink the memo.
                # RateLimitTripwire is a BaseException precisely so it escapes
                # this handler and stops the run.
                results[name] = exc
                dossier.warnings.append(f"Pass '{name}' failed: {exc}")

    return results


def research(ticker: str, *, years: int = 10) -> str:
    dossier = build_dossier(ticker, years=years)
    results = run_analysis(dossier)
    return render_memo(dossier, results)
