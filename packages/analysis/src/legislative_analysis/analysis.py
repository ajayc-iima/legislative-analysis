"""Minimal, defensible analysis of scraped legislative questions.

Computes only what the data supports: counts, distributions, reply
coverage, and subjects recurring across sessions. No composite scores,
no invented probabilities, no LLM.
"""

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

UNKNOWN = "Unknown"
DEFAULT_CSV = "data/dl_questions_raw.csv"
DEFAULT_OUT = "output"
TOP_N = 20
MIN_SUBJECT_CHARS = 10

# Analysis scope: sessions before 2021 have reply coverage of 0-16%
# (Autumn 2018 and Budget 2019: zero signed replies), too sparse for
# reply-side analysis. Every driver filters through scope_rows().
SCOPE_FROM_YEAR = 2021


def in_scope(row, from_year=SCOPE_FROM_YEAR):
    """True when the row's sitting date falls inside the analysis window."""
    sitting = parse_date(row.get("Session_Date"))
    return sitting is not None and sitting.year >= from_year


def scope_rows(rows, from_year=SCOPE_FROM_YEAR):
    """Drop rows outside the analysis window (pre-2021 by default).

    Recurrence, trends and diversity are all measured WITHIN the
    window: a subject asked in 2020 and 2021 counts as new in 2021.
    """
    return [row for row in rows if in_scope(row, from_year)]

MONTHS = {m.lower(): i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def parse_date(value):
    """Parse portal/master dates: 28/Aug/2026, 15-Sep-26, 15 Oct 2025, 2026-08-28."""
    text = str(value or "").strip()
    iso = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if iso:
        return datetime(*map(int, iso.groups()))
    match = re.match(r"(\d{1,2})[/\- ]([A-Za-z]{3})[/\- ](\d{2,4})", text)
    if not match:
        return None
    day, month, year = int(match.group(1)), MONTHS.get(match.group(2).lower()), int(match.group(3))
    if not month or not 1 <= day <= 31:
        return None
    return datetime(year + 2000 if year < 100 else year, month, day)


def subject_of(row):
    """Single-line subject; a bare 'Q.No N' prefix is dropped."""
    for column in ("Subject", "Question_Number"):
        lines = [ln.strip() for ln in str(row.get(column) or "").splitlines() if ln.strip()]
        lines = [ln for ln in lines if not re.fullmatch(r"Q\.?\s*No\.?\s*\d+\.?", ln, re.I)]
        if lines:
            text = lines[-1]
            # single-line subjects may carry the prefix inline
            text = re.sub(r"^Q\.?\s*No\.?\s*\d+\s*[:.\-]?\s*", "", text, flags=re.I)
            return text.strip()
    return ""


SINGULAR_EXCEPTIONS = {"news", "status", "crisis", "class", "gas", "bus",
                       "lens", "series", "basis", "analysis", "species"}


def _singular(word):
    """Strip a trailing plural 's', leaving singular nouns ending in 's' alone."""
    if len(word) > 3 and word.endswith("s") and word not in SINGULAR_EXCEPTIONS:
        return word[:-1]
    return word


def _words(text):
    return [_singular(w) for w in re.sub(r"[^a-z0-9 ]+", " ", str(text).lower()).split()]


def normalize_subject(text):
    """Lowercase, strip punctuation, fold simple plurals ('languages'->'language')."""
    return " ".join(_words(text or ""))


def normalize_department(name):
    """Merge portal spelling variants ('Power' / 'Power Department')."""
    words = [w for w in _words(name or "") if w != "department"]
    return " ".join(words) or UNKNOWN


def canonical_departments(keys):
    """Map each normalized key to the shortest key it extends by whole words.

    The portal mixes long and short spellings of the same portfolio
    ('Community & Rural Development' / 'Community & Rural Department'),
    so 'x y z' folds into 'x' when a bare 'x' key exists.
    """
    return {k: min((o for o in keys if o != k and k.startswith(o + " ")), key=len, default=k)
            for k in keys}


def normalize_mla(name):
    """Collapse portal typo variants ('Process T. Sawkmie,' -> 'Process T. Sawkmie')."""
    text = re.sub(r"\s+", " ", str(name or "").strip())
    return re.sub(r"[\s,.;]+$", "", text) or UNKNOWN


def reply_link(row):
    for column in ("Document_Link", "Reply_URL", "Reply"):
        value = str(row.get(column) or "").strip()
        if value.lower().startswith(("http://", "https://")):
            return value
    return ""


def question_type(row):
    for column in ("Question_Type", "Category"):
        value = str(row.get(column) or "").strip()
        if value:
            return value
    return UNKNOWN


def question_number(row):
    match = re.search(r"Q\.?No\.?\s*(\d+)", str(row.get("Question_Number") or ""), re.I)
    return match.group(1) if match else ""


def load(csv_path):
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _pct(count, total):
    return round(100 * count / total, 1) if total else 0.0


def _display(counter):
    return re.sub(r"\s+", " ", counter.most_common(1)[0][0])


def analyze(rows, top=TOP_N):
    keys = {normalize_department(r.get("Departments")) for r in rows}
    canonical = canonical_departments(keys)
    depts = defaultdict(lambda: {"n": 0, "replies": 0, "sessions": set(), "askers": set(), "names": Counter()})
    mlas = defaultdict(lambda: {"n": 0, "depts": set(), "top": Counter(), "names": Counter()})
    sessions = defaultdict(lambda: {"n": 0, "replies": 0, "dates": []})
    subjects = defaultdict(lambda: {"n": 0, "sessions": set(), "depts": Counter(), "askers": Counter(), "names": Counter()})
    types = Counter()
    numbers, replies, missing = [], 0, 0

    for row in rows:
        raw_dept = str(row.get("Departments") or "").strip()
        dept = canonical[normalize_department(raw_dept)]
        mla, mla_name = normalize_mla(row.get("Asked_By")), str(row.get("Asked_By") or "").strip() or UNKNOWN
        session = (str(row.get("Assembly") or "").strip() or UNKNOWN,
                   str(row.get("Session") or "").strip() or UNKNOWN)
        subject = subject_of(row)
        reply = bool(reply_link(row))
        replies += reply
        types[question_type(row)] += 1
        if not subject:
            missing += 1
        numbers.append((session, str(row.get("Session_Date") or ""), question_number(row)))

        d = depts[dept]
        d["n"] += 1; d["replies"] += reply; d["sessions"].add(session[1])
        d["askers"].add(mla); d["names"][raw_dept or UNKNOWN] += 1

        m = mlas[mla]
        m["n"] += 1; m["depts"].add(dept); m["top"][dept] += 1; m["names"][mla_name] += 1

        s = sessions[session]
        s["n"] += 1; s["replies"] += reply; s["dates"].append(parse_date(row.get("Session_Date")))

        norm = normalize_subject(subject)
        if len(norm) >= MIN_SUBJECT_CHARS:
            x = subjects[norm]
            x["n"] += 1; x["sessions"].add(session); x["names"][subject] += 1
            x["depts"][dept] += 1; x["askers"][mla] += 1

    session_rows = []
    for (assembly, name), s in sessions.items():
        dates = [d for d in s["dates"] if d]
        session_rows.append({
            "assembly": assembly, "session": name, "sort": min(dates) if dates else None,
            "first_date": min(dates).strftime("%d %b %Y") if dates else "",
            "questions": s["n"], "with_reply": s["replies"], "coverage": _pct(s["replies"], s["n"])})
    session_rows.sort(key=lambda x: (x["sort"] is None, x["sort"] or datetime.min,
                                     x["assembly"], x["session"]))
    [x.pop("sort") for x in session_rows]

    dept_rows = sorted(({
        "department": _display(d["names"]), "questions": d["n"], "sessions": len(d["sessions"]),
        "askers": len(d["askers"]), "coverage": _pct(d["replies"], d["n"])} for d in depts.values()),
        key=lambda x: (-x["questions"], x["department"]))
    for d in dept_rows:
        d["share"] = _pct(d["questions"], len(rows))

    mla_rows = sorted(({
        "mla": m["names"].most_common(1)[0][0], "questions": m["n"], "departments": len(m["depts"]),
        "top_department": _display(depts[m["top"].most_common(1)[0][0]]["names"])} for m in mlas.values()),
        key=lambda x: (-x["questions"], x["mla"]))

    recurring_rows = [{
        "subject": re.sub(r"\s+", " ", x["names"].most_common(1)[0][0]).rstrip("."), "key": key,
        "sessions": sorted(x["sessions"]), "occurrences": x["n"],
        "departments": {_display(depts[k]["names"]): v for k, v in x["depts"].most_common(3)},
        "askers": {mlas[k]["names"].most_common(1)[0][0]: v for k, v in x["askers"].most_common(3)}}
        for key, x in subjects.items() if len(x["sessions"]) >= 2]
    recurring_rows.sort(key=lambda x: (-len(x["sessions"]), -x["occurrences"], x["subject"]))

    notes = []
    if missing:
        notes.append(f"{missing} row(s) have no subject in the source data")
    numbered = Counter(k for k in numbers if k[2])
    dupes = sum(count - 1 for count in numbered.values() if count > 1)
    if dupes:
        notes.append(f"{dupes} row(s) repeat a question number on the same date in the source data")

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "overview": {"questions": len(rows), "sessions": len(sessions),
                     "dates": len({d for s in sessions.values() for d in s["dates"] if d}),
                     "departments": len(depts), "mlas": len(mlas), "with_reply": replies,
                     "reply_coverage": _pct(replies, len(rows)), "types": dict(types)},
        "data_notes": notes,
        "sessions": session_rows,
        "departments": dept_rows[:top],
        "mlas": mla_rows[:top],
        "recurring": recurring_rows[:top],
    }


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |"
              for row in rows]
    return "\n".join(lines)


def write_report(stats, out_dir, source=""):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    overview = stats["overview"]
    parts = [
        "# Legislative Questions Analysis", "",
        f"Source: `{source}` · Generated: {stats['generated']}", "",
        "## Overview", "",
        _table(["Questions", "Sessions", "Sitting dates", "Departments", "MLAs", "Reply coverage"],
               [[overview["questions"], overview["sessions"], overview["dates"],
                 overview["departments"], overview["mlas"],
                 f"{overview['reply_coverage']}% ({overview['with_reply']})"]]), "",
        "Question types: " + (", ".join(f"{name} {count}" for name, count in overview["types"].items())
                              or "n/a"), ""]
    if stats.get("data_notes"):
        parts += ["Data notes (source data quirks, not scraper errors):"]
        parts += [f"- {note}" for note in stats["data_notes"]]
        parts.append("")
    parts += [
        "## Questions per session", "",
        _table(["Assembly", "Session", "First date", "Questions", "With reply", "Coverage"],
               [[s["assembly"], s["session"], s["first_date"], s["questions"],
                 s["with_reply"], f"{s['coverage']}%"] for s in stats["sessions"]]), "",
        "## Departments (by question volume)", "",
        _table(["Department", "Questions", "Share", "Sessions", "Askers", "Reply coverage"],
               [[d["department"], d["questions"], f"{d['share']}%", d["sessions"], d["askers"],
                 f"{d['coverage']}%"] for d in stats["departments"]]), "",
        "## MLAs (by question volume)", "",
        _table(["MLA", "Questions", "Departments", "Top department"],
               [[m["mla"], m["questions"], m["departments"], m["top_department"]]
                for m in stats["mlas"]]), "",
        "## Recurring subjects (same subject in 2+ sessions)", ""]
    if stats["recurring"]:
        parts.append(_table(["Subject", "Sessions", "Occurrences", "Departments", "Askers"],
                            [[r["subject"], len(r["sessions"]), r["occurrences"],
                              ", ".join(r["departments"]), ", ".join(r["askers"])]
                             for r in stats["recurring"]]))
    else:
        parts.append("_None found (recurs across sessions; single-session data yields none)._")
    parts.append("")
    report = out / "analysis_report.md"
    report.write_text("\n".join(parts), encoding="utf-8")
    (out / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Minimal legislative questions analysis")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="questions CSV (scraper output)")
    parser.add_argument("--out-dir", default=DEFAULT_OUT, help="output directory")
    parser.add_argument("--top", type=int, default=TOP_N, help="rows per table")
    parser.add_argument("--layers", action="store_true",
                        help="run the full six-layer analysis (Tasks 1-3)")
    args = parser.parse_args(argv)
    if not Path(args.csv).exists():
        print(f"Input CSV not found: {args.csv} (run the scraper first, or pass --csv)")
        return 1
    if args.layers:
        from . import layers as layers_mod
        return layers_mod.main(["--csv", args.csv, "--out-dir", args.out_dir])
    stats = analyze(scope_rows(load(args.csv)), top=args.top)
    report = write_report(stats, args.out_dir, source=args.csv)
    print(f"{stats['overview']['questions']} questions -> {report}")
    return 0
