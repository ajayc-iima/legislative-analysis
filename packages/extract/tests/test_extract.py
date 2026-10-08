"""Tests for the extraction harness (no live API calls)."""

from legislative_extract import nvidia
from legislative_extract.extract import (find_dates, parse_date,
                                         split_reply, squash_spaced_text)
from legislative_extract.trial import ocr_text, score_text


def test_load_key_prefers_explicit_and_env(monkeypatch):
    assert nvidia.load_key(explicit="abc") == "abc"
    monkeypatch.setenv("NVIDIA_API_KEY", "env-key")
    assert nvidia.load_key() == "env-key"
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("NIM_API_KEY", raising=False)
    monkeypatch.setattr(nvidia, "LEGACY_KEY_PATHS", [])
    assert nvidia.load_key() == ""


def test_score_text_matches_fields():
    truth = {"memo": "PLR.89/2023/9-A", "reply_date": "14th September, 2023",
             "scheduled": "", "minister": "Kyrmen Shylla",
             "excerpt": "apex body for coordinating", "table_cells": ["185"]}
    text = ("Memo No. PLR.89/2023/9-A Dated Shillong, the 14th September, 2023. "
            "Shri Kyrmen Shylla reply: apex body for coordinating work TOTAL 185")
    checks = score_text(text, truth)
    assert all(checks.values()), checks


def test_score_text_misses_absent_field():
    truth = {"memo": "PLR.89/2023/9-A", "reply_date": "", "scheduled": "",
             "minister": "", "excerpt": "apex body"}
    assert score_text("unrelated text here", truth)["memo"] is False
    assert score_text("unrelated text here", truth)["reply_date"] is True  # empty want = pass


def test_ocr_text_sorts_detections(monkeypatch):
    payload = {"data": [{"text_detections": [
        {"text_prediction": {"text": "world"},
         "bounding_box": {"points": [{"x": 50, "y": 10}, {"x": 90, "y": 30}]}},
        {"text_prediction": {"text": "Hello"},
         "bounding_box": {"points": [{"x": 10, "y": 10}, {"x": 40, "y": 30}]}},
    ]}]}
    monkeypatch.setattr(nvidia, "cv_model", lambda *a, **k: (True, payload, "", 5))
    ok, text, _, _ = ocr_text("key", "model", b"png")
    assert ok and text == "Hello world"


def test_ocr_text_propagates_failure(monkeypatch):
    monkeypatch.setattr(nvidia, "cv_model", lambda *a, **k: (False, None, "HTTP 500", 5))
    ok, text, error, _ = ocr_text("key", "model", b"png")
    assert ok is False and text == "" and error == "HTTP 500"


def test_parse_document_reads_tool_calls(monkeypatch):
    payload = {"choices": [{"message": {"tool_calls": [
        {"type": "function", "function": {"name": "markdown_no_bbox",
                                          "arguments": "[{\"text\": \"hello\"}]"}}]}}]}
    monkeypatch.setattr(nvidia, "_post", lambda *a, **k: (True, payload, "", 5))
    ok, text, _, _ = nvidia.parse_document("key", b"png")
    assert ok and "hello" in text


def test_parse_date_formats():
    assert parse_date("26/02/2024").strftime("%Y-%m-%d") == "2024-02-26"
    assert parse_date("17.08.2026").strftime("%Y-%m-%d") == "2026-08-17"
    assert parse_date("26th August, 2026").strftime("%Y-%m-%d") == "2026-08-26"
    assert parse_date("19.2.2024").strftime("%Y-%m-%d") == "2024-02-19"
    assert parse_date("28/Aug/2026").strftime("%Y-%m-%d") == "2026-08-28"
    assert parse_date("28-Aug-26").strftime("%Y-%m-%d") == "2026-08-28"
    assert parse_date("32/13/2024") is None
    assert parse_date("") is None


def test_find_dates_handles_ocr_variants():
    assert find_dates("Memo No.57/2026/8, Dated Shillong; the 21 August, 2026.")[0] == "21 August 2026"
    assert find_dates('Dated Shillong, the 21"t August, 2026')[0] == "21 August 2026"
    assert find_dates("Dated Shillong, the 26th August,2026")[0] == "26 August 2026"
    assert find_dates("Date of Reply is on 28.02.2026")[0] == "28.02.2026"
    assert find_dates("letter (..LB.68/LA/22266 dated 07-08-2026")[1] == "07-08-2026"
    assert find_dates("DATE OF REPLY -28.08.2026")[0] == "28.08.2026"
    assert find_dates("Dated Shillong the 21* August, 2026")[0] == "21 August 2026"
    assert find_dates("listed for reply on 2 8 / 0 8 / 2 0 2 6")[0] == ""
    assert find_dates("letter No.LB.79/LA/2026/2 dated 1 4 / 0 8 / 2 0 2 6")[1] == "14/08/2026"


def test_squash_spaced_text():
    assert squash_spaced_text("2 8 / 0 8 / 2 0 2 6") == "28/08/2026"
    assert squash_spaced_text("18 t h August") == "18th August"
    assert squash_spaced_text("listed for reply on") == "listed for reply on"


def test_split_reply_keeps_right_column_skips_full_width():
    words = [(10, 10, 40, 20, "Question?"), (65, 10, 80, 20, "Sir,"),
             (65, 25, 85, 35, "yes."),
             (10, 50, 30, 60, "Memo"), (40, 50, 70, 60, "crosses-split")]
    assert split_reply(words, 110, 100) == "Sir,\nyes."


def test_split_reply_stops_at_footer():
    words = [(10, 10, 40, 20, "Question?"), (65, 10, 80, 20, "Reply text"),
             (65, 50, 100, 60, "By order etc.,"),
             (65, 70, 100, 80, "signature block")]
    assert split_reply(words, 110, 100) == "Reply text"
