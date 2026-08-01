"""Split a 10-K into its narrative Items.

10-K HTML has no semantic structure worth trusting — filers use tables for
layout and inline styles for headings. The reliable signal is the Item headings
themselves in the flattened text. We find every occurrence and take the last
one before the next Item, which skips the table-of-contents entries.
"""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

# Every Item heading a 10-K can carry, in filing order. This list exists to
# bound sections: a section ends at the next heading in this sequence. It must
# be complete even where we don't want the content, otherwise the last item we
# care about runs to the end of the document and swallows the financial
# statements, signatures, and exhibit index.
ALL_ITEMS: list[tuple[str, str]] = [
    ("1", "Business"),
    ("1A", "Risk Factors"),
    ("1B", "Unresolved Staff Comments"),
    ("1C", "Cybersecurity"),
    ("2", "Properties"),
    ("3", "Legal Proceedings"),
    ("4", "Mine Safety Disclosures"),
    ("5", "Market for Registrant's Common Equity"),
    ("6", "Reserved"),
    ("7", "Management's Discussion and Analysis"),
    ("7A", "Quantitative and Qualitative Disclosures About Market Risk"),
    ("8", "Financial Statements and Supplementary Data"),
    ("9", "Changes in and Disagreements with Accountants"),
    ("9A", "Controls and Procedures"),
    ("9B", "Other Information"),
    ("9C", "Disclosure Regarding Foreign Jurisdictions"),
    ("10", "Directors, Executive Officers and Corporate Governance"),
    ("11", "Executive Compensation"),
    ("12", "Security Ownership"),
    ("13", "Certain Relationships and Related Transactions"),
    ("14", "Principal Accountant Fees and Services"),
    ("15", "Exhibits and Financial Statement Schedules"),
    ("16", "Form 10-K Summary"),
]

# Items we actually return. Everything else in ALL_ITEMS is a boundary marker.
WANTED_ITEMS = {"1", "1A", "1B", "1C", "2", "3", "5", "7", "7A", "8", "9A"}

# Backstop for the final item when no later Item heading exists — Part IV of a
# 10-K ends here even when the issuer omits Item 15 or 16.
TAIL_MARKERS = re.compile(
    r"^\s*(SIGNATURES?|EXHIBIT\s+INDEX|INDEX\s+TO\s+EXHIBITS)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Public alias: the items callers can ask for, with their titles.
ITEMS: list[tuple[str, str]] = [(n, t) for n, t in ALL_ITEMS if n in WANTED_ITEMS]


def html_to_text(html: str) -> str:
    """Flatten filing HTML to whitespace-normalized text."""
    tree = HTMLParser(html)
    for tag in tree.css("script, style"):
        tag.decompose()
    text = tree.body.text(separator="\n") if tree.body else tree.text(separator="\n")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _item_pattern(number: str) -> re.Pattern[str]:
    # "Item 1A.", "ITEM 1A -", "Item 1A:" and friends.
    return re.compile(rf"^\s*item\s+{re.escape(number)}\s*[.:\-–—]?\s", re.IGNORECASE | re.MULTILINE)


def split_items(text: str) -> dict[str, str]:
    """Map item number -> section body.

    Returns only items in WANTED_ITEMS that were found with plausible content.
    A section shorter than 200 characters is treated as a table-of-contents
    artifact, not a body.
    """
    ordered = [n for n, _ in ALL_ITEMS]
    positions: dict[str, list[int]] = {
        number: [m.start() for m in _item_pattern(number).finditer(text)]
        for number in ordered
    }

    # Where Part IV ends, for bounding the final item present in the filing.
    tail = [m.start() for m in TAIL_MARKERS.finditer(text)]

    sections: dict[str, str] = {}

    for idx, number in enumerate(ordered):
        if number not in WANTED_ITEMS:
            continue
        starts = positions.get(number) or []
        if not starts:
            continue

        best_body = ""
        for start in starts:
            # Bound at the nearest following heading of ANY later item, not the
            # first later item that happens to appear anywhere. Issuers skip and
            # reorder items freely; taking the minimum is what keeps a section
            # from running past its true end.
            candidates = [
                p
                for later in ordered[idx + 1 :]
                for p in positions.get(later, [])
                if p > start
            ]
            candidates += [p for p in tail if p > start]
            end = min(candidates) if candidates else len(text)

            body = text[start:end].strip()
            if len(body) > len(best_body):
                best_body = body

        if len(best_body) >= 200:
            sections[number] = best_body

    return sections


def extract_sections(html: str) -> dict[str, str]:
    """Convenience wrapper: filing HTML -> item sections."""
    return split_items(html_to_text(html))


def section_title(number: str) -> str:
    for num, title in ALL_ITEMS:
        if num == number:
            return title
    return f"Item {number}"
