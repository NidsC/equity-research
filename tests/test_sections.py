"""Section extraction tests against filing-shaped HTML."""

from __future__ import annotations

from equity_research.parse.sections import extract_sections, html_to_text, split_items

BODY_1 = "We design and sell widgets to industrial customers worldwide. " * 20
BODY_1A = "Our business faces supply chain concentration risk in a single region. " * 20
BODY_7 = "Revenue increased year over year driven by volume in our core segment. " * 20

FILING_HTML = f"""
<html><body>
  <style>.hidden {{ display:none }}</style>
  <p>TABLE OF CONTENTS</p>
  <p>Item 1. Business ....... 3</p>
  <p>Item 1A. Risk Factors ....... 12</p>
  <p>Item 7. Management's Discussion and Analysis ....... 40</p>

  <p>Item 1. Business</p>
  <p>{BODY_1}</p>

  <p>Item 1A. Risk Factors</p>
  <p>{BODY_1A}</p>

  <p>Item 7. Management&rsquo;s Discussion and Analysis</p>
  <p>{BODY_7}</p>

  <p>Item 8. Financial Statements and Supplementary Data</p>
  <p>See the consolidated financial statements beginning on page F-1.</p>
</body></html>
"""


def test_html_to_text_drops_style_and_normalizes_whitespace():
    text = html_to_text("<html><body><style>a{color:red}</style><p>Hello    world</p></body></html>")
    assert "color:red" not in text
    assert "Hello world" in text


def test_extracts_expected_items():
    found = extract_sections(FILING_HTML)
    assert {"1", "1A", "7"} <= set(found)


def test_table_of_contents_entries_are_not_returned_as_bodies():
    found = extract_sections(FILING_HTML)
    # The TOC line is ~25 chars; a real body is thousands.
    assert len(found["1A"]) > 1000
    assert "....... 12" not in found["1A"][:200]


def test_sections_do_not_bleed_into_the_next_item():
    found = extract_sections(FILING_HTML)
    assert "supply chain concentration" not in found["1"]
    assert "Revenue increased" not in found["1A"]


def test_short_sections_are_dropped_as_artifacts():
    found = extract_sections(FILING_HTML)
    # Item 8 here is a one-line cross reference, below the 200-char floor.
    assert "8" not in found


def test_no_items_found_returns_empty():
    assert split_items("Just some prose with no headings at all.") == {}


BODY_9A = "Management concluded that disclosure controls were effective. " * 20
TRAILING_JUNK = "Exhibit 21.1 Subsidiaries of the Registrant. " * 500

FILING_WITH_TAIL = f"""
<html><body>
  <p>Item 9A. Controls and Procedures</p>
  <p>{BODY_9A}</p>

  <p>Item 15. Exhibits and Financial Statement Schedules</p>
  <p>{TRAILING_JUNK}</p>

  <p>SIGNATURES</p>
  <p>Pursuant to the requirements of Section 13 of the Securities Exchange Act...</p>
</body></html>
"""


def test_final_wanted_item_does_not_swallow_the_rest_of_the_filing():
    """Regression: Item 9A used to run to EOF, absorbing exhibits and signatures."""
    found = extract_sections(FILING_WITH_TAIL)
    assert "9A" in found
    assert "Subsidiaries of the Registrant" not in found["9A"]
    assert "Pursuant to the requirements" not in found["9A"]
    assert len(found["9A"]) < len(BODY_9A) + 200


FILING_NO_LATER_ITEM = f"""
<html><body>
  <p>Item 9A. Controls and Procedures</p>
  <p>{BODY_9A}</p>
  <p>SIGNATURES</p>
  <p>{TRAILING_JUNK}</p>
</body></html>
"""


def test_tail_marker_bounds_the_last_item_when_no_later_item_exists():
    found = extract_sections(FILING_NO_LATER_ITEM)
    assert "9A" in found
    assert "Subsidiaries of the Registrant" not in found["9A"]


def test_boundary_only_items_are_not_returned():
    """Items 10-16 bound sections but are not research content."""
    found = extract_sections(FILING_WITH_TAIL)
    assert "15" not in found
