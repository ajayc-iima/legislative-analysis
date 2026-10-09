"""Supervisor smoke matrix: DIRECT supervise calls only.

Lesson from trial v1: adjudicate-level smokes never exercise the
supervisor (the vote decides first). Here each model is called
directly on disagreement-rich readings (4088: reply 24th vs 28th,
submission 14th), retries=0, measuring: served?, latency, format
compliance, decision supported by the readings?

Usage: python scripts/supervisor_smoke.py
"""

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/extract/src"))

from legislative_extract import consensus, nvidia  # noqa: E402
from legislative_extract.consensus import reading_dates  # noqa: E402

PDF = "assembly-11/autumn-session-2026/11_9_S_4088_V1_signed.pdf"
CANDIDATES = [
    ("lightning-strict", "nvidia/nemotron-3.5-lightning-30b-a3b", "json"),
    ("muse-glimmer-30b", "meta/muse-glimmer-30b", "json"),
    ("mistral-nemo-12b", "nv-mistralai/mistral-nemo-12b-instruct", "json"),
    ("minitron-8b", "nvidia/mistral-nemo-minitron-8b-8k-instruct", "json"),
    ("gemma-3-12b", "google/gemma-3-12b-it", "json"),
    ("glm-flash", "z-ai/glm-5.3-flash", "json"),
    ("deepseek-flash", "deepseek-ai/deepseek-v4.1-flash", "json"),
]


def main():
    key = nvidia.load_key()
    png = nvidia.render_page(str(REPO / "data/pdfs" / PDF), page=0, dpi=200)
    readings = [consensus.read_ocr(key, png)]
    time.sleep(0.4)
    ok_parse, parse_text, _, _ = nvidia.parse_document(key, png)
    readings.append({"reader": "parse", "ok": ok_parse, "text": parse_text,
                     "error": "", "ms": 0})
    time.sleep(0.4)
    readings.append(consensus.read_vision(key, png))
    supported = sorted({d for r in readings if r["ok"]
                        for d in reading_dates(r) if d})
    print(f"supported dates: {supported}", flush=True)
    context = {"session": "Autumn Session, 2026", "sitting_date": "28/Aug/2026"}
    for label, model, style in CANDIDATES:
        consensus.SUPERVISOR = model
        t0 = time.time()
        try:
            out = consensus.supervise(key, readings, context, retries=0,
                                      prompt_style=style)
        except Exception as exc:  # noqa: BLE001 — endpoint probe
            print(f"[{label:18} ----] EXC {exc!r}", flush=True)
            continue
        dt = time.time() - t0
        dec = out.get("decision", {}) if out["ok"] else {}
        picks = [dec.get("reply_date", ""), dec.get("submission_date", "")]
        verdict = ("INVENTED" if any(p and p not in supported for p in picks)
                   else ("SUPPORTED" if any(picks) else "ABSTAIN"))
        print(f"[{label:18} {dt:5.1f}s] ok={out['ok']!s:5} {verdict:9} "
              f"r={picks[0] or '-':12} s={picks[1] or '-':12} "
              f"{str(out.get('error', ''))[:70]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
