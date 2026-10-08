"""Model consensus for uncertain extractions (review queue only).

Three blind readers + one supervisor. Readers never see each other's
output or any candidate date. Agreement is mechanical (2-of-3 on
normalized ISO dates), then validators gate acceptance. The supervisor
only adjudicates disagreements, using CSV context for plausibility —
it cannot invent: winners must appear in ≥1 reading and pass parsing.
"""

import json
import re
import time

from . import nvidia
from .extract import find_dates, parse_date
from .trial import ocr_text

READER_OCR = "nvidia/nemotron-ocr-v1"
READER_VISION = "meta/llama-3.2-11b-vision-instruct"
SUPERVISOR = "nvidia/nemotron-3.5-lightning-30b-a3b"
PAUSE_SECONDS = 0.4


def read_ocr(key, png):
    ok, text, error, ms = ocr_text(key, READER_OCR, png)
    return {"reader": "ocr", "ok": ok, "text": text, "error": error, "ms": ms}


def read_vision(key, png):
    ok, payload, error, ms = nvidia.chat_vl(
        key, READER_VISION, png,
        "Transcribe verbatim every line on this page that contains a date, "
        "a memo number, or the words reply, dated, letter, reference, "
        "notice. Quote exact lines, nothing else.",
        max_tokens=800)
    text = ""
    if ok:
        text = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return {"reader": "vision", "ok": ok, "text": str(text), "error": error, "ms": ms}


def read_parse(key, png):
    """Independent reader: nemotron-parse markdown (different engine)."""
    ok, text, error, ms = nvidia.parse_document(key, png)
    return {"reader": "parse", "ok": ok, "text": text, "error": error, "ms": ms}


def reading_dates(reading):
    """(reply_iso, submission_iso) from one reading's text."""
    reply_raw, sub_raw = find_dates(reading["text"])
    reply = parse_date(reply_raw)
    sub = parse_date(sub_raw)
    return (reply.strftime("%Y-%m-%d") if reply else "",
            sub.strftime("%Y-%m-%d") if sub else "")


def supervise(key, readings, csv_context, retries=1):
    """Reasoning supervisor: decides from blind readings + CSV context.

    Retries once on empty/non-JSON answers. Every pick is still gated by
    the support rule in adjudicate (must appear in ≥1 reading).
    """
    shown = []
    for i, reading in enumerate(readings):
        shown.append(f"--- Reading {chr(65 + i)} ---\n{reading['text'][:1500]}")
    prompt = (
        "Three independent readings (A, B, C) of one legislative reply page "
        "are shown. Using them plus the official record below, decide the "
        "reply date and the submission date. Prefer dates appearing in at "
        "least two readings; use the record only for plausibility (dates "
        "should fall near the sitting date). Never invent a date: if none "
        "is supported, use empty strings. First reason briefly, then reply "
        "with a JSON object on its own line: "
        '{"reply_date": "YYYY-MM-DD or empty", '
        '"submission_date": "YYYY-MM-DD or empty", '
        '"confidence": "high/medium/low", "rationale": "one line"}\n\n'
        f"Official record: {json.dumps(csv_context)}\n\n" + "\n".join(shown))
    error, ms_total, attempt = "", 0, 0
    while attempt <= retries:
        ok, payload, err, ms = nvidia._post(
            nvidia.CHAT_URL, key,
            {"model": SUPERVISOR,
             "messages": [{"role": "user", "content": prompt}],
             "temperature": 0, "max_tokens": 500})
        ms_total += ms
        if not ok:
            error = err
            break
        content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        match = re.search(r"\{[^{}]*\"reply_date\"[^{}]*\}", str(content), re.S)
        try:
            decision = json.loads(match.group(0)) if match else {}
            if decision.get("reply_date") or decision.get("submission_date"):
                return {"ok": True, "decision": decision, "error": "", "ms": ms_total}
            error = f"empty decision: {content[:150]}"
        except ValueError:
            error = f"non-JSON: {content[:150]}"
        attempt += 1
        time.sleep(PAUSE_SECONDS)
    return {"ok": False, "decision": {}, "error": error, "ms": ms_total}


def valid_iso(value):
    try:
        return bool(value and len(value) == 10 and parse_date(value))
    except (ValueError, TypeError):
        return False


def adjudicate(key, readings, csv_context, sitting_iso=""):
    """Full consensus: 2-of-3 agreement wins; else supervisor decides.

    Returns {reply_date, submission_date, confidence, provenance}.
    Every winner passes all gates inside this function: parseable,
    reply >= submission, and within 120 days of the sitting date.
    Anything failing a gate is dropped before confidence is assigned.
    """
    sitting = parse_date(sitting_iso) if sitting_iso else None

    def plausible(iso):
        day = parse_date(iso) if iso else None
        if not day:
            return False
        if sitting and abs((day - sitting).days) > 120:
            return False
        return True

    time.sleep(PAUSE_SECONDS)
    dates = [reading_dates(r) for r in readings if r["ok"]]
    votes_reply, votes_sub = {}, {}
    for reply_iso, sub_iso in dates:
        if reply_iso and plausible(reply_iso):
            votes_reply[reply_iso] = votes_reply.get(reply_iso, 0) + 1
        if sub_iso and plausible(sub_iso):
            votes_sub[sub_iso] = votes_sub.get(sub_iso, 0) + 1
    winners = {}
    for field, votes in (("reply_date", votes_reply), ("submission_date", votes_sub)):
        top = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))
        if top and top[0][1] >= 2:
            winners[field] = (top[0][0], "high" if len(dates) >= 3 else "medium")
    reply_iso = winners.get("reply_date", ("", ""))[0]
    sub_iso = winners.get("submission_date", ("", ""))[0]
    parts = ["consensus"] if winners else []
    decision = {}
    if "reply_date" not in winners or "submission_date" not in winners:
        time.sleep(PAUSE_SECONDS)
        result = supervise(key, readings, csv_context)
        decision = result.get("decision", {}) if result["ok"] else {}
        supported = {d for pair in dates for d in pair if d}
        if "reply_date" not in winners:
            candidate = decision.get("reply_date", "") or ""
            if candidate in supported and plausible(candidate):
                reply_iso = candidate
                parts.append("supervisor")
            elif candidate:
                parts.append("supervisor-rejected")
        if "submission_date" not in winners:
            candidate = decision.get("submission_date", "") or ""
            if candidate in supported and plausible(candidate):
                sub_iso = candidate
                parts.append("supervisor")
            elif candidate:
                parts.append("supervisor-rejected")
    if reply_iso and sub_iso and reply_iso < sub_iso:
        return {"reply_date": "", "submission_date": "",
                "confidence": "low", "provenance": "rejected-order",
                "readings": [r["reader"] for r in readings if r["ok"]]}
    confidence = decision.get("confidence", "low") if "supervisor" in parts else (
        winners.get("reply_date", ("", "low"))[1] if winners else "low")
    provenance = "+".join(parts) if parts else "unresolved"
    return {"reply_date": reply_iso if valid_iso(reply_iso) else "",
            "submission_date": sub_iso if valid_iso(sub_iso) else "",
            "confidence": confidence, "provenance": provenance,
            "readings": [r["reader"] for r in readings if r["ok"]]}
    if reply_iso and sub_iso and reply_iso < sub_iso:
        return {"reply_date": "", "submission_date": "",
                "confidence": "low", "provenance": "rejected-order",
                "readings": [r["reader"] for r in readings if r["ok"]]}
    confidence = decision.get("confidence", "low") if "supervisor" in parts else (
        winners.get("reply_date", ("", "low"))[1] if winners else "low")
    provenance = "+".join(parts) if parts else "unresolved"
    return {"reply_date": reply_iso if valid_iso(reply_iso) else "",
            "submission_date": sub_iso if valid_iso(sub_iso) else "",
            "confidence": confidence, "provenance": provenance,
            "readings": [r["reader"] for r in readings if r["ok"]]}
