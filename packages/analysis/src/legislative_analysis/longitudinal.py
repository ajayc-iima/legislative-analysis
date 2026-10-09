"""Longitudinal analysis: resolution tracking, trends, emerging issues.

Tasks 3.1–3.3 from PLAN.md.

Resolution tracking links each recurring subject (same normalized
subject in ≥2 sessions) to its replies across sessions and codes
the trajectory:

  resolved     latest reply contains completion language
  progressing  latest reply shows measurable progress signals
  stalled      latest reply is boilerplate / repeats earlier text
  regressed    latest reply contains negative language after an
               earlier positive claim

Trend analysis (Task 3.2): department × session attention matrix
with session-over-session deltas, theme × session (requires the
codebook layer), new-vs-recurring ratio, MLA diversity index.

Emerging issues (Task 3.3): subjects that first appeared in the
last 2–3 sessions, occur ≥2 times, and are asked by ≥2 MLAs.
"""

import re
import statistics
from collections import defaultdict

from . import response as resp
from .analysis import normalize_subject
from .codebook import normalize_dept

# Completion / progress language (legacy-derived, transparent).
RESOLVED_RE = re.compile(
    r"\b(?:completed|commissioned|operational|functional|inaugurated|"
    r"established|constructed|finalized|delivered|achieved|implemented)\b", re.I)
PROGRESS_RE = re.compile(
    r"\b(?:\d+\s*%|percent|partly|partially|in progress|under construction|"
    r"funds? (?:have |has )?(?:been )?(?:released|sanctioned|allocated)|"
    r"\d+\s*(?:of|out of)\s*\d+|so far|till (?:date|now))\b", re.I)
STALLED_RE = re.compile(
    r"\b(?:under (?:active )?consideration|receiving attention|"
    r"necessary steps (?:are being |will be )?taken|"
    r"at the (?:earliest|appropriate time)|in due course|"
    r"seized of the matter|being examined|being looked into)\b", re.I)
NEGATIVE_RE = re.compile(
    r"\b(?:not yet|has not been|have not been|no proposal|no funds?"
    r"|unable to|not in a position|nil|no assurance)\b", re.I)


def code_trajectory(session_replies):
    """Code a family's trajectory from ordered (session, reply) pairs."""
    if not session_replies:
        return "unknown", {}
    replies_present = [str(t or "") for _s, t in session_replies]
    if not any(r.strip() for r in replies_present):
        # OCR extraction has not covered this family yet
        return "awaiting_replies", {}
    first_reply = replies_present[0]
    last_reply = replies_present[-1]

    last_resolved = bool(RESOLVED_RE.search(last_reply))
    last_progress = bool(PROGRESS_RE.search(last_reply))
    last_stalled = bool(STALLED_RE.search(last_reply))
    last_negative = bool(NEGATIVE_RE.search(last_reply))
    first_positive = bool(RESOLVED_RE.search(first_reply) or PROGRESS_RE.search(first_reply))

    if last_negative and first_positive:
        status = "regressed"
    elif last_resolved and not last_negative:
        status = "resolved"
    elif last_progress and not last_stalled:
        status = "progressing"
    elif last_stalled or (not last_resolved and not last_progress and not last_negative):
        status = "stalled"
    else:
        status = "mixed"

    return status, {
        "first_positive": first_positive,
        "last_resolved": last_resolved,
        "last_progress": last_progress,
        "last_stalled": last_stalled,
        "last_negative": last_negative,
        "reply_len_first": len(first_reply),
        "reply_len_last": len(last_reply),
    }


def build_families(rows, subject_of, reply_lookup, session_order):
    """Group recurring subjects into families with cross-session replies.

    reply_lookup: pdf basename -> extracted record (may be empty dict).
    session_order: list of (assembly, session) sorted by first sitting.
    """
    families = defaultdict(list)
    for row in rows:
        key = normalize_subject(subject_of(row))
        if len(key) < 10:
            continue
        families[key].append(row)

    out = {}
    for key, group in families.items():
        sessions = {(r.get("Assembly") or "", r.get("Session") or "") for r in group}
        if len(sessions) < 2:
            continue
        by_session = defaultdict(list)
        for r in group:
            by_session[(r.get("Assembly") or "", r.get("Session") or "")].append(r)
        ordered = []
        for sk in session_order:
            if sk not in by_session:
                continue
            # one representative reply per session (first by question number)
            rep = sorted(by_session[sk], key=lambda r: str(r.get("Question_Number") or ""))[0]
            name = str(rep.get("Document_Link") or "").rsplit("/", 1)[-1]
            rec = reply_lookup.get(name, {})
            ordered.append((sk, rec.get("reply", ""), rep))
        status, detail = code_trajectory([(s, t) for s, t, _ in ordered])
        out[key] = {
            "subject": re.sub(r"\s+", " ", subject_of(group[0]) or "").strip(),
            "sessions": [f"{s[0].split()[0]} {s[1]}" for s, _t, _r in ordered],
            "occurrences": len(group),
            "departments": sorted({str(r.get("Departments") or "") for r in group}),
            "askers": sorted({str(r.get("Asked_By") or "") for r in group}),
            "trajectory": status,
            "detail": detail,
            "question_numbers": [str(r.get("Question_Number") or "") for r in group],
        }
    return out


def resolution_summary(families):
    counts = defaultdict(int)
    for f in families.values():
        counts[f["trajectory"]] += 1
    return dict(counts)


def department_trends(rows, session_order):
    """Department × session matrix with session-over-session deltas.

    Departments are normalized through the ported alias table so
    portal spelling variants ('Public Work Department(Road)' vs
    'Public Work (Roads)') do not split the series.
    """
    matrix = defaultdict(lambda: defaultdict(int))
    for r in rows:
        dept = normalize_dept(r.get("Departments"))
        matrix[dept][(r.get("Assembly") or "", r.get("Session") or "")] += 1

    per_dept = {}
    for dept, by_session in matrix.items():
        series = [by_session.get(sk, 0) for sk in session_order]
        deltas = [b - a for a, b in zip(series, series[1:])]
        per_dept[dept] = {
            "series": series,
            "sessions": [f"{sk[0].split()[0]} {sk[1]}" for sk in session_order],
            "total": sum(series),
            "sessions_active": sum(1 for v in series if v),
            "mean_delta": round(statistics.mean(deltas), 2) if deltas else 0.0,
            "last_delta": deltas[-1] if deltas else 0,
        }
    return per_dept


def theme_trends(rows, session_order):
    matrix = defaultdict(lambda: defaultdict(int))
    for r in rows:
        theme = r.get("_theme") or "General / Other"
        matrix[theme][(r.get("Assembly") or "", r.get("Session") or "")] += 1
    return {t: {f"{sk[0].split()[0]} {sk[1]}": by.get(sk, 0) for sk in session_order}
            for t, by in matrix.items()}


def new_vs_recurring(rows, subject_of, session_order):
    """Per-session share of questions on subjects seen in earlier sessions."""
    seen = set()
    out = {}
    by_session = defaultdict(list)
    for r in rows:
        by_session[(r.get("Assembly") or "", r.get("Session") or "")].append(r)
    for sk in session_order:
        group = by_session.get(sk, [])
        if not group:
            continue
        recurring = 0
        for r in group:
            key = normalize_subject(subject_of(r))
            if len(key) >= 10 and key in seen:
                recurring += 1
            if len(key) >= 10:
                seen.add(key)
        out[f"{sk[0].split()[0]} {sk[1]}"] = {
            "questions": len(group),
            "recurring": recurring,
            "new": len(group) - recurring,
            "recurring_pct": round(100 * recurring / len(group), 1),
        }
    return out


def diversity_index(rows, session_order):
    """Mean distinct departments questioned per MLA, per session."""
    out = {}
    by_session = defaultdict(lambda: defaultdict(set))
    for r in rows:
        by_session[(r.get("Assembly") or "", r.get("Session") or "")][
            str(r.get("Asked_By") or "")].add(str(r.get("Departments") or ""))
    for sk in session_order:
        mla_depts = by_session.get(sk, {})
        if mla_depts:
            out[f"{sk[0].split()[0]} {sk[1]}"] = round(
                statistics.mean(len(v) for v in mla_depts.values()), 2)
    return out


def emerging_issues(rows, subject_of, session_order, recent=3, min_occurrences=2):
    """Subjects first seen in the last `recent` sessions, asked by ≥2 MLAs."""
    by_subject = defaultdict(list)
    for r in rows:
        key = normalize_subject(subject_of(r))
        if len(key) >= 10:
            by_subject[key].append(r)

    recent_keys = set(session_order[-recent:])
    emerging = []
    for key, group in by_subject.items():
        sessions = {(r.get("Assembly") or "", r.get("Session") or "") for r in group}
        first = min(sessions, key=lambda s: session_order.index(s))
        askers = {str(r.get("Asked_By") or "") for r in group}
        if first in recent_keys and len(group) >= min_occurrences and len(askers) >= 2:
            emerging.append({
                "subject": re.sub(r"\s+", " ", subject_of(group[0]) or "").strip(),
                "first_session": f"{first[0].split()[0]} {first[1]}",
                "occurrences": len(group),
                "askers": sorted(askers),
                "departments": sorted({str(r.get("Departments") or "") for r in group}),
            })
    emerging.sort(key=lambda e: (-e["occurrences"], e["subject"]))
    return emerging


def session_order_of(rows):
    """(assembly, session) pairs ordered by first sitting date."""
    from .codebook import _clean  # noqa: F401  (kept for parity)
    from legislative_analysis.analysis import parse_date

    first_date = {}
    for r in rows:
        sk = (r.get("Assembly") or "", r.get("Session") or "")
        d = parse_date(r.get("Session_Date"))
        if sk not in first_date or (d and d < first_date[sk]):
            if d:
                first_date[sk] = d
    return sorted(first_date, key=lambda sk: first_date[sk])
