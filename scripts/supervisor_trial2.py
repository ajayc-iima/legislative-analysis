"""Supervisor trial v2: genuine disagreements, three models, judged truth.

v1 was vacuous (the vote decided everything; supervisors never fired).
v2 takes 8 real cases where supervision engaged, feeds IDENTICAL
readings to mistral-7b, gemma-4b and lightning-30b, and prints the
date-bearing source lines so the correct answer can be judged from
the source text — not from any pipeline output.

Usage: python scripts/supervisor_trial2.py
"""

import csv
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/extract/src"))

from legislative_extract import consensus, nvidia  # noqa: E402
from legislative_extract.consensus import reading_dates  # noqa: E402

PDFS = [
    "assembly-11/autumn-session-2026/11_9_S_4079_V1_signed.pdf",
    "assembly-11/autumn-session-2026/11_9_S_4088_V1_signed.pdf",
    "assembly-11/autumn-session-2026/11_9_US_4146_V1_signed.pdf",
    "assembly-11/autumn-session-2026/11_9_S_4169_V1_signed.pdf",
    "assembly-11/autumn-session-2026/11_9_S_4171_V2_signed.pdf",
    "assembly-11/autumn-session-2026/11_9_US_4168_V1_signed.pdf",
    "assembly-11/autumn-session-2026/11_9_US_3967_V1_signed.pdf",
    "assembly-11/autumn-session-2026/11_9_US_4239_V1_signed.pdf",
]
MODELS = [
    "mistralai/mistral-7b-instruct-v0.3",
    "google/gemma-3-4b-it",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
]


def date_lines(text, limit=12):
    import re
    out = []
    for line in str(text).splitlines():
        if re.search(r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\b\d{4}\b|ated\b|ated,|eference|otice", line):
            s = " ".join(line.split())
            if len(s) > 25:
                out.append(s[:160])
        if len(out) >= limit:
            break
    return out


def main():
    key = nvidia.load_key()
    with open(REPO / "data/dl_questions_raw.csv", encoding="utf-8-sig") as handle:
        rows = {r["Document_Link"].rsplit("/", 1)[-1]: r for r in csv.DictReader(handle)}
    results = []
    for pdf_rel in PDFS:
        name = pdf_rel.rsplit("/", 1)[-1]
        png = nvidia.render_page(str(REPO / "data/pdfs" / pdf_rel), page=0, dpi=200)
        readings = [consensus.read_ocr(key, png)]
        time.sleep(0.4)
        ok_parse, parse_text, _, _ = nvidia.parse_document(key, png)
        readings.append({"reader": "parse", "ok": ok_parse, "text": parse_text,
                         "error": "", "ms": 0})
        time.sleep(0.4)
        readings.append(consensus.read_vision(key, png))
        row = rows.get(name, {})
        context = {"session": row.get("Session"), "sitting_date": row.get("Session_Date"),
                   "department": row.get("Departments"), "mla": row.get("Asked_By"),
                   "subject": (row.get("Subject") or "")[:120]}
        votes = [reading_dates(r) for r in readings if r["ok"]]
        supported = sorted({d for pair in votes for d in pair if d})
        print(f"\n{'=' * 100}\n{name}  supported={supported}", flush=True)
        for r in readings:
            if r["ok"]:
                print(f"--- {r['reader']} dates={reading_dates(r)}", flush=True)
                for line in date_lines(r["text"]):
                    print(f"    {line}", flush=True)
        case = {"pdf": name, "supported": supported, "decisions": {}}
        for model in MODELS:
            consensus.SUPERVISOR = model
            t0 = time.time()
            try:
                out = consensus.supervise(key, readings, context)
            except Exception as exc:  # noqa: BLE001 — endpoint probe
                out = {"ok": False, "decision": {}, "error": repr(exc)}
            dt = time.time() - t0
            dec = out.get("decision", {}) if out["ok"] else {}
            case["decisions"][model] = {
                "ok": out["ok"], "secs": round(dt, 1),
                "reply_date": dec.get("reply_date", ""),
                "submission_date": dec.get("submission_date", ""),
                "confidence": dec.get("confidence", ""),
                "rationale": str(dec.get("rationale", ""))[:120],
                "error": str(out.get("error", ""))[:120],
            }
            print(f"  [{model.split('/')[-1]:28} {dt:5.1f}s] "
                  f"r={dec.get('reply_date', '') or '-':12} "
                  f"s={dec.get('submission_date', '') or '-':12} "
                  f"{str(out.get('error', ''))[:60]}", flush=True)
        results.append(case)
    dest = REPO / "output/validation/supervisor_trial2.json"
    dest.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
