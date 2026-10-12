"""Tests for scripts/quarantine_mixed.py (no live API calls)."""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import quarantine_mixed


def _setup(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    recs = [
        {"pdf": "mixed.pdf", "reply": "STARRED QUESTIONS TO BE ASKED",
         "parts": [{"part": "", "question": "q", "answer": "a"}],
         "reply_date": "2024-01-01", "submission_date": "2023-12-01",
         "needs_review": ["empty reply text"]},
        {"pdf": "clean.pdf", "reply": "Sir, yes.", "parts": [],
         "reply_date": "", "submission_date": "", "needs_review": []},
    ]
    (run_dir / "extracted.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    deny = tmp_path / "deny.csv"
    with deny.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, ["pdf", "reason", "decided", "decided_by"])
        writer.writeheader()
        writer.writerow({"pdf": "mixed.pdf", "reason": "mixed page",
                         "decided": "2026-10-12", "decided_by": "test"})
    return run_dir, backup_dir, deny


def _load(run_dir):
    return {json.loads(l)["pdf"]: json.loads(l) for l in
            (run_dir / "extracted.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()}


def test_quarantine_withholds_text_keeps_dates(tmp_path, capsys):
    run_dir, backup_dir, deny = _setup(tmp_path)
    assert quarantine_mixed.main(["--run-dir", str(run_dir),
                                  "--backup-dir", str(backup_dir),
                                  "--denylist", str(deny)]) == 0
    recs = _load(run_dir)
    assert recs["mixed.pdf"]["reply"] == ""
    assert recs["mixed.pdf"]["parts"] == []
    assert recs["mixed.pdf"]["reply_date"] == "2024-01-01"
    assert any(n.startswith("quarantined:") for n in recs["mixed.pdf"]["needs_review"])
    assert recs["clean.pdf"]["reply"] == "Sir, yes."
    assert list(backup_dir.glob("extracted_full_*.jsonl"))
    assert "1 had text withheld" in capsys.readouterr().out


def test_quarantine_idempotent(tmp_path, capsys):
    run_dir, backup_dir, deny = _setup(tmp_path)
    args = ["--run-dir", str(run_dir), "--backup-dir", str(backup_dir),
            "--denylist", str(deny)]
    quarantine_mixed.main(args)
    quarantine_mixed.main(args)
    recs = _load(run_dir)
    notes = [n for n in recs["mixed.pdf"]["needs_review"]
             if n.startswith("quarantined:")]
    assert len(notes) == 1
    assert "already quarantined" in capsys.readouterr().out
