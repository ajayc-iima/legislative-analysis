"""Trial harness: run OCR models over the stratified sample, score vs ground truth.

Each model extracts page-1 text; scoring is substring matching of the
hand-transcribed fields (memo, dates, minister surname, reply excerpt,
table cells). Failures are recorded, never raised.
"""

import json
import re
import time
from pathlib import Path

from . import nvidia

OCR_MODELS = [
    "nvidia/nemotron-ocr-v1",
    "nvidia/nemotron-ocr-v2",
    "baidu/paddleocr",
]


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def ocr_text(key, model, png):
    """Page text from a CV OCR model: detections sorted top-to-bottom, left-to-right."""
    ok, payload, error, ms = nvidia.cv_model(key, model, png)
    if not ok:
        return ok, "", error, ms
    try:
        detections = (payload.get("data") or [{}])[0].get("text_detections") or []
        items = []
        for det in detections:
            points = ((det.get("bounding_box") or {}).get("points") or [])
            if not points:
                continue
            ys = [p["y"] for p in points]
            xs = [p["x"] for p in points]
            items.append(((min(ys), min(xs)), (det.get("text_prediction") or {}).get("text", "")))
        items.sort()
        return True, " ".join(t for _, t in items), "", ms
    except (KeyError, IndexError, TypeError) as exc:
        return False, "", f"unexpected shape: {exc}", ms


def parse_text(key, png):
    """Page markdown from nemotron-parse (tool-call arguments)."""
    return nvidia.parse_document(key, png)


def score_text(text, truth):
    """Per-field hit/miss against hand-transcribed ground truth."""
    flat = _norm(text)
    checks = {}
    for field in ("memo", "reply_date", "scheduled", "minister", "excerpt"):
        want = truth.get(field, "")
        checks[field] = (not want) or (_norm(want) in flat)
    for cell in truth.get("table_cells", []):
        checks[f"table:{cell}"] = _norm(cell) in flat
    return checks


def run_trial(pdf_root, ground_truth, key, dpi=200, pause=1.0):
    """Run every OCR model over every sample page. Returns the scorecard dict."""
    results = {"models": {}, "pages": {}}
    runners = {m: (lambda m: lambda png: ocr_text(key, m, png))(m) for m in OCR_MODELS}
    runners["nvidia/nemotron-parse"] = lambda png: parse_text(key, png)
    for entry in ground_truth:
        pdf = str(Path(pdf_root) / entry["pdf"])
        png = nvidia.render_page(pdf, page=0, dpi=dpi)
        page = {"file": entry["pdf"], "png_bytes": len(png), "models": {}}
        for model, run in runners.items():
            ok, text, error, ms = run(png)
            checks = score_text(text, entry) if ok else {}
            page["models"][model] = {"ok": ok, "ms": ms, "chars": len(text),
                                     "error": error[:200], "checks": checks}
            time.sleep(pause)
        results["pages"][entry["id"]] = page
    for model in runners:
        hits = total = 0
        ms_total, fails = 0, 0
        for page in results["pages"].values():
            result = page["models"][model]
            if not result["ok"]:
                fails += 1
                continue
            ms_total += result["ms"]
            for field, hit in result["checks"].items():
                total += 1
                hits += hit
        results["models"][model] = {"accuracy": round(hits / total, 3) if total else 0.0,
                                    "checked": total, "failed_pages": fails,
                                    "avg_ms": ms_total // max(len(results["pages"]) - fails, 1)}
    return results


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Run the OCR model trial")
    parser.add_argument("--pdf-root", default="data/pdfs")
    parser.add_argument("--truth", default="trial_ground_truth.json")
    parser.add_argument("--out", default="trial_scorecard.json")
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args(argv)
    key = nvidia.load_key()
    if not key:
        print("No NVIDIA API key (env NVIDIA_API_KEY or legacy config).")
        return 1
    with open(args.truth, encoding="utf-8") as handle:
        truth = json.load(handle)
    results = run_trial(args.pdf_root, truth, key, dpi=args.dpi)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=1)
    for model, summary in results["models"].items():
        print(f"{model:32} acc={summary['accuracy']:.3f} "
              f"failed={summary['failed_pages']} avg={summary['avg_ms']}ms")
    print(f"saved {args.out}")
    return 0
