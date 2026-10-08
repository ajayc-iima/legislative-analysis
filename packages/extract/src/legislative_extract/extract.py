"""Three-field reply extraction: reply text, reply date, submission date.

Method (no LLM): word boxes from the text layer (free) or ocr-v1
(trial winner, 0.937) feed a per-line column split — right side is the
reply in both portal layouts (Q/R tables and two-column pages).
Full-width lines (memo, copy-to) are skipped via the straddle test.
Dates come from regexes over all pages; validators decide approval.
"""

import argparse
import csv
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import nvidia

OCR_MODEL = "nvidia/nemotron-ocr-v1"
NATIVE_MIN_CHARS = 200
MAX_OCR_PAGES = 8
PAUSE_SECONDS = 0.4

MONTHS = {m.lower(): i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}

def squash_spaced_text(text):
    """Collapse OCR-inserted spaces inside dates/words: '2 8 / 0 8' -> '28/08'.

    Only joins single characters and digit runs, so normal word spacing is
    untouched. Applied to a copy used for date search.
    """
    for _ in range(3):
        text = re.sub(r"(?<!\d)(\d)\s+(?=\d(?!\d))", r"\1", text)
        text = re.sub(r"\s+(?=/)", "", text)
        text = re.sub(r"([/])\s+(?=\d)", r"\1", text)
        text = re.sub(r"\b([A-Za-z])\s+(?=[A-Za-z]\b)", r"\1", text)
        text = re.sub(r"\b(\d{1,2})\s+(?=(?:st|nd|rd|th)\b)", r"\1", text)
    return text


REPLY_DATE = [
    re.compile(r"date\s+of\s+(?:reply|discussion)(?:\s+is\s+on)?\s*[-:]?\s*(\d{1,2}[/\-.,]\d{1,2}[/\-.,]\d{2,4})", re.I),
    re.compile(r"dated\s*:?,?\s*(?:[A-Za-z]+[;,]?\s+)?(?:the\s+)?(\d{1,2})[a-z\"'*.(]{0,6}\s+([A-Za-z]+),?\s*(\d{4})", re.I),
    re.compile(r"dated\s*:?\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", re.I),
]
SUBMISSION_DATE = [
    re.compile(r"(?:letter|reference|question)[^\n]{0,120}?(?:No\.?\s*\.?\s*)?(?:[A-Z]{1,4}\.?\s*\d[^\n,]{0,40}?)[,]?\s*dated?\.?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})", re.I),
    re.compile(r"\b[Dd]t\.?\s*(\d{1,2}(?:st|nd|rd|th)?[\s.]+(?:[A-Za-z]+|\d{1,2})[\s.,/]+\d{2,4})", re.I),
    re.compile(r"Meghalaya\s+Legislative\s+Assembly[^\n]{0,120}?(?:letter\s+No\.?|D\.\s*No\.?)\s*[A-Z0-9./\-\s]+?[,;]?\s*(?:Notice\s+received\s+on\s+|dated\s+)(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})", re.I | re.S),
    re.compile(r"Notice\s+received\s+on\s+(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})", re.I),
]


def parse_date(value):
    """Parse 26/02/2024, 17.08.2026, '26th August, 2026', '26 August 2026', ISO."""
    text = str(value or "").strip().replace(",", ".")
    match = re.match(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$", text)
    if match:
        try:
            return datetime(*map(int, match.groups()))
        except ValueError:
            return None
    match = re.match(r"(\d{1,2})[/\-. ](\d{1,2})[/\-. ](\d{2,4})(?![\d.])", text)
    if match:
        day, month, year = map(int, match.groups())
        year += 2000 if year < 100 else 0
        if 1900 <= year <= 2100:
            try:
                return datetime(year, month, day)
            except ValueError:
                return None
        return None
    match = re.match(r"(\d{1,2})(?:st|nd|rd|th)?[\s/\-.]+([A-Za-z]+),?[\s/\-.]+(\d{4}|\d{2})", text)
    if match and match.group(2).lower()[:3] in MONTHS:
        year = int(match.group(3))
        return datetime(year + 2000 if year < 100 else year,
                        MONTHS[match.group(2).lower()[:3]], int(match.group(1)))
    return None


def parse_session_date(value):
    """Session_Date from the CSV: 28/Aug/2026, 28-Aug-26, 2026-08-28."""
    return parse_date(str(value or "").strip())


def find_dates(text, reply_date=""):
    """First reply-date and submission-date matches in reading order.

    A submission candidate equal to the reply date is rejected (it is the
    memo date wearing a different label).
    """
    reply = reply_date
    text = squash_spaced_text(text)
    if not reply:
        for pattern in REPLY_DATE:
            match = pattern.search(text)
            if match:
                reply = match.group(1) if len(match.groups()) == 1 else " ".join(match.groups())
                reply = reply.strip()
                break
    submission = ""
    for pattern in SUBMISSION_DATE:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip()
            if candidate and candidate != reply:
                submission = candidate
                break
    return reply, submission


SPLIT_FRACTION = 0.45
FOOTER_MARK = re.compile(
    r"^\s*(memo|dated|date of reply|copy to|by orders?|yours faithfully|"
    r"(joint|deputy|under) secretary)", re.I)


def split_reply(words, width, height=0, side="right"):
    """Column text above the memo/signature footer (default: reply side).

    Both portal layouts put the reply right of mid-page; the memo block,
    copy-to list and signature sit below, so anything at/below the first
    footer marker line is excluded. Full-width (straddling) lines skipped.
    """
    if not words:
        return ""
    split = SPLIT_FRACTION * width
    height = height or 1
    # Full-width boxes (titles, banners) belong to neither column.
    words = [w for w in words if not (w[0] < 0.3 * width and w[2] > 0.7 * width)]
    if not words:
        return ""
    footer_ys = [(w[1] + w[3]) / 2 for w in words
                 if (w[1] + w[3]) / 2 > 0.35 * height and FOOTER_MARK.match(w[4])]
    cutoff = min(footer_ys, default=float("inf"))
    lines = defaultdict(list)
    for word in words:
        lines[round((word[1] + word[3]) / 2)] += [word]
    parts = []
    for _, line in sorted(lines.items()):
        line.sort()
        # A short box crossing the split means continuous full-width text
        # (titles, unwrapped lines): skip the line. Tall crossing boxes are
        # table cells whose edges sit near the gutter: assign by center.
        if any(w[0] < split < w[2] and (w[3] - w[1]) < 0.02 * height for w in line):
            continue
        text = " ".join(w[4] for w in line)
        if FOOTER_MARK.match(text):
            continue
        if side == "right":
            kept = [w[4] for w in line if (w[0] + w[2]) / 2 >= split
                    and (w[1] + w[3]) / 2 < cutoff]
        else:
            kept = [w[4] for w in line if (w[0] + w[2]) / 2 < split
                    and (w[1] + w[3]) / 2 < cutoff]
        if kept:
            parts.append(" ".join(kept))
    return "\n".join(parts)


FOOTER_CUT = re.compile(
    r"Memo\s*\.?\s*No|Date of Reply|Dated Shillong|Copy to|By Orders?|Yours faithfully",
    re.I)


def cut_footer(text):
    """Drop a trailing memo/signature block leaking into column text."""
    match = FOOTER_CUT.search(text or "")
    return text[:match.start()].strip() if match else (text or "").strip()


LABEL = re.compile(r"(?m)^\s*\(?([a-z])\)\s+")


def split_parts(qtext, rtext):
    """Pair question/reply sub-parts by their printed (a), (b) labels.

    Labels count only at line starts, so citations like 'clause 4(1) (b)'
    mid-sentence never split. Labeled reply segments pair with the
    same-labeled question segment. When the reply carries no labels, no
    granularity is invented: one whole-to-whole part is returned.
    """

    def segments(text):
        chunks = LABEL.split(text or "")
        head, rest = chunks[0].strip(), chunks[1:]
        out = []
        if head:
            out.append((None, head))
        for i in range(0, len(rest) - 1, 2):
            if rest[i + 1].strip():
                out.append((rest[i], rest[i + 1].strip()))
        return out

    qmap = {label: text for label, text in segments(qtext) if label}
    parts = [{"part": label, "question": qmap.get(label, ""), "answer": text}
             for label, text in segments(rtext) if label]
    if not parts and (rtext or "").strip():
        parts = [{"part": "", "question": (qtext or "").strip(),
                  "answer": (rtext or "").strip()}]
    return parts


def ocr_words(key, png):
    """Word boxes from ocr-v1 detections: (x0, y0, x1, y1, text).

    Boxes arrive as 0-1 fractions; they are rescaled to the image pixel
    size so geometry matches the text-layer path. Returns (ok, words,
    width, error).
    """
    import io
    from PIL import Image
    ok, payload, error, _ = nvidia.cv_model(key, OCR_MODEL, png)
    if not ok:
        return ok, [], 0, error
    try:
        width = Image.open(io.BytesIO(png)).width
        words = []
        for det in (payload.get("data") or [{}])[0].get("text_detections") or []:
            points = ((det.get("bounding_box") or {}).get("points") or [])
            text = (det.get("text_prediction") or {}).get("text", "").strip()
            if len(points) >= 2 and text:
                xs = [p["x"] for p in points]
                ys = [p["y"] for p in points]
                scale = width if max(xs) <= 1.0 else 1.0
                words.append((min(xs) * scale, min(ys) * scale,
                              max(xs) * scale, max(ys) * scale, text))
        return True, words, width, ""
    except (KeyError, IndexError, TypeError) as exc:
        return False, [], 0, f"unexpected shape: {exc}"


def page_data(pdf_path, key, page, dpi=200):
    """(full_text, question_text, reply_text, ocr_used, error) for one page."""
    import pymupdf
    try:
        with pymupdf.open(pdf_path) as doc:
            page_obj = doc[page]
            raw = page_obj.get_text("words")
            width, height = page_obj.rect.width, page_obj.rect.height
    except Exception as exc:
        return "", "", "", False, f"unreadable: {exc}"
    native = " ".join(w[4] for w in raw)
    if len(native.strip()) >= NATIVE_MIN_CHARS:
        words = [(w[0], w[1], w[2], w[3], w[4]) for w in raw]
        return (native, split_reply(words, width, height, side="left"),
                split_reply(words, width, height), False, "")
    png = nvidia.render_page(pdf_path, page=page, dpi=dpi)
    ok, words, width, error = ocr_words(key, png)
    if not ok:
        return "", "", "", True, error
    full = " ".join(w[4] for w in sorted(words, key=lambda w: (w[1], w[0])))
    import io
    from PIL import Image
    height = Image.open(io.BytesIO(png)).height
    return (full, split_reply(words, width, height, side="left"),
            split_reply(words, width, height), True, "")


def extract_pdf(pdf_path, key, dpi=200, session_date=""):
    """Full three-field record for one PDF (all pages until dates found)."""
    import pymupdf
    try:
        with pymupdf.open(pdf_path) as doc:
            n_pages = len(doc)
    except Exception as exc:
        return {"pdf": Path(pdf_path).name, "reply": "", "reply_date": "",
                "submission_date": "", "needs_review": [f"unreadable pdf: {exc}"]}
    texts, replies, questions, ocr_pages, errors = [], [], [], 0, []
    reply_raw, submission_raw = "", ""
    for page in range(min(n_pages, MAX_OCR_PAGES)):
        full, question, reply, ocr_used, error = page_data(pdf_path, key, page, dpi)
        if error:
            errors.append(f"p{page}: {error}")
        ocr_pages += ocr_used
        texts.append(full)
        if reply.strip():
            replies.append(reply)
        if question.strip():
            questions.append(question)
        if not reply_raw or not submission_raw:
            found_reply, found_sub = find_dates(full)
            reply_raw = reply_raw or found_reply
            submission_raw = submission_raw or found_sub
        time.sleep(PAUSE_SECONDS if ocr_used else 0)
        if reply_raw and submission_raw and page >= 1:
            break
    reply_date, submission_date = parse_date(reply_raw), parse_date(submission_raw)
    needs_review = list(errors)
    if not reply_raw:
        needs_review.append("no reply date found")
    elif not reply_date:
        needs_review.append(f"unparseable reply date: {reply_raw[:40]!r}")
    if not submission_raw:
        needs_review.append("no submission date found")
    elif not submission_date:
        needs_review.append(f"unparseable submission date: {submission_raw[:40]!r}")
    if reply_date and submission_date and reply_date < submission_date:
        needs_review.append("reply date precedes submission date")
    sitting = parse_session_date(session_date)
    if reply_date and sitting and abs((reply_date - sitting).days) > 120:
        needs_review.append(f"reply date {reply_date.strftime('%Y-%m-%d')} far from sitting {sitting.strftime('%Y-%m-%d')}")
    reply = cut_footer("\n".join(replies).strip())
    parts = split_parts("\n".join(questions).strip(), reply)
    if not reply:
        needs_review.append("empty reply text")
    return {"pdf": Path(pdf_path).name,
            "reply": reply,
            "parts": parts,
            "reply_date": reply_date.strftime("%Y-%m-%d") if reply_date else "",
            "reply_date_raw": reply_raw,
            "submission_date": submission_date.strftime("%Y-%m-%d") if submission_date else "",
            "submission_date_raw": submission_raw,
            "pages_ocr": ocr_pages, "needs_review": needs_review}


def run(csv_path, pdf_root, out_dir, key, limit=0, session=""):
    """Extract all PDFs listed in the CSV; skips basenames already stored."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    done_path = out / "extracted.jsonl"
    done = set()
    if done_path.exists():
        with open(done_path, encoding="utf-8") as handle:
            done = {json.loads(line).get("pdf") for line in handle if line.strip()}
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = [r for r in csv.DictReader(handle)
                if (r.get("Document_Link") or "").strip().lower().startswith("http")
                and (not session or session.lower() in str(r.get("Session") or "").lower())]
    extracted, review, saved = 0, 0, 0
    with open(done_path, "a", encoding="utf-8") as handle:
        for row in rows:
            name = str(row["Document_Link"]).rsplit("/", 1)[-1]
            if name in done or (limit and saved >= limit):
                continue
            matches = list(Path(pdf_root).rglob(name))
            if not matches:
                continue
            record = extract_pdf(str(matches[0]), key, session_date=str(row.get("Session_Date") or ""))
            record["session"] = str(row.get("Session") or "")
            record["question"] = str(row.get("Question_Number") or "").replace("\n", " ")[:80]
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            done.add(name)
            saved += 1
            extracted += 1
            review += bool(record["needs_review"])
            print(f"  [{saved}] {name}: reply={len(record['reply'])}ch "
                  f"rdate={record['reply_date'] or '?'} sdate={record['submission_date'] or '?'} "
                  f"{'REVIEW: ' + '; '.join(record['needs_review']) if record['needs_review'] else 'ok'}")
    print(f"extracted {extracted} ({review} need review), skipped {len(done) - saved} already stored")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract reply, reply date, submission date")
    parser.add_argument("--csv", default="data/dl_questions_raw.csv")
    parser.add_argument("--pdf-root", default="data/pdfs")
    parser.add_argument("--out", default="data/extracted")
    parser.add_argument("--limit", type=int, default=0, help="max PDFs (0 = all)")
    parser.add_argument("--session", default="", help="only sessions matching this text")
    args = parser.parse_args(argv)
    key = nvidia.load_key()
    if not key:
        print("No NVIDIA API key (env NVIDIA_API_KEY or legacy config).")
        return 1
    run(args.csv, args.pdf_root, args.out, key, limit=args.limit, session=args.session)
    return 0
