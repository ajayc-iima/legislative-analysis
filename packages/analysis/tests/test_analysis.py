"""Tests for the analysis module (synthetic data only)."""

import json

from legislative_analysis.analysis import analyze, load, parse_date, write_report

CSV_TEXT = """Assembly,Session,Session_Date,Sr_No,Subject,Departments,Asked_By,Question_Type,Document_Link
Eleventh,"Autumn Session, 2025",15/Oct/2025,1,Marten dumping ground,Urban Affairs,A B,Starred Questions,https://x/1.pdf
Eleventh,"Autumn Session, 2025",16/Oct/2025,2,Roads,PWD,C D,Unstarred Questions,
Eleventh,"Budget Session, 2026",10/Mar/2026,1,Marten Dumping Ground,Urban Affairs,A B,Starred Questions,https://x/2.pdf
Eleventh,"Budget Session, 2026",11/Mar/2026,2,Roads,Power,E F,Unstarred Questions,https://x/3.pdf
"""


def _csv(tmp_path):
    path = tmp_path / "questions.csv"
    path.write_text(CSV_TEXT, encoding="utf-8")
    return path


def test_load_and_overview(tmp_path):
    stats = analyze(load(_csv(tmp_path)))
    assert stats["overview"]["questions"] == 4
    assert stats["overview"]["sessions"] == 2
    assert stats["overview"]["departments"] == 3
    assert stats["overview"]["with_reply"] == 3
    assert stats["overview"]["reply_coverage"] == 75.0


def test_recurring_subjects_are_case_insensitive(tmp_path):
    stats = analyze(load(_csv(tmp_path)))
    subjects = {r["subject"]: r for r in stats["recurring"]}
    assert "marten dumping ground" in subjects
    assert len(subjects["marten dumping ground"]["sessions"]) == 2
    assert "roads" not in subjects  # too short to count as a meaningful subject


def test_sessions_sorted_by_first_date(tmp_path):
    stats = analyze(load(_csv(tmp_path)))
    assert [s["session"] for s in stats["sessions"]] == [
        "Autumn Session, 2025", "Budget Session, 2026"]


def test_department_and_mla_tables(tmp_path):
    stats = analyze(load(_csv(tmp_path)))
    assert stats["departments"][0]["department"] == "Urban Affairs"
    assert stats["departments"][0]["questions"] == 2
    assert stats["departments"][0]["coverage"] == 100.0
    assert stats["mlas"][0]["mla"] == "A B"


def test_write_report(tmp_path):
    stats = analyze(load(_csv(tmp_path)))
    report = write_report(stats, tmp_path / "out", source="questions.csv")
    text = report.read_text(encoding="utf-8")
    assert "Recurring subjects" in text and "Urban Affairs" in text
    saved = json.loads((tmp_path / "out" / "stats.json").read_text(encoding="utf-8"))
    assert saved["overview"]["questions"] == 4


def test_parse_date_formats():
    assert parse_date("15/Oct/2025").year == 2025
    assert parse_date("15-Oct-25").month == 10
    assert parse_date("garbage") is None


def test_department_variants_merge():
    rows = [
        {"Departments": "Power Department", "Asked_By": "A", "Subject": "Load shedding"},
        {"Departments": "Power", "Asked_By": "B", "Subject": "Load shedding"},
        {"Departments": "Education", "Asked_By": "C", "Subject": "Schools"},
    ]
    stats = analyze(rows)
    assert stats["overview"]["departments"] == 2
    power = next(d for d in stats["departments"] if d["department"] == "Power Department")
    assert power["questions"] == 2
    assert power["askers"] == 2


def test_department_prefix_variants_fold():
    rows = [
        {"Departments": "Community & Rural Development", "Asked_By": "A", "Subject": "Roads x"},
        {"Departments": "Community & Rural Department", "Asked_By": "B", "Subject": "Roads y"},
        {"Departments": "Community & Rural", "Asked_By": "C", "Subject": "Roads z"},
    ]
    stats = analyze(rows)
    assert stats["overview"]["departments"] == 1
    assert stats["departments"][0]["questions"] == 3
