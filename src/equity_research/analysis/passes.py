"""The analysis lenses.

Each pass is deliberately narrow. A single "analyse this company" prompt
produces confident mush; four constrained passes with schemas produce claims you
can check. Every pass that touches numbers receives them pre-computed from XBRL
and is told not to derive its own.
"""

from __future__ import annotations

from .runner import AnalysisResult, run_pass

SYSTEM = (
    "You are a buy-side equity analyst. Be specific and falsifiable. "
    "Never state a figure that was not given to you in the prompt — if a number "
    "you want is absent, say so rather than estimating it. Attribute every claim "
    "to the filing section it came from. Prefer 'unclear from the filing' over a "
    "plausible guess."
)

_EVIDENCE = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "claim": {"type": "string"},
            "source_item": {"type": "string", "description": "e.g. 'Item 1A' or 'financials table'"},
            "quote_or_figure": {"type": "string"},
        },
        "required": ["claim", "source_item", "quote_or_figure"],
    },
}


BUSINESS_MODEL_SCHEMA = {
    "type": "object",
    "properties": {
        "what_they_sell": {"type": "string"},
        "revenue_model": {"type": "string"},
        "customer_concentration": {"type": "string"},
        "competitive_position": {"type": "string"},
        "moat_assessment": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": [
                        "network_effects",
                        "switching_costs",
                        "cost_advantage",
                        "intangible_assets",
                        "efficient_scale",
                        "none_evident",
                    ],
                },
                "durability": {"type": "string", "enum": ["strong", "moderate", "weak", "unclear"]},
                "reasoning": {"type": "string"},
            },
            "required": ["source", "durability", "reasoning"],
        },
        "evidence": _EVIDENCE,
    },
    "required": ["what_they_sell", "revenue_model", "competitive_position", "moat_assessment", "evidence"],
}

RISK_DELTA_SCHEMA = {
    "type": "object",
    "properties": {
        "new_risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["risk", "why_it_matters", "severity"],
            },
        },
        "removed_risks": {"type": "array", "items": {"type": "string"}},
        "materially_reworded": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk": {"type": "string"},
                    "change": {"type": "string"},
                    "direction": {"type": "string", "enum": ["escalated", "softened", "reframed"]},
                },
                "required": ["risk", "change", "direction"],
            },
        },
        "analyst_read": {"type": "string"},
    },
    "required": ["new_risks", "removed_risks", "materially_reworded", "analyst_read"],
}

EARNINGS_QUALITY_SCHEMA = {
    "type": "object",
    "properties": {
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "flag": {"type": "string"},
                    "metric_evidence": {"type": "string"},
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "benign_explanation": {"type": "string"},
                },
                "required": ["flag", "metric_evidence", "severity", "benign_explanation"],
            },
        },
        "cash_conversion_assessment": {"type": "string"},
        "margin_trend_assessment": {"type": "string"},
        "overall_quality": {"type": "string", "enum": ["high", "acceptable", "questionable", "poor"]},
    },
    "required": ["flags", "cash_conversion_assessment", "margin_trend_assessment", "overall_quality"],
}

MDA_SCHEMA = {
    "type": "object",
    "properties": {
        "management_narrative": {"type": "string"},
        "consistencies": {"type": "array", "items": {"type": "string"}},
        "tensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "management_says": {"type": "string"},
                    "numbers_show": {"type": "string"},
                    "assessment": {"type": "string"},
                },
                "required": ["management_says", "numbers_show", "assessment"],
            },
        },
        "forward_guidance_signals": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["management_narrative", "consistencies", "tensions", "forward_guidance_signals"],
}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[... truncated at {limit:,} characters ...]"


def business_model(ticker: str, item_1: str) -> AnalysisResult:
    prompt = f"""Analyse the business model and competitive position of {ticker} using only the
Item 1 (Business) section below.

Judge the moat on what the filing actually evidences, not on the company's reputation.
If Item 1 is mostly boilerplate, say the moat is unclear.

<item_1>
{_truncate(item_1, 120_000)}
</item_1>
"""
    return run_pass(prompt, schema=BUSINESS_MODEL_SCHEMA, system_prompt=SYSTEM)


def risk_delta(ticker: str, current_1a: str, prior_1a: str) -> AnalysisResult:
    prompt = f"""Compare {ticker}'s risk factors between two consecutive 10-K filings.

What changed year over year is the signal — risk factor sections are otherwise
boilerplate that carries forward verbatim. Ignore pure formatting changes.
Focus on genuinely new risks, dropped risks, and risks whose language escalated
or softened materially.

<prior_year_item_1a>
{_truncate(prior_1a, 100_000)}
</prior_year_item_1a>

<current_year_item_1a>
{_truncate(current_1a, 100_000)}
</current_year_item_1a>
"""
    return run_pass(prompt, schema=RISK_DELTA_SCHEMA, system_prompt=SYSTEM)


def earnings_quality(ticker: str, financials_markdown: str) -> AnalysisResult:
    prompt = f"""Assess the earnings quality of {ticker} from the figures below.

These figures were computed from the company's XBRL filings. Treat them as
ground truth and do not recompute or estimate anything.

Look for: operating cash flow persistently below net income, margin expansion
that is not supported by the cost lines, receivables or inventory growing faster
than revenue, and leverage trends. For every flag, state the most plausible
innocent explanation as well.

{financials_markdown}
"""
    return run_pass(prompt, schema=EARNINGS_QUALITY_SCHEMA, system_prompt=SYSTEM)


def mda_vs_numbers(ticker: str, item_7: str, financials_markdown: str) -> AnalysisResult:
    prompt = f"""Compare what {ticker}'s management says in the MD&A against what the reported
figures show.

The figures below are computed from XBRL and are ground truth. The MD&A is
management's framing of the same period. Your job is to find where the framing
and the figures pull in different directions — emphasis on a growing segment
while total revenue declines, "disciplined cost management" alongside rising
opex, that kind of thing. Also note where they genuinely agree.

{financials_markdown}

<item_7_mda>
{_truncate(item_7, 120_000)}
</item_7_mda>
"""
    return run_pass(prompt, schema=MDA_SCHEMA, system_prompt=SYSTEM)
