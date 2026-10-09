"""Tests for the extraction harness (no live API calls)."""

from legislative_extract import nvidia
from legislative_extract.extract import (cut_footer, find_dates, flag_date_issues,
                                         parse_date, split_parts, split_reply,
                                         squash_spaced_text)
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


def test_adjudicate_two_of_three_wins():
    from legislative_extract.consensus import adjudicate
    readings = [
        {"reader": "ocr", "ok": True, "text": "Dated Shillong, the 14th September, 2023", "error": "", "ms": 1},
        {"reader": "vision", "ok": True, "text": "Dated Shillong, the 14th September, 2023", "error": "", "ms": 1},
        {"reader": "reason", "ok": True, "text": "no dates here", "error": "", "ms": 1},
    ]
    verdict = adjudicate("key", readings, {})
    assert verdict["reply_date"] == "2023-09-14"
    assert verdict["provenance"] == "consensus"


def test_adjudicate_single_vote_goes_to_supervisor(monkeypatch):
    import legislative_extract.consensus as consensus
    readings = [
        {"reader": "ocr", "ok": True, "text": "Dated Shillong, the 14th September, 2023", "error": "", "ms": 1},
    ]
    monkeypatch.setattr(consensus, "supervise", lambda *a, **k: {
        "ok": True, "decision": {"reply_date": "2023-09-14", "submission_date": "",
                                 "confidence": "medium", "rationale": "x"}, "error": "", "ms": 1})
    verdict = consensus.adjudicate("key", readings, {}, sitting_iso="2023-09-16")
    assert verdict["reply_date"] == "2023-09-14"
    assert verdict["provenance"] == "supervisor"


def test_adjudicate_rejects_unsupported_supervisor_pick(monkeypatch):
    import legislative_extract.consensus as consensus
    readings = [
        {"reader": "ocr", "ok": True, "text": "Dated Shillong, the 14th September, 2023", "error": "", "ms": 1},
    ]
    monkeypatch.setattr(consensus, "supervise", lambda *a, **k: {
        "ok": True, "decision": {"reply_date": "2020-01-01", "submission_date": "",
                                 "confidence": "high", "rationale": "x"}, "error": "", "ms": 1})
    verdict = consensus.adjudicate("key", readings, {}, sitting_iso="2023-09-16")
    assert verdict["reply_date"] == ""
    assert verdict["provenance"] == "supervisor-rejected"


def test_adjudicate_keeps_partial_winners(monkeypatch):
    import legislative_extract.consensus as consensus
    readings = [
        {"reader": "ocr", "ok": True, "text": "Dated Shillong, the 14th September, 2023", "error": "", "ms": 1},
        {"reader": "vision", "ok": True, "text": "Dated Shillong, the 14th September, 2023", "error": "", "ms": 1},
    ]
    monkeypatch.setattr(consensus, "supervise", lambda *a, **k: {
        "ok": False, "decision": {}, "error": "down", "ms": 1})
    verdict = consensus.adjudicate("key", readings, {}, sitting_iso="2023-09-16")
    assert verdict["reply_date"] == "2023-09-14"
    assert verdict["submission_date"] == ""
    assert verdict["provenance"] == "consensus"


def test_adjudicate_drops_implausible_consensus(monkeypatch):
    import legislative_extract.consensus as consensus
    readings = [
        {"reader": "ocr", "ok": True, "text": "Dated Shillong, the 14th September, 2033", "error": "", "ms": 1},
        {"reader": "vision", "ok": True, "text": "Dated Shillong, the 14th September, 2033", "error": "", "ms": 1},
    ]
    monkeypatch.setattr(consensus, "supervise", lambda *a, **k: {
        "ok": False, "decision": {}, "error": "down", "ms": 1})
    verdict = consensus.adjudicate("key", readings, {}, sitting_iso="2023-09-16")
    assert verdict["reply_date"] == ""
    assert verdict["provenance"] == "unresolved"


def test_parse_date_formats():
    assert parse_date("26/02/2024").strftime("%Y-%m-%d") == "2024-02-26"
    assert parse_date("17.08.2026").strftime("%Y-%m-%d") == "2026-08-17"
    assert parse_date("26th August, 2026").strftime("%Y-%m-%d") == "2026-08-26"
    assert parse_date("19.2.2024").strftime("%Y-%m-%d") == "2024-02-19"
    assert parse_date("28/Aug/2026").strftime("%Y-%m-%d") == "2026-08-28"
    assert parse_date("28-Aug-26").strftime("%Y-%m-%d") == "2026-08-28"
    assert parse_date("2026-08-28").strftime("%Y-%m-%d") == "2026-08-28"
    assert parse_date("32/13/2024") is None
    assert parse_date("") is None


def test_parse_date_forgives_ocr_month_typos():
    assert parse_date("21 Agust 2026").strftime("%Y-%m-%d") == "2026-08-21"
    assert parse_date("21 Aug 2026").strftime("%Y-%m-%d") == "2026-08-21"
    assert parse_date("21 Xyz 2026") is None
    assert parse_date("12 Sept 2026").strftime("%Y-%m-%d") == "2026-09-12"


def test_find_dates_handles_ocr_variants():
    assert find_dates("Memo No.57/2026/8, Dated Shillong; the 21 August, 2026.")[0] == "21 August 2026"
    assert find_dates('Dated Shillong, the 21"t August, 2026')[0] == "21 August 2026"
    assert find_dates("Dated Shillong, the 26th August,2026")[0] == "26 August 2026"
    assert find_dates("Date of Reply is on 28.02.2026")[0] == "28.02.2026"
    assert find_dates("letter (..LB.68/LA/22266 dated 07-08-2026")[1] == "07-08-2026"
    assert find_dates("Dated, Shillong, the 10th August, 2026")[0] == "10 August 2026"
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
             (10, 50, 30, 60, "Memo No. X"), (40, 50, 70, 60, "dated")]
    assert split_reply(words, 110, 100) == "Sir,\nyes."


def test_split_reply_keeps_wide_left_cells():
    # coarse OCR boxes: question cell ends at 0.50, reply starts at 0.51
    words = [(20, 10, 50, 30, "Question text here"), (51, 10, 87, 30, "Reply text here")]
    assert split_reply(words, 100, 100, side="left") == "Question text here"
    assert split_reply(words, 100, 100) == "Reply text here"


def test_split_reply_skips_short_spanning_line():
    # one short word crossing mid-page means continuous full-width text
    words = [(10, 10, 40, 20, "Question?"), (65, 10, 80, 20, "Sir,"),
             (10, 40, 30, 41, "Title"), (35, 40, 55, 41, "spans"), (60, 40, 100, 41, "width")]
    assert split_reply(words, 110, 100) == "Sir,"


def test_split_reply_skips_full_width_title_box():
    # a single tall box spanning the gutter is a title, not reply content
    words = [(18, 5, 96, 25, "STARRED QUESTIONS TO BE ASKED BY X"),
             (60, 40, 95, 60, "Reply text here")]
    assert split_reply(words, 110, 100) == "Reply text here"


def test_split_reply_stops_at_footer():
    words = [(10, 10, 40, 20, "Question?"), (65, 10, 80, 20, "Reply text"),
             (65, 50, 100, 60, "By order etc.,"),
             (65, 70, 100, 80, "signature block")]
    assert split_reply(words, 110, 100) == "Reply text"


def test_split_reply_left_side():
    words = [(10, 10, 40, 20, "Question?"), (65, 10, 80, 20, "Reply text")]
    assert split_reply(words, 110, 100, side="left") == "Question?"


def test_cut_footer_drops_memo_block():
    text = "Sir, yes.\nDated Shillong, the 26th August, 2026\nMemo No. X\nBy Order"
    assert cut_footer(text) == "Sir, yes."
    assert cut_footer("Sir, yes. No date here.") == "Sir, yes. No date here."
    assert cut_footer("") == ""


def test_split_parts_pairs_by_label():
    q = "Will the Minister state:\n(a) The length?\n(b) Whether fencing done?"
    r = "Shri X to reply:\n(a) Sir, 221.225 Kms.\n(b) Sir, 215.729 Kms done."
    parts = split_parts(q, r)
    assert [(p["part"], p["question"][:12], p["answer"][:12]) for p in parts] == [
        ("a", "The length?", "Sir, 221.225"),
        ("b", "Whether fenc", "Sir, 215.729"),
    ]


def test_split_parts_ignores_mid_sentence_citations():
    q = "(a) Whether prepaid meters?\n(b) Details thereof?"
    r = "Sir, under clause 4(1) (b) of the Regulations, 2019.\nSir, yes."
    assert split_parts(q, r) == [{"part": "", "question": q, "answer": r}]


def test_split_parts_whole_when_unlabeled():
    q = "(a) First? (b) Second?"
    r = "Yes, Sir. Sir, details follow. No, Sir."
    assert split_parts(q, r) == [{"part": "", "question": q, "answer": r}]
    assert split_parts(q, "") == []
    assert split_parts("", "") == []


def test_flag_date_issues_clean_pair():
    from datetime import datetime
    notes = flag_date_issues(datetime(2026, 8, 21), datetime(2026, 8, 7),
                             datetime(2026, 8, 28), [])
    assert notes == []


def test_flag_date_issues_submission_far_from_sitting():
    # regression: a 2016 submission date on a 2026 sitting must be flagged
    from datetime import datetime
    notes = flag_date_issues(datetime(2026, 8, 20), datetime(2016, 8, 17),
                             datetime(2026, 8, 28), [])
    assert any("submission date" in n and "far from sitting" in n for n in notes)


def test_flag_date_issues_reply_before_submission():
    from datetime import datetime
    notes = flag_date_issues(datetime(2026, 8, 5), datetime(2026, 8, 10),
                             datetime(2026, 8, 28), [])
    assert notes == ["reply date precedes submission date"]


def test_flag_date_issues_tolerates_missing():
    notes = flag_date_issues(None, None, None, [])
    assert notes == []


def test_flag_date_issues_dedupes_on_refill():
    from datetime import datetime
    notes = flag_date_issues(datetime(2026, 8, 5), datetime(2026, 8, 10),
                             datetime(2026, 8, 28), [])
    renotes = flag_date_issues(datetime(2026, 8, 5), datetime(2026, 8, 10),
                               datetime(2026, 8, 28), notes)
    assert renotes == ["reply date precedes submission date"]


def test_acquire_lock_single_instance(tmp_path):
    import os
    from legislative_extract.extract import _acquire_lock
    first = _acquire_lock(tmp_path)
    assert first is not None and first.exists()
    assert _acquire_lock(tmp_path) is None  # live PID holds it
    first.unlink()


def test_acquire_lock_reaps_stale_pid(tmp_path):
    from legislative_extract.extract import _acquire_lock, _pid_alive
    assert _pid_alive(2 ** 30) is False  # no such process
    (tmp_path / "extract.lock").write_text("1073741824", encoding="utf-8")
    assert _acquire_lock(tmp_path) is not None  # stale lock reaped


def test_validate_lock_accepts_own_pid(tmp_path):
    import os
    from legislative_extract.extract import _validate_lock
    lock = tmp_path / "extract.lock"
    lock.write_text(str(os.getpid()), encoding="utf-8")
    assert _validate_lock(lock) is True


def test_validate_lock_rejects_superseded(tmp_path):
    from legislative_extract.extract import _validate_lock
    lock = tmp_path / "extract.lock"
    lock.write_text("1073741824", encoding="utf-8")
    assert _validate_lock(lock) is False


def test_render_page_retries_lower_dpi(monkeypatch):
    import io as stdlib_io
    import pymupdf
    from PIL import Image as PILImage
    from legislative_extract import nvidia as nvidia_mod
    calls = []

    class FakePix:
        def tobytes(self, fmt):
            return b"fakepng"

    class FakePage:
        def get_pixmap(self, dpi):
            calls.append(dpi)
            if dpi > 100:
                raise PILImage.DecompressionBombError("too big")
            return FakePix()

    class FakeDoc:
        def __getitem__(self, i):
            return FakePage()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pymupdf, "open", lambda *a, **k: FakeDoc())
    assert nvidia_mod.render_page("whatever.pdf", dpi=200) == b"fakepng"
    assert calls[0] == 200 and calls[-1] <= 100


def test_render_page_survives_downscale_bomb(monkeypatch):
    """The bomb fires in Image.open (downscale step), not the rasterizer."""
    import io
    import os
    import pymupdf
    from PIL import Image as PILImage
    from legislative_extract import nvidia as nvidia_mod
    dpis = []

    big = io.BytesIO()
    PILImage.frombytes("RGB", (400, 400),
                       os.urandom(400 * 400 * 3)).save(big, format="PNG")
    big_png = big.getvalue()
    assert len(big_png) > 100

    class FakePix:
        def tobytes(self, fmt):
            return big_png

    class FakePage:
        def get_pixmap(self, dpi):
            dpis.append(dpi)
            return FakePix()

    class FakeDoc:
        def __getitem__(self, i):
            return FakePage()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    real_open = PILImage.open
    calls = []

    def bomb_once(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise PILImage.DecompressionBombError("too big")
        return real_open(*a, **k)

    monkeypatch.setattr(pymupdf, "open", lambda *a, **k: FakeDoc())
    monkeypatch.setattr(PILImage, "open", bomb_once)
    out = nvidia_mod.render_page("whatever.pdf", dpi=200, max_bytes=100)
    assert dpis[0] == 200 and len(dpis) >= 2  # fell through to lower DPI
    assert isinstance(out, bytes) and out


def test_run_aborts_on_volume_failure(tmp_path, monkeypatch):
    from pathlib import Path as PathCls
    from legislative_extract import extract as ext_mod
    csv_path = tmp_path / "q.csv"
    csv_path.write_text("Document_Link,Session,Session_Date,Question_Number\n"
                        "http://x/a.pdf,S1,01/Jan/2026,Q.No 1\n", encoding="utf-8")

    def boom(self, pattern):
        raise OSError(433, "device does not exist")
    monkeypatch.setattr(PathCls, "rglob", boom)
    assert ext_mod.run(str(csv_path), str(tmp_path / "pdfs"),
                       str(tmp_path / "out"), "key") == 3


def test_consensus_fill_survives_render_failure(tmp_path, monkeypatch):
    import pymupdf
    from legislative_extract import extract as ext_mod
    from legislative_extract import nvidia as nvidia_mod
    pdf = tmp_path / "x.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "hello")
    doc.save(str(pdf))
    doc.close()
    monkeypatch.setattr(nvidia_mod, "render_page",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))
    record = {"reply_date": "", "submission_date": "", "needs_review": []}
    assert ext_mod.consensus_fill(str(pdf), "key", record, {}) is False


def test_run_skips_directory_matches(tmp_path):
    from legislative_extract import extract as ext_mod
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()
    (pdf_root / "a.pdf").mkdir()  # directory, not a file
    csv_path = tmp_path / "q.csv"
    csv_path.write_text("Document_Link,Session,Session_Date,Question_Number\n"
                        "http://x/a.pdf,S1,01/Jan/2026,Q.No 1\n", encoding="utf-8")
    assert ext_mod.run(str(csv_path), str(pdf_root), str(tmp_path / "out"), "key") == 0
    content = (tmp_path / "out" / "extracted.jsonl").read_text(encoding="utf-8")
    assert content == ""  # directory match skipped: nothing extracted, nothing failed


def test_run_survives_failing_pdf(tmp_path, monkeypatch):
    from legislative_extract import extract as ext_mod
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()
    (pdf_root / "a.pdf").write_bytes(b"%PDF-1.4 fake")
    (pdf_root / "b.pdf").write_bytes(b"%PDF-1.4 fake")
    csv_path = tmp_path / "q.csv"
    csv_path.write_text("Document_Link,Session,Session_Date,Question_Number\n"
                        "http://x/a.pdf,S1,01/Jan/2026,Q.No 1\n"
                        "http://x/b.pdf,S1,01/Jan/2026,Q.No 2\n", encoding="utf-8")

    def boom(pdf_path, key, session_date=""):
        if pdf_path.endswith("a.pdf"):
            raise RuntimeError("bad scan")
        return {"pdf": "b.pdf", "reply": "Sir, yes.", "parts": [],
                "reply_date": "2026-01-05", "reply_date_raw": "",
                "submission_date": "", "submission_date_raw": "",
                "pages_ocr": 0, "needs_review": []}

    monkeypatch.setattr(ext_mod, "extract_pdf", boom)
    monkeypatch.setattr(ext_mod, "consensus_fill", lambda *a, **k: False)
    assert ext_mod.run(str(csv_path), str(pdf_root), str(tmp_path / "out"), "key") == 0
    lines = (tmp_path / "out" / "extracted.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and '"b.pdf"' in lines[0]
    assert "a.pdf" in (tmp_path / "out" / "extract_errors.jsonl").read_text(encoding="utf-8")
