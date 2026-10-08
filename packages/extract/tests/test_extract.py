"""Tests for the extraction harness (no live API calls)."""

from legislative_extract import nvidia
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
