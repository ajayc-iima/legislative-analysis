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
DATE_FORMATS = ("%d/%b/%Y", "%d-%b-%Y", "%d/%b/%y", "%d-%b-%y",
                "%d %b %Y", "%d %b %y", "%Y-%m-%d")


def parse_date(value):
    text = str(value or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def subject_of(row):
    """Single-line subject; a bare 'Q.No N' prefix line is dropped.

    Returns '' when the row carries no real subject text.
    """
    for column in ("Subject", "Question_Number"):
        lines = [ln.strip() for ln in str(row.get(column) or "").splitlines() if ln.strip()]
        lines = [ln for ln in lines if not re.fullmatch(r"Q\.?\s*No\.?\s*\d+\.?", ln, re.I)]
        if lines:
            return lines[-1]
    return ""


SINGULAR_EXCEPTIONS = {"news", "status", "crisis", "class", "gas", "bus",
                       "lens", "series", "basis", "analysis", "species"}


def _singular(word):
    """Strip a trailing plural 's', leaving singular nouns ending in 's' alone."""
    if len(word) > 3 and word.endswith("s") and word not in SINGULAR_EXCEPTIONS:
        return word[:-1]
    return word


def normalize_subject(text):
    """Lowercase, strip punctuation, fold simple plurals ('languages'->'language')."""
    text = re.sub(r"[^a-z0-9 ]+", " ", str(text).lower())
    return " ".join(_singular(w) for w in text.split())


def normalize_department(name):
    """Merge portal spelling variants ('Power' / 'Power Department')."""
    text = str(name or "").strip()
    if not text:
        return UNKNOWN
    key = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    words = [w for w in key.split() if w != "department"]
    words = [_singular(w) for w in words]
    return " ".join(words) or UNKNOWN


def canonical_departments(keys):
    """Map each normalized key to the shortest key it extends by whole words.

    The portal mixes long and short spellings of the same portfolio
    ('Community & Rural Development' / 'Community & Rural Department'),
    so 'x y z' folds into 'x' when a bare 'x' key exists.
    """
    canonical = {}
    for key in keys:
        prefixes = [other for other in keys if other != key and key.startswith(other + " ")]
        canonical[key] = min(prefixes, key=len) if prefixes else key
    return canonical


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


def _coverage(items):
    if not items:
        return 0.0
    return round(100 * sum(1 for r in items if reply_link(r)) / len(items), 1)


def analyze(rows, top=TOP_N):
    by_dept, by_mla, by_session = defaultdict(list), defaultdict(list), defaultdict(list)
    dept_names = defaultdict(Counter)
    mla_names = defaultdict(Counter)
    # Fold variant spellings into one key each before grouping.
    all_keys = {normalize_department(str(row.get("Departments") or "").strip()) for row in rows}
    canonical = canonical_departments(all_keys)
    subject_names = defaultdict(Counter)
    recurring = defaultdict(lambda: {"sessions": set(), "occurrences": 0,
                                     "departments": Counter(), "askers": Counter()})
    for row in rows:
        raw_dept = str(row.get("Departments") or "").strip()
        dept_key = normalize_department(raw_dept)
        dept = canonical.get(dept_key, dept_key)
        dept_names[dept][raw_dept or UNKNOWN] += 1
        mla = normalize_mla(row.get("Asked_By"))
        mla_names[mla][str(row.get("Asked_By") or "").strip() or UNKNOWN] += 1
        session = (str(row.get("Assembly") or "").strip() or UNKNOWN,
                   str(row.get("Session") or "").strip() or UNKNOWN)
        by_dept[dept].append(row)
        by_mla[mla].append(row)
        by_session[session].append(row)
        subject = normalize_subject(subject_of(row))
        if len(subject) >= MIN_SUBJECT_CHARS:
            subject_names[subject][subject_of(row)] += 1
            entry = recurring[subject]
            entry["sessions"].add(session)
            entry["occurrences"] += 1
            entry["departments"][dept] += 1
            entry["askers"][mla] += 1

    # Most common raw spelling for each normalized department key.
    display = {key: re.sub(r"\s+", " ", counter.most_common(1)[0][0])
               for key, counter in dept_names.items()}
    mla_display = {key: counter.most_common(1)[0][0] for key, counter in mla_names.items()}
    subject_display = {key: re.sub(r"\s+", " ", counter.most_common(1)[0][0]).rstrip(".")
                       for key, counter in subject_names.items()}

    session_rows = []
    for name, items in by_session.items():
        assembly, session = name if isinstance(name, tuple) else ("", name)
        dates = [d for d in (parse_date(r.get("Session_Date")) for r in items) if d]
        session_rows.append({"session": session, "assembly": assembly, "sort": min(dates) if dates else None,
                             "first_date": min(dates).strftime("%d %b %Y") if dates else "",
                             "questions": len(items),
                             "with_reply": sum(1 for r in items if reply_link(r)),
                             "coverage": _coverage(items)})
    session_rows.sort(key=lambda s: (s["sort"] is None, s["sort"] or datetime.min,
                                     s["assembly"], s["session"]))
    for entry in session_rows:
        entry.pop("sort")

    total = len(rows)

    def canon_dept(raw):
        key = normalize_department(raw)
        return canonical.get(key, key)

    dept_rows = [{"department": display[name], "questions": len(items),
                  "sessions": len({str(r.get("Session") or "").strip() for r in items}),
                  "askers": len({normalize_mla(r.get("Asked_By")) for r in items}),
                  "coverage": _coverage(items)}
                 for name, items in by_dept.items()]
    dept_rows.sort(key=lambda d: (-d["questions"], d["department"]))
    for entry in dept_rows:
        entry["share"] = round(100 * entry["questions"] / total, 1) if total else 0.0

    mla_rows = [{"mla": mla_display[name], "questions": len(items),
                 "departments": len({canon_dept(r.get("Departments")) for r in items}),
                 "top_department": display[Counter(canon_dept(r.get("Departments"))
                                                 for r in items).most_common(1)[0][0]]}
                for name, items in by_mla.items()]
    mla_rows.sort(key=lambda m: (-m["questions"], m["mla"]))

    recurring_rows = [{"subject": subject_display.get(subject, subject), "key": subject,
                       "sessions": sorted(entry["sessions"]),
                       "occurrences": entry["occurrences"],
                       "departments": {display.get(k, k): v for k, v in entry["departments"].most_common(3)},
                       "askers": {mla_display.get(k, k): v for k, v in entry["askers"].most_common(3)}}
                      for subject, entry in recurring.items() if len(entry["sessions"]) >= 2]
    recurring_rows.sort(key=lambda r: (-len(r["sessions"]), -r["occurrences"], r["subject"]))

    dates = {parse_date(r.get("Session_Date")) for r in rows}

    data_notes = []
    missing_subject = [r for r in rows if not subject_of(r)]
    if missing_subject:
        data_notes.append(f"{len(missing_subject)} row(s) have no subject in the source data")
    seen, dupes = set(), 0
    for row in rows:
        number = question_number(row)
        if not number:
            continue
        key = (str(row.get("Session") or ""), str(row.get("Session_Date") or ""), number)
        if key in seen:
            dupes += 1
        seen.add(key)
    if dupes:
        data_notes.append(f"{dupes} row(s) repeat a question number on the same date in the source data")

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "overview": {"questions": total, "sessions": len(by_session),
                     "dates": len({d for d in dates if d}), "departments": len(by_dept),
                     "mlas": len(by_mla),
                     "with_reply": sum(1 for r in rows if reply_link(r)),
                     "reply_coverage": _coverage(rows),
                     "types": dict(Counter(question_type(r) for r in rows))},
        "data_notes": data_notes,
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
        "# Legislative Questions Analysis",
        "",
        f"Source: `{source}` · Generated: {stats['generated']}",
        "",
        "## Overview",
        "",
        _table(["Questions", "Sessions", "Sitting dates", "Departments", "MLAs", "Reply coverage"],
               [[overview["questions"], overview["sessions"], overview["dates"],
                 overview["departments"], overview["mlas"],
                 f"{overview['reply_coverage']}% ({overview['with_reply']})"]]),
        "",
        "Question types: " + (", ".join(f"{name} {count}" for name, count in overview["types"].items())
                              or "n/a"),
        "",
    ]
    if stats.get("data_notes"):
        parts.append("Data notes (source data quirks, not scraper errors):")
        parts += [f"- {note}" for note in stats["data_notes"]]
        parts.append("")
    parts += [
        "## Questions per session",
        "",
        _table(["Assembly", "Session", "First date", "Questions", "With reply", "Coverage"],
               [[s["assembly"], s["session"], s["first_date"], s["questions"],
                 s["with_reply"], f"{s['coverage']}%"]
                for s in stats["sessions"]]),
        "",
        "## Departments (by question volume)",
        "",
        _table(["Department", "Questions", "Share", "Sessions", "Askers", "Reply coverage"],
               [[d["department"], d["questions"], f"{d['share']}%", d["sessions"], d["askers"],
                 f"{d['coverage']}%"] for d in stats["departments"]]),
        "",
        "## MLAs (by question volume)",
        "",
        _table(["MLA", "Questions", "Departments", "Top department"],
               [[m["mla"], m["questions"], m["departments"], m["top_department"]]
                for m in stats["mlas"]]),
        "",
        "## Recurring subjects (same subject in 2+ sessions)",
        "",
    ]
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
    args = parser.parse_args(argv)
    if not Path(args.csv).exists():
        print(f"Input CSV not found: {args.csv} (run the scraper first, or pass --csv)")
        return 1
    rows = load(args.csv)
    stats = analyze(rows, top=args.top)
    report = write_report(stats, args.out_dir, source=args.csv)
    print(f"{len(rows)} questions -> {report}")
    return 0
