"""Tests for session filtering, table parsing, and record building."""

from legislative_scraper.config import COLUMNS
from legislative_scraper.scraper import build_record, clean_label, matches, parse_table

ROW_HTML = (
    "<table><thead><tr><th>Sr No</th><th>Title</th><th>Details</th><th>Category</th>"
    "<th>Member</th><th>Ministry</th><th>Department(s)</th><th>Reply</th><th>Reply Regional</th></tr></thead>"
    "<tbody><tr><td>1</td><td>Q.No <b>1</b><p>Test Subject</p></td><td>details here</td>"
    "<td>Starred Questions</td><td>Paul Lyngdoh</td><td>Power Department</td><td>Power</td>"
    '<td><a href="https://x/reply.pdf"><img></a></td><td></td></tr></tbody></table>'
)


def test_match_target():
    assert matches("Autumn Session, 2026", {"Autumn Session, 2026"}) is True


def test_reject_other():
    assert matches("Budget Session, 2026", {"Autumn Session, 2026"}) is False


def test_case_insensitive_and_trailing_dot():
    assert matches("autumn session, 2026.", {"Autumn Session, 2026"}) is True
    assert clean_label("Autumn Session, 2026.") == "Autumn Session, 2026"


def test_empty_targets_match_all():
    assert matches("Budget Session, 2026", set()) is True


def test_parse_table_reads_text_and_links():
    rows, headers = parse_table(ROW_HTML)
    assert headers[0] == "Sr No" and len(rows) == 1
    cells, links = rows[0]
    assert cells[1] == "Q.No 1Test Subject"
    assert links == ["https://x/reply.pdf"]


def test_parse_table_empty_results():
    assert parse_table("<div>All Question No Records Founds.</div>") == ([], [])


def test_build_record_maps_fixed_columns():
    cells, links = parse_table(ROW_HTML)[0][0]
    rec = build_record(cells, links, "A11", "Autumn Session, 2026", "15-Sep-26")
    assert list(rec.keys()) == COLUMNS
    assert (rec["Sr_No"], rec["Asked_By"], rec["Departments"], rec["Ministry"]) == (
        "1", "Paul Lyngdoh", "Power Department", "Power")
    assert rec["Question_Number"] == rec["Subject"] == cells[1]
    assert rec["Reply"] == "" and rec["Document_Link"] == "https://x/reply.pdf"


def test_build_record_prefers_pdf_link():
    rec = build_record(["1", "T", "d", "Starred", "M", "Dept", "Min", "", ""],
                       ["https://x/page", "https://x/reply.pdf"], "A", "S", "D")
    assert rec["Document_Link"] == "https://x/reply.pdf"
