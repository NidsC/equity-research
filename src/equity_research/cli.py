"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="er", description="AI equity research over SEC filings")
    sub = parser.add_subparsers(dest="command", required=True)

    facts = sub.add_parser("facts", help="Fetch and print verified financials (no model calls)")
    facts.add_argument("ticker")
    facts.add_argument("--years", type=int, default=10)

    sections_cmd = sub.add_parser("sections", help="List narrative sections found in the latest 10-K")
    sections_cmd.add_argument("ticker")

    research = sub.add_parser("research", help="Full research memo (runs analysis passes)")
    research.add_argument("ticker")
    research.add_argument("--years", type=int, default=10)
    research.add_argument("-o", "--output", type=Path, help="Write memo to this path")

    args = parser.parse_args(argv)

    if args.command == "facts":
        from .ingest.edgar import EdgarClient
        from .parse.financials import annual_financials, derived_metrics, to_markdown_table

        with EdgarClient() as client:
            cik = client.cik_for_ticker(args.ticker)
            company_facts = client.company_facts(cik)
        financials = annual_financials(company_facts, years=args.years)
        print(f"{company_facts.get('entityName', args.ticker)} (CIK {cik})\n")
        print(to_markdown_table(financials, derived_metrics(financials)))
        return 0

    if args.command == "sections":
        from .ingest.edgar import EdgarClient
        from .parse.sections import extract_sections, section_title

        with EdgarClient() as client:
            cik = client.cik_for_ticker(args.ticker)
            filings = client.filings(cik, forms=("10-K",), limit=1)
            if not filings:
                print(f"No 10-K found for {args.ticker}", file=sys.stderr)
                return 1
            html = client.filing_document(filings[0])
        found = extract_sections(html)
        print(f"10-K filed {filings[0].filing_date} — {len(found)} sections located\n")
        for number, body in found.items():
            print(f"  Item {number:<4} {section_title(number):<52} {len(body):>9,} chars")
        return 0

    if args.command == "research":
        from .pipeline import research as run_research

        memo = run_research(args.ticker, years=args.years)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(memo)
            print(f"Wrote {args.output}")
        else:
            print(memo)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
