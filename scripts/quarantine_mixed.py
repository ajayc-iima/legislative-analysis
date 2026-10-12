"""Quarantine mixed Q&A records: force flagged-empty with a reason note.

Line rules cannot separate interleaved bulletin/question fragments from
reply text on some pages (OCR column smear, mixed bulletin layouts).
Listed records keep their verified dates but their text is withheld so
layer-4 never codes question text as reply. The denylist
(data/review/quarantine_list.csv) is versioned evidence: every entry
carries its reason, decision date and decider. Idempotent: re-running
changes nothing.

Run after every extraction pass, before the analysis chain:
    python scripts/quarantine_mixed.py
"""

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_RUN = Path(r"C:\Users\chou_\AppData\Local\Temp\opencode\extract_run")
DEFAULT_BACKUP = Path(r"C:\Users\chou_\AppData\Local\Temp\opencode\extract_backup")
NOTE = "quarantined: mixed Q&A page - reply text withheld, see data/review/quarantine_list.csv"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN))
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP))
    parser.add_argument("--denylist",
                        default=str(REPO / "data/review/quarantine_list.csv"))
    args = parser.parse_args(argv)

    denied = {}
    with open(args.denylist, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("pdf") or "").strip()
            if name:
                denied[name] = (row.get("reason") or "").strip()

    jsonl = Path(args.run_dir) / "extracted.jsonl"
    lines = jsonl.read_text(encoding="utf-8").splitlines()
    recs = [json.loads(l) for l in lines if l.strip()]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = Path(args.backup_dir)
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(jsonl, backup / f"extracted_full_{ts}.jsonl")

    n_hit, n_already, n_text = 0, 0, 0
    for rec in recs:
        if rec.get("pdf") not in denied:
            continue
        n_hit += 1
        notes = rec.get("needs_review", [])
        if any(n.startswith("quarantined:") for n in notes):
            n_already += 1
            continue
        if (rec.get("reply") or "").strip():
            n_text += 1
        rec["reply"] = ""
        rec["parts"] = []
        notes.append(NOTE)
        rec["needs_review"] = notes

    jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
                     encoding="utf-8")
    print(f"quarantine: {len(denied)} listed, {n_hit} matched, "
          f"{n_text} had text withheld, {n_already} already quarantined")
    return 0


if __name__ == "__main__":
    sys.exit(main())
