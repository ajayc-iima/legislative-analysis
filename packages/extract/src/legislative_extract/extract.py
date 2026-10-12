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
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import nvidia

OCR_MODEL = "nvidia/nemotron-ocr-v1"
NATIVE_MIN_CHARS = 200
GIBBERISH_MAX_UNEXPECTED = 0.06
# Characters expected in a trustworthy native text layer. A layer with more
# symbol-soup than this is a broken font encoding (mojibake), not real text:
# measured 0.14-0.19 on mojibake pages vs 0.00-0.01 on normal pages.
_NATIVE_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                      "0123456789 \t\n,.;:'\"()-\u2013\u2014/%\u20b9&?!")


def looks_gibberish(text):
    """True when a native text layer is font-encoding mojibake. Conservative:
    a false positive only costs one OCR call; a false negative keeps the
    status quo (flagged, untrusted layer unused... see page_data)."""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return False
    unexpected = sum(1 for c in chars if c not in _NATIVE_ALLOWED)
    return unexpected / len(chars) > GIBBERISH_MAX_UNEXPECTED
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
    re.compile(r"date\s+of\s+(?:reply|discussion)(?:\s+(?:is\s+)?on)?\s*[-:]?\s*(\d{1,2}[/\-.,]\d{1,2}[/\-.,]\d{2,4})", re.I),
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
    if match:
        import difflib
        frag = match.group(2).lower()[:3]
        month = MONTHS.get(frag)
        if month is None:
            # OCR typos in month names ('Agust' for August): closest
            # abbreviation at 0.6+ similarity (transpositions score ~0.67).
            # Exact matches always win; day/month names ('mon') score <0.4.
            close = difflib.get_close_matches(frag, MONTHS, n=1, cutoff=0.6)
            month = MONTHS[close[0]] if close else None
        if month:
            year = int(match.group(3))
            try:
                return datetime(year + 2000 if year < 100 else year,
                                month, int(match.group(1)))
            except ValueError:
                return None  # e.g. '30 February': impossible calendar date
    return None


def parse_session_date(value):
    """Session_Date from the CSV: 28/Aug/2026, 28-Aug-26, 2026-08-28."""
    return parse_date(str(value or "").strip())


def flag_date_issues(reply_date, submission_date, sitting, needs_review):
    """Append ordering/proximity notes for a date pair (values are kept).

    Pure function over datetimes so the policy is unit-testable; both
    extract_pdf (deterministic) and Layer 4 filtering share its flags.
    Notes are de-duplicated: consensus_fill re-flags the merged pair,
    which may already carry deterministic notes.
    """
    notes = []
    if reply_date and submission_date and reply_date < submission_date:
        notes.append("reply date precedes submission date")
    if reply_date and sitting and abs((reply_date - sitting).days) > 120:
        notes.append(f"reply date {reply_date.strftime('%Y-%m-%d')} far from sitting {sitting.strftime('%Y-%m-%d')}")
    if submission_date and sitting and abs((submission_date - sitting).days) > 120:
        notes.append(f"submission date {submission_date.strftime('%Y-%m-%d')} far from sitting {sitting.strftime('%Y-%m-%d')}")
    for note in notes:
        if note not in needs_review:
            needs_review.append(note)
    return needs_review


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
# Bulletin/question formulae: never reply content. Unanchored on purpose:
# header boxes often share a line with other words ("Question? STARRED
# QUESTIONS ..."), and OCR glues prefixes ("UNSTARRED"). The plural
# "questions" plus the asker formula keeps replies that cite a singular
# "Starred Question No. N" safe — locked by
# test_split_reply_keeps_singular_citation. The answering-minister
# assignment ("... to reply:-") and bare column headers ("Question" /
# "Replies") are endemic benign metadata and are NOT matched here — only
# patterns that prove bulletin/question material shares the page.
QUESTION_HEAD = re.compile(
    r"(?:UN)?STARRED QUESTIONS\b|\bQUESTIONS? TO BE ASKED BY\b|pleased to state",
    re.I)


def split_reply(words, width, height=0, side="right"):
    """Column text above the memo/signature footer (default: reply side).

    Both portal layouts put the reply right of mid-page; the memo block,
    copy-to list and signature sit below, so anything at/below the first
    footer marker line is excluded. Full-width (straddling) lines skipped.

    Single-column fallback: some sittings file single-column replies whose
    every line straddles the split, so the column pass keeps nothing. When
    the right-side pass is empty, full lines above the footer are returned
    ONLY if the text demonstrably flows across the gutter (a majority of
    lines straddle it, with enough characters) — or a single straddling
    line that reads as a sentence (lowercase letters, terminal punctuation),
    which titles and banners never are. A left-column-only page (question
    asked, no reply given) has no straddling lines and still returns "", so
    question text is never mislabelled as reply. Bulletin/question formulae
    (STARRED-questions headers, "pleased to state") are skipped in both
    passes; if the fallback drops any such line the page mixes bulletin
    material with answers and the whole fallback is refused. Residual risk
    (documented): a page holding nothing but two long full-width title
    lines would be taken as reply text; such pages are pathological
    in reply PDFs and still carry their REVIEW flags for dates.
    """
    if not words:
        return ""
    split = SPLIT_FRACTION * width
    height = height or 1
    # Full-width boxes (titles, banners) belong to neither column.
    col_words = [w for w in words
                 if not (w[0] < 0.3 * width and w[2] > 0.7 * width)]
    footer_ys = [(w[1] + w[3]) / 2 for w in col_words
                 if (w[1] + w[3]) / 2 > 0.35 * height and FOOTER_MARK.match(w[4])]
    cutoff = min(footer_ys, default=float("inf"))
    lines = defaultdict(list)
    for word in col_words:
        lines[round((word[1] + word[3]) / 2)] += [word]
    parts = []
    for _, line in sorted(lines.items()):
        line.sort()
        # A short box crossing the split means continuous full-width text
        # (titles, unwrapped lines): skip the line. Tall crossing boxes are
        # table cells whose edges sit near the gutter: assign by center.
        #
        # A tempting relaxation (apply the skip only to 1-3 box lines, or
        # test full-width spans per line) was validated corpus-wide and
        # rejected: it changed 495 of 577 native-path replies with gains
        # and losses mixed. Word-level native layers wrap across the
        # split routinely, so neither variant separates real reply lines
        # from full-width text reliably. The conservative rule stands;
        # the 13 records it refuses are documented in
        # data/review/FLAGGED_EMPTY.md instead.
        if any(w[0] < split < w[2] and (w[3] - w[1]) < 0.02 * height for w in line):
            continue
        text = " ".join(w[4] for w in line)
        if FOOTER_MARK.match(text):
            continue
        if QUESTION_HEAD.search(text):
            continue
        if side == "right":
            kept = [w[4] for w in line if (w[0] + w[2]) / 2 >= split
                    and (w[1] + w[3]) / 2 < cutoff]
        else:
            kept = [w[4] for w in line if (w[0] + w[2]) / 2 < split
                    and (w[1] + w[3]) / 2 < cutoff]
        if kept:
            parts.append(" ".join(kept))
    result = "\n".join(parts)
    if result.strip() or side != "right":
        return result
    # Single-column fallback on the unfiltered boxes: the column pass above
    # already dropped full-width lines, which is exactly what a single-column
    # reply is made of.
    body = defaultdict(list)
    for w in words:
        if (w[1] + w[3]) / 2 < cutoff:
            body[round((w[1] + w[3]) / 2)] += [w]
    flines = []
    qdropped = 0
    for _, line in sorted(body.items()):
        text = " ".join(w[4] for w in sorted(line))
        if not text.strip() or FOOTER_MARK.match(text):
            continue
        if QUESTION_HEAD.search(text):
            # Bulletin/question material shares the page: line rules cannot
            # separate interleaved sub-questions from answers. Refuse the
            # whole fallback rather than store question text as reply; the
            # record stays flagged for human review.
            qdropped += 1
            continue
        flines.append(line)
    if qdropped:
        return ""
    n_chars = sum(len(w[4]) for line in flines for w in line)
    straddling = sum(1 for line in flines
                     if any(w[0] < split < w[2] for w in line))
    flowing = bool(flines) and straddling / len(flines) > 0.25
    single_sentence = (
        len(flines) == 1 and straddling == 1
        and _looks_sentence(" ".join(w[4] for w in flines[0])))
    if n_chars >= 40 and flowing and (len(flines) >= 2 or single_sentence):
        return "\n".join(" ".join(w[4] for w in sorted(line)) for line in flines)
    # Reply-marker fallback: short replies ("Sir, ...") can sit entirely
    # left of the split, geometrically identical to an empty reply column
    # beside a question page. Take them ONLY when most lines carry reply
    # markers — question text essentially never does — so a bundled
    # question page is never mislabelled as reply.
    if flines and n_chars >= 25:
        sir = sum(1 for line in flines
                  if re.search(r"\bSir\b", " ".join(w[4] for w in line)))
        whole = "\n".join(" ".join(w[4] for w in sorted(line)) for line in flines)
        if (sir / len(flines) >= 0.5
                and (len(flines) >= 2 or _looks_sentence(whole))):
            return whole
    return result


def _looks_sentence(text):
    """A sentence, not a title or banner: mixed case, terminal punctuation."""
    return bool(re.search(r"[a-z]", text) and text.rstrip().endswith((".", "?", "!", ":")))


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
    if len(native.strip()) >= NATIVE_MIN_CHARS and not looks_gibberish(native):
        words = [(w[0], w[1], w[2], w[3], w[4]) for w in raw]
        return (native, split_reply(words, width, height, side="left"),
                split_reply(words, width, height), False, "")
    # Unscanned page, or a native layer too corrupted to trust: OCR it.
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
        # Dates found AND some reply text in hand (and past page 0): stop.
        # Requiring reply text too keeps reading while the reply pages are
        # still ahead (e.g. dates on page 0, reply from page 2 on).
        if reply_raw and submission_raw and replies and page >= 1:
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
    sitting = parse_session_date(session_date)
    flag_date_issues(reply_date, submission_date, sitting, needs_review)
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


def consensus_fill(pdf_path, key, record, row):
    """Run model consensus for dates the deterministic pass missed.

    Page 0 first; page 1 only if dates remain undecided. The two
    fast readers (ocr-v1, parse) run first; the ~20s vision
    reader is only invoked when they do not already agree on both
    dates, and the reasoning supervisor only when no 2-of-N
    consensus emerges. Fills the record in place; returns True
    when both dates are decided.
    """
    from . import consensus
    readings = []
    name = Path(pdf_path).name
    context = {"session": str(row.get("Session") or ""),
               "sitting_date": str(row.get("Session_Date") or ""),
               "department": str(row.get("Departments") or ""),
               "mla": str(row.get("Asked_By") or ""),
               "subject": str(row.get("Subject") or "")[:120]}
    sitting_iso = str(row.get("Session_Date") or "")
    import pymupdf
    try:
        with pymupdf.open(pdf_path) as doc:
            n_pages = len(doc)
    except Exception:
        return False

    def both_decided():
        q = consensus.quick_consensus(readings, sitting_iso=sitting_iso)
        return bool(q["reply_date"] and q["submission_date"])

    for page in range(min(n_pages, 2)):
        try:
            png = nvidia.render_page(pdf_path, page=page, dpi=200)
        except Exception:
            return False  # transient read failure; keep deterministic results
        readings.append(consensus.read_ocr(key, png))
        time.sleep(consensus.PAUSE_SECONDS)
        ok, text, _, _ = nvidia.parse_document(key, png)
        readings.append({"reader": "parse", "ok": ok, "text": text,
                         "error": "", "ms": 0})
        time.sleep(consensus.PAUSE_SECONDS)
        if both_decided():
            break  # fast readers agree; skip the vision call
        readings.append(consensus.read_vision(key, png))
        if both_decided():
            break

    verdict = consensus.adjudicate(key, readings, context,
                                   sitting_iso=sitting_iso)
    filled = False
    if not record["reply_date"] and verdict["reply_date"]:
        record["reply_date"] = verdict["reply_date"]
        filled = True
    if not record["submission_date"] and verdict["submission_date"]:
        record["submission_date"] = verdict["submission_date"]
        filled = True
    record["confidence"] = verdict["confidence"]
    record["provenance"] = verdict["provenance"]
    sitting = parse_session_date(sitting_iso)
    flag_date_issues(parse_date(record["reply_date"]) if record["reply_date"] else None,
                     parse_date(record["submission_date"]) if record["submission_date"] else None,
                     sitting, record["needs_review"])
    record["needs_review"] = [
        note for note in record["needs_review"]
        if not (note.startswith("no reply date") and record["reply_date"])
        and not (note.startswith("no submission date") and record["submission_date"])
        and not (note.startswith("unparseable reply date") and record["reply_date"])
        and not (note.startswith("unparseable submission date") and record["submission_date"])]
    if verdict["confidence"] == "low" or not verdict["reply_date"]:
        record["needs_review"].append(f"consensus {verdict['provenance']} ({verdict['confidence']})")
    return filled


def _pid_alive(pid):
    """True if a process with this PID exists (stale-lock check)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        return False
    return True


def _acquire_lock(out_dir):
    """Single-instance guard: one extraction run per output directory.

    Uses atomic exclusive creation so two processes starting in the
    same second cannot both proceed. A lock whose PID is dead is
    reaped. Returns the lock path, or None when another live run
    holds it.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lock_path = out / "extract.lock"

    def create():
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))

    try:
        create()
        return lock_path
    except FileExistsError:
        pass
    try:
        pid = int(lock_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = -1
    if pid > 0 and _pid_alive(pid):
        print(f"extract.lock held by live PID {pid}; refusing a second run "
              f"(delete {lock_path} if that process is not extracting).")
        return None
    lock_path.unlink(missing_ok=True)
    try:
        create()
        return lock_path
    except FileExistsError:
        print("lost the lock race; another instance is running.")
        return None


def _validate_lock(lock_path):
    """Confirm our lock still names us after a settling delay.

    Two starters in the same second can interleave acquire/reap so
    that both briefly believe they hold the lock. The last writer
    wins; everyone else exits here. Pure read — unit-testable.
    """
    time.sleep(2)
    try:
        return int(lock_path.read_text(encoding="utf-8").strip()) == os.getpid()
    except (OSError, ValueError):
        return False


def run(csv_path, pdf_root, out_dir, key, limit=0, session="", consensus_on=True,
        from_year=0):
    """Extract all PDFs listed in the CSV; skips basenames already stored.

    Per-PDF failures are caught and logged to extract_errors.jsonl
    so one bad scan cannot abort the run; the run is resume-friendly
    (already-stored basenames are skipped). A lockfile refuses a
    second concurrent run in the same output directory.
    from_year skips rows sitting before that year (analysis starts
    2021; pre-2021 PDFs are not processed at all).
    """
    lock_path = _acquire_lock(out_dir)
    if lock_path is None:
        return 2
    if not _validate_lock(lock_path):
        print("lock superseded by another starter; exiting.")
        return 2
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
    extracted, review, saved, failed = 0, 0, 0, 0
    not_on_disk = 0
    err_path = out / "extract_errors.jsonl"
    out_of_scope = 0

    def log_error(name, exc):
        """Error logging must never kill the run (the volume flickered once)."""
        try:
            with open(err_path, "a", encoding="utf-8") as ef:
                ef.write(json.dumps({"pdf": name, "error": repr(exc)},
                                    ensure_ascii=False) + "\n")
        except OSError:
            pass

    with open(done_path, "a", encoding="utf-8") as handle:
        for row in rows:
            name = str(row["Document_Link"]).rsplit("/", 1)[-1]
            if name in done or (limit and saved >= limit):
                continue
            if from_year:
                sitting = parse_session_date(row.get("Session_Date"))
                if sitting is not None and sitting.year < from_year:
                    out_of_scope += 1
                    continue
            try:
                matches = [m for m in Path(pdf_root).rglob(name) if m.is_file()]
            except OSError as exc:
                # volume-level failure (the store vanished mid-run before):
                # abort loudly so the run is retried, not silently starved.
                print(f"ABORT: cannot list {pdf_root}: {exc!r}")
                lock_path.unlink(missing_ok=True)
                return 3
            if not matches:
                not_on_disk += 1
                log_error(name, FileNotFoundError(f"no PDF on disk under {pdf_root}"))
                print(f"  [MISS] {name}: no PDF on disk")
                continue
            try:
                record = extract_pdf(str(matches[0]), key,
                                     session_date=str(row.get("Session_Date") or ""))
                record["session"] = str(row.get("Session") or "")
                record["question"] = str(row.get("Question_Number") or "").replace("\n", " ")[:80]
                record.setdefault("confidence", "deterministic")
                record.setdefault("provenance", "deterministic")
                if consensus_on and (not record["reply_date"] or not record["submission_date"]):
                    consensus_fill(str(matches[0]), key, record, row)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
            except Exception as exc:
                failed += 1
                log_error(name, exc)
                print(f"  [FAIL] {name}: {exc!r}")
                continue
            done.add(name)
            saved += 1
            extracted += 1
            review += bool(record["needs_review"])
            print(f"  [{saved}] {name}: reply={len(record['reply'])}ch "
                  f"rdate={record['reply_date'] or '?'} sdate={record['submission_date'] or '?'} "
                  f"{'REVIEW: ' + '; '.join(record['needs_review']) if record['needs_review'] else 'ok'}")
    print(f"extracted {extracted} ({review} need review), "
          f"skipped {len(done) - saved} already stored, {failed} failed, "
          f"{not_on_disk} not on disk, {out_of_scope} out of scope")
    lock_path.unlink(missing_ok=True)
    return 0


def append_csv(csv_path, out_dir, csv_out=""):
    """Write a copy of the questions CSV with extracted date columns appended.

    Matches JSONL records to rows by Document_Link basename. Never modifies
    the input CSV; reply text and parts stay in extracted.jsonl (keyed by pdf).
    """
    out = Path(out_dir)
    records = {}
    done_path = out / "extracted.jsonl"
    if done_path.exists():
        with open(done_path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    records[record.get("pdf", "")] = record
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = list(reader.fieldnames or []) + ["Reply_Date_Extracted",
            "Submission_Date_Extracted", "Extract_Confidence", "Extract_Provenance"]
    for row in rows:
        name = str(row.get("Document_Link") or "").rsplit("/", 1)[-1]
        record = records.get(name, {})
        row["Reply_Date_Extracted"] = record.get("reply_date", "")
        row["Submission_Date_Extracted"] = record.get("submission_date", "")
        row["confidence"] = record.get("confidence", "")
        row["Extract_Confidence"] = record.get("confidence", "")
        row["Extract_Provenance"] = record.get("provenance", "")
    dest = Path(csv_out) if csv_out else Path(csv_path).parent / "dl_questions_extracted.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    filled = sum(1 for r in rows if r["Reply_Date_Extracted"])
    print(f"wrote {dest} ({len(rows)} rows, {filled} with reply dates)")
    return str(dest)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract reply, reply date, submission date")
    parser.add_argument("--csv", default="data/dl_questions_raw.csv")
    parser.add_argument("--pdf-root", default="data/pdfs")
    parser.add_argument("--out", default="data/extracted")
    parser.add_argument("--limit", type=int, default=0, help="max PDFs (0 = all)")
    parser.add_argument("--session", default="", help="only sessions matching this text")
    parser.add_argument("--from-year", type=int, default=0,
                        help="skip rows sitting before this year (0 = all)")
    parser.add_argument("--csv-out", default="",
                        help="after the run, write a copy of the questions CSV "
                             "with extracted date/confidence columns appended")
    args = parser.parse_args(argv)
    key = nvidia.load_key()
    if not key:
        print("No NVIDIA API key (env NVIDIA_API_KEY or legacy config).")
        return 1
    status = run(args.csv, args.pdf_root, args.out, key, limit=args.limit,
                 session=args.session, from_year=args.from_year)
    if args.csv_out:
        append_csv(args.csv, args.out, csv_out=args.csv_out)
    return status
