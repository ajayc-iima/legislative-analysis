"""Supervisor speed trial: fastest candidates vs the 12-page hand-truth gate.

Readings (ocr + parse + vision) are done ONCE and cached — they don't
depend on the supervisor. Each candidate then adjudicates the same
readings. Ship criterion: >=11/12 reply dates, 0 confident errors
(a confident wrong answer disqualifies immediately).

Usage: python scripts/supervisor_trial.py
"""

import csv
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/extract/src"))

from legislative_extract import consensus, nvidia  # noqa: E402
from legislative_extract.extract import parse_date  # noqa: E402

CANDIDATES = [
    "mistralai/mistral-7b-instruct-v0.3",
    "google/gemma-3-4b-it",
]
GATE_MIN, GATE_CONFIDENT_WRONG = 11, 0

TRUTH = json.loads((REPO / "packages/extract/trial_ground_truth.json").read_text(encoding="utf-8"))


def load_rows():
    with open(REPO / "data/dl_questions_raw.csv", encoding="utf-8-sig") as handle:
        return {r["Document_Link"].rsplit("/", 1)[-1]: r for r in csv.DictReader(handle)}


def collect_readings(key, rows):
    """One full read pass over the 12 pages (slow; done once)."""
    cached = []
    for entry in TRUTH:
        name = entry["pdf"].rsplit("/", 1)[-1]
        pdf = str(REPO / "data/pdfs" / entry["pdf"])
        png = nvidia.render_page(pdf, page=0, dpi=200)
        readings = [consensus.read_ocr(key, png)]
        time.sleep(0.4)
        ok_parse, parse_text, _, _ = nvidia.parse_document(key, png)
        readings.append({"reader": "parse", "ok": ok_parse, "text": parse_text,
                         "error": "", "ms": 0})
        time.sleep(0.4)
        readings.append(consensus.read_vision(key, png))
        row = rows.get(name, {})
        cached.append({"entry": entry, "readings": readings, "row": row})
        print(f"  read {entry['id']}: {[r['reader'] for r in readings if r['ok']]}", flush=True)
    return cached


def smoke(key, cached, model):
    """One adjudication to verify the endpoint serves before the full run."""
    consensus.SUPERVISOR = model
    item = cached[0]
    row = item["row"]
    context = {"session": row.get("Session"), "sitting_date": row.get("Session_Date")}
    t0 = time.time()
    try:
        verdict = consensus.adjudicate(key, item["readings"], context,
                                       sitting_iso=row.get("Session_Date", ""))
    except Exception as exc:  # noqa: BLE001 — endpoint probe, report and move on
        return False, 0.0, repr(exc)
    return True, time.time() - t0, verdict


def trial(key, cached, model):
    consensus.SUPERVISOR = model
    rows_out, sup_ms, correct, confident_wrong = [], [], 0, 0
    for item in cached:
        entry, readings, row = item["entry"], item["readings"], item["row"]
        context = {"session": row.get("Session"), "sitting_date": row.get("Session_Date"),
                   "department": row.get("Departments"), "mla": row.get("Asked_By"),
                   "subject": (row.get("Subject") or "")[:120]}
        t0 = time.time()
        verdict = consensus.adjudicate(key, readings, context,
                                       sitting_iso=row.get("Session_Date", ""))
        dt = time.time() - t0
        want = parse_date(entry.get("reply_date", ""))
        want_r = want.strftime("%Y-%m-%d") if want else ""
        got_r = verdict["reply_date"]
        if got_r == want_r:
            correct += 1
        elif got_r and verdict["confidence"] == "high":
            confident_wrong += 1
        rows_out.append({"id": entry["id"], "want_r": want_r, "got_r": got_r,
                         "conf": verdict["confidence"], "prov": verdict["provenance"],
                         "secs": round(dt, 1)})
        print(f"  {entry['id']}: want={want_r or '-':12} got={got_r or '-':12} "
              f"conf={verdict['confidence']:6} prov={verdict['provenance']:28} {dt:.1f}s",
              flush=True)
    return {"model": model, "correct": correct, "total": len(cached),
            "confident_wrong": confident_wrong,
            "mean_secs": round(sum(r["secs"] for r in rows_out) / len(rows_out), 1),
            "rows": rows_out}


def main():
    key = nvidia.load_key()
    rows = load_rows()
    print("Phase 1: readings (once, ~6 min)...", flush=True)
    cached = collect_readings(key, rows)
    results = []
    for model in CANDIDATES:
        print(f"Phase 2: smoke {model}...", flush=True)
        ok, dt, info = smoke(key, cached, model)
        print(f"  smoke: ok={ok} {dt:.1f}s {info if not ok else ''}", flush=True)
        if not ok:
            results.append({"model": model, "error": str(info)})
            continue
        print(f"Phase 3: full gate {model}...", flush=True)
        res = trial(key, cached, model)
        res["pass"] = res["correct"] >= GATE_MIN and res["confident_wrong"] <= GATE_CONFIDENT_WRONG
        results.append(res)
        print(f"  => {res['correct']}/{res['total']} confident-wrong={res['confident_wrong']} "
              f"mean={res['mean_secs']}s pass={res['pass']}", flush=True)
    dest = REPO / "output/validation/supervisor_trial.json"
    dest.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"wrote {dest}")
    passing = [r for r in results if r.get("pass")]
    if passing:
        best = min(passing, key=lambda r: r["mean_secs"])
        print(f"RECOMMEND: {best['model']} ({best['correct']}/{best['total']}, "
              f"{best['mean_secs']}s/page)")
    else:
        print("RECOMMEND: hold (no candidate passed the gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
