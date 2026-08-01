"""Render analysis-pass output into a research memo."""

from __future__ import annotations

from typing import Any

from ..analysis.runner import AnalysisResult


def _fmt_evidence(evidence: list[dict]) -> str:
    lines = []
    for item in evidence:
        lines.append(
            f"- **{item.get('claim', '')}** — {item.get('source_item', '?')}: "
            f"_{item.get('quote_or_figure', '')}_"
        )
    return "\n".join(lines)


def _business_model_section(data: dict) -> str:
    moat = data.get("moat_assessment", {})
    parts = [
        "## Business & competitive position",
        "",
        f"**What they sell.** {data.get('what_they_sell', '')}",
        "",
        f"**Revenue model.** {data.get('revenue_model', '')}",
        "",
        f"**Competitive position.** {data.get('competitive_position', '')}",
        "",
        f"**Moat:** {moat.get('source', 'unknown')} — durability **{moat.get('durability', 'unclear')}**",
        "",
        moat.get("reasoning", ""),
    ]
    if data.get("customer_concentration"):
        parts += ["", f"**Customer concentration.** {data['customer_concentration']}"]
    if data.get("evidence"):
        parts += ["", "### Evidence", "", _fmt_evidence(data["evidence"])]
    return "\n".join(parts)


def _risk_delta_section(data: dict) -> str:
    parts = ["## Risk factor changes year over year", "", data.get("analyst_read", ""), ""]

    if data.get("new_risks"):
        parts.append("### New risks")
        parts.append("")
        for risk in data["new_risks"]:
            parts.append(
                f"- **[{risk.get('severity', '?').upper()}] {risk.get('risk', '')}** — "
                f"{risk.get('why_it_matters', '')}"
            )
        parts.append("")

    if data.get("materially_reworded"):
        parts.append("### Reworded")
        parts.append("")
        for risk in data["materially_reworded"]:
            parts.append(
                f"- _{risk.get('direction', '')}_ — **{risk.get('risk', '')}**: {risk.get('change', '')}"
            )
        parts.append("")

    if data.get("removed_risks"):
        parts.append("### Dropped")
        parts.append("")
        parts += [f"- {risk}" for risk in data["removed_risks"]]
        parts.append("")

    return "\n".join(parts)


def _earnings_quality_section(data: dict) -> str:
    parts = [
        "## Earnings quality",
        "",
        f"**Overall: {data.get('overall_quality', 'unknown')}**",
        "",
        f"**Cash conversion.** {data.get('cash_conversion_assessment', '')}",
        "",
        f"**Margin trend.** {data.get('margin_trend_assessment', '')}",
        "",
    ]
    if data.get("flags"):
        parts += ["### Flags", ""]
        for flag in data["flags"]:
            parts.append(f"- **[{flag.get('severity', '?').upper()}] {flag.get('flag', '')}**")
            parts.append(f"  - Evidence: {flag.get('metric_evidence', '')}")
            parts.append(f"  - Benign reading: {flag.get('benign_explanation', '')}")
        parts.append("")
    else:
        parts += ["No earnings-quality flags raised.", ""]
    return "\n".join(parts)


def _mda_section(data: dict) -> str:
    parts = [
        "## Management commentary vs. reported figures",
        "",
        data.get("management_narrative", ""),
        "",
    ]
    if data.get("tensions"):
        parts += ["### Where narrative and numbers diverge", ""]
        for tension in data["tensions"]:
            parts.append(f"- **Management says:** {tension.get('management_says', '')}")
            parts.append(f"  - **Numbers show:** {tension.get('numbers_show', '')}")
            parts.append(f"  - **Read:** {tension.get('assessment', '')}")
        parts.append("")
    if data.get("consistencies"):
        parts += ["### Where they agree", ""]
        parts += [f"- {item}" for item in data["consistencies"]]
        parts.append("")
    if data.get("forward_guidance_signals"):
        parts += ["### Forward-looking signals", ""]
        parts += [f"- {item}" for item in data["forward_guidance_signals"]]
        parts.append("")
    return "\n".join(parts)


RENDERERS = {
    "business_model": _business_model_section,
    "risk_delta": _risk_delta_section,
    "earnings_quality": _earnings_quality_section,
    "mda_vs_numbers": _mda_section,
}

ORDER = ["business_model", "earnings_quality", "mda_vs_numbers", "risk_delta"]


def render_memo(dossier: Any, results: dict[str, Any]) -> str:
    latest = dossier.filings[0]
    parts = [
        f"# {dossier.entity_name} ({dossier.ticker})",
        "",
        (
            f"CIK {dossier.cik} · latest 10-K filed {latest.filing_date} "
            f"for period ending {latest.report_date}"
        ),
        "",
        f"[Source filing]({latest.document_url})",
        "",
        "---",
        "",
    ]

    total_cost = 0.0
    for name in ORDER:
        result = results.get(name)
        if result is None:
            continue
        if isinstance(result, Exception):
            parts += [f"## {name.replace('_', ' ').title()}", "", f"_Pass failed: {result}_", ""]
            continue
        if isinstance(result, AnalysisResult):
            if result.cost_usd:
                total_cost += result.cost_usd
            data = result.output if isinstance(result.output, dict) else {}
            parts += [RENDERERS[name](data), "", "---", ""]

    parts += ["## Verified financials", "", dossier.financials_markdown, ""]

    if dossier.warnings:
        parts += ["## Data caveats", ""]
        parts += [f"- {warning}" for warning in dossier.warnings]
        parts.append("")

    parts += [
        "---",
        "",
        (
            f"_Generated from SEC EDGAR filings. Analysis cost: ${total_cost:.2f}. "
            "All figures computed from XBRL; narrative assessments are model-generated "
            "and should be verified against the source filing before use._"
        ),
    ]

    return "\n".join(parts)
