"""XBRL company facts -> a normalized annual financial table.

Design rule for the whole platform: numbers come from here, never from a
language model. Filers tag the same economic line item with different concepts
depending on industry and filing era, so each logical line has an ordered list
of candidate concepts and we take the first one that actually has data.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Ordered fallbacks. First concept with data for a period wins.
CONCEPT_MAP: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "rnd": ["ResearchAndDevelopmentExpense"],
    "sgna": [
        "SellingGeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpense",
    ],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "total_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "inventory": ["InventoryNet"],
    "receivables": ["AccountsReceivableNetCurrent"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}

# Balance-sheet items are point-in-time facts (no start date); income and
# cash-flow items span a period. XBRL marks the difference with the presence of
# `start`, so _facts_for_concept discriminates on that directly — there is no
# need for a hand-maintained list of which line items are which.


@dataclass(frozen=True)
class Fact:
    end: str
    val: float
    fy: int
    form: str
    accession: str


def _facts_for_concept(company_facts: dict, concept: str, taxonomy: str = "us-gaap") -> list[Fact]:
    node = company_facts.get("facts", {}).get(taxonomy, {}).get(concept)
    if not node:
        return []

    out: list[Fact] = []
    for unit, entries in node.get("units", {}).items():
        if unit not in ("USD", "shares", "USD/shares"):
            continue
        for e in entries:
            if e.get("form") not in ("10-K", "10-K/A"):
                continue
            start, end = e.get("start"), e.get("end")
            if start is not None:
                # Duration fact: keep only full-year periods (340-400 days).
                days = (pd.Timestamp(end) - pd.Timestamp(start)).days
                if not 340 <= days <= 400:
                    continue
            out.append(
                Fact(
                    end=end,
                    val=float(e["val"]),
                    fy=int(e.get("fy") or pd.Timestamp(end).year),
                    form=e["form"],
                    accession=e.get("accn", ""),
                )
            )
    return out


def _series_for_line(company_facts: dict, line: str) -> dict[str, float]:
    """Best available value per period end for one logical line item."""
    series: dict[str, float] = {}

    for concept in CONCEPT_MAP[line]:
        for fact in _facts_for_concept(company_facts, concept):
            # Facts arrive in filing order within a concept, so the first value
            # seen for a period end is the one originally reported.
            series.setdefault(fact.end, fact.val)
        if series:
            break

    return series


def annual_financials(company_facts: dict, years: int = 10) -> pd.DataFrame:
    """Wide table of annual financials, one row per fiscal period end."""
    columns = {line: _series_for_line(company_facts, line) for line in CONCEPT_MAP}
    frame = pd.DataFrame(columns)
    if frame.empty:
        return frame

    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()

    # Balance-sheet dates and income-statement period ends do not always align
    # exactly; snap everything to fiscal year and collapse.
    frame["fiscal_year"] = frame.index.year
    frame = frame.groupby("fiscal_year").last()

    return frame.tail(years)


def derived_metrics(financials: pd.DataFrame) -> pd.DataFrame:
    """Ratios and growth rates computed from the normalized table.

    Everything here is arithmetic on reported figures — auditable, reproducible,
    and safe to hand to an analysis agent as ground truth.
    """
    if financials.empty:
        return financials

    f = financials
    out = pd.DataFrame(index=f.index)

    def safe_div(a: str, b: str) -> pd.Series:
        if a not in f or b not in f:
            return pd.Series(index=f.index, dtype="float64")
        return f[a] / f[b].replace(0, pd.NA)

    gross_profit = f.get("gross_profit")
    missing = gross_profit is None or gross_profit.isna().all()
    if missing and "revenue" in f and "cost_of_revenue" in f:
        # Some filers report only revenue and COGS; derive the difference.
        gross_profit = f["revenue"] - f["cost_of_revenue"]
    if gross_profit is not None:
        out["gross_margin"] = gross_profit / f["revenue"].replace(0, pd.NA)

    out["operating_margin"] = safe_div("operating_income", "revenue")
    out["net_margin"] = safe_div("net_income", "revenue")
    out["roe"] = safe_div("net_income", "equity")
    out["roa"] = safe_div("net_income", "assets")
    out["current_ratio"] = safe_div("current_assets", "current_liabilities")
    out["debt_to_equity"] = safe_div("total_debt", "equity")
    out["rnd_intensity"] = safe_div("rnd", "revenue")

    if "operating_cash_flow" in f and "capex" in f:
        fcf = f["operating_cash_flow"] - f["capex"]
        out["free_cash_flow"] = fcf
        out["fcf_margin"] = fcf / f["revenue"].replace(0, pd.NA)

    if "net_income" in f and "operating_cash_flow" in f:
        # Accruals check: persistent OCF < net income is an earnings-quality flag.
        out["ocf_to_net_income"] = safe_div("operating_cash_flow", "net_income")

    for line in ("revenue", "operating_income", "net_income"):
        if line in f:
            out[f"{line}_growth"] = f[line].pct_change()

    return out


def to_markdown_table(financials: pd.DataFrame, metrics: pd.DataFrame) -> str:
    """Verified figures formatted for an analysis prompt."""
    if financials.empty:
        return "_No XBRL financial data available._"

    scaled = financials.drop(columns=["shares_diluted"], errors="ignore") / 1e6
    if "shares_diluted" in financials:
        scaled["shares_diluted_m"] = financials["shares_diluted"] / 1e6

    # free_cash_flow is a currency amount living in a table of ratios — scale it
    # to millions like everything else, or it prints as raw dollars (1.1e+11)
    # next to values between 0 and 1.
    metrics_display = metrics.copy()
    if "free_cash_flow" in metrics_display:
        metrics_display["free_cash_flow"] = metrics_display["free_cash_flow"] / 1e6
        metrics_display = metrics_display.rename(
            columns={"free_cash_flow": "free_cash_flow_m"}
        )

    parts = [
        "### Reported financials (USD millions, from XBRL)",
        scaled.round(1).to_markdown(),
        "",
        "### Derived metrics (computed, not model-generated)",
        metrics_display.round(4).to_markdown(),
    ]
    return "\n".join(parts)
