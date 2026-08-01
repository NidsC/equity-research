"""Parser tests run entirely on synthetic facts — no network, no cache."""

from __future__ import annotations

import pandas as pd
import pytest

from equity_research.parse.financials import (
    annual_financials,
    derived_metrics,
    to_markdown_table,
)


def _fact(start: str | None, end: str, val: float, fy: int, form: str = "10-K") -> dict:
    entry = {"end": end, "val": val, "fy": fy, "fp": "FY", "form": form, "accn": f"acc-{fy}"}
    if start:
        entry["start"] = start
    return entry


def _company_facts() -> dict:
    return {
        "cik": 320193,
        "entityName": "Test Co",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            _fact("2022-01-01", "2022-12-31", 1_000_000_000, 2022),
                            _fact("2023-01-01", "2023-12-31", 1_200_000_000, 2023),
                            # Quarterly fact — must be filtered out.
                            _fact("2023-10-01", "2023-12-31", 350_000_000, 2023),
                            # Wrong form — must be filtered out.
                            _fact("2023-01-01", "2023-12-31", 999, 2023, form="10-Q"),
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            _fact("2022-01-01", "2022-12-31", 100_000_000, 2022),
                            _fact("2023-01-01", "2023-12-31", 150_000_000, 2023),
                        ]
                    }
                },
                "Assets": {
                    "units": {
                        "USD": [
                            _fact(None, "2022-12-31", 2_000_000_000, 2022),
                            _fact(None, "2023-12-31", 2_500_000_000, 2023),
                        ]
                    }
                },
                "StockholdersEquity": {
                    "units": {
                        "USD": [
                            _fact(None, "2022-12-31", 800_000_000, 2022),
                            _fact(None, "2023-12-31", 1_000_000_000, 2023),
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            _fact("2022-01-01", "2022-12-31", 90_000_000, 2022),
                            _fact("2023-01-01", "2023-12-31", 120_000_000, 2023),
                        ]
                    }
                },
            }
        },
    }


def test_annual_financials_extracts_yearly_rows():
    frame = annual_financials(_company_facts())
    assert list(frame.index) == [2022, 2023]
    assert frame.loc[2023, "revenue"] == 1_200_000_000


def test_quarterly_and_wrong_form_facts_are_excluded():
    frame = annual_financials(_company_facts())
    # The 350m quarterly and the 999 10-Q value must never appear.
    assert frame.loc[2023, "revenue"] == 1_200_000_000
    assert 350_000_000 not in frame["revenue"].values


def test_instant_facts_land_on_the_right_year():
    frame = annual_financials(_company_facts())
    assert frame.loc[2022, "assets"] == 2_000_000_000
    assert frame.loc[2023, "equity"] == 1_000_000_000


def test_derived_metrics_are_arithmetic_on_reported_figures():
    frame = annual_financials(_company_facts())
    metrics = derived_metrics(frame)

    assert metrics.loc[2023, "net_margin"] == 150_000_000 / 1_200_000_000
    assert metrics.loc[2023, "roe"] == 150_000_000 / 1_000_000_000
    assert metrics.loc[2023, "revenue_growth"] == pytest.approx(0.2)
    # OCF below net income is the accruals flag the analysis pass looks for.
    assert metrics.loc[2023, "ocf_to_net_income"] < 1.0


def test_empty_facts_returns_empty_frame():
    frame = annual_financials({"facts": {"us-gaap": {}}})
    assert frame.empty
    assert derived_metrics(frame).empty


def test_missing_concept_does_not_crash_metrics():
    facts = _company_facts()
    del facts["facts"]["us-gaap"]["StockholdersEquity"]
    metrics = derived_metrics(annual_financials(facts))
    assert pd.isna(metrics.loc[2023, "roe"])


def test_free_cash_flow_renders_in_millions():
    frame = annual_financials(_company_facts())
    table = to_markdown_table(frame, derived_metrics(frame))
    # The raw value is 1.07e+11; scaled it is ~107,539 (millions).
    assert "free_cash_flow_m" in table
    assert "1.07539e+11" not in table
