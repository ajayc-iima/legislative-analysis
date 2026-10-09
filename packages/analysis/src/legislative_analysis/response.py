"""Reply-side analysis: response pattern coding (Tasks 2.1–2.3).

Codes each OCR-extracted reply along four observable dimensions,
ported from the legacy registries (reference_data.py). Nothing is
collapsed into a composite score — each dimension is reported
separately, per the project's design principle.

Dimensions
  substantiveness  text-length band (brief/standard/detailed/very detailed)
  specificity      count of data points (numbers, dates, schemes, amounts)
  assurance        count of assurance-signal hits (SIGNAL_REGISTRY)
  evasion          count of evasion-signal hits (EVASION_REGISTRY)
  boilerplate      reply is mostly stock phrases (legacy regex)
  contradiction    positive claim + negative qualifier in one paragraph
  actionability    timeline / budget / named responsible party

Timeliness (Task 2.3): latency = reply_date − submission_date
where both were extracted; coverage reported alongside.
"""

import re
import statistics
from datetime import datetime

from . import reference_data as ref
from .codebook import _clean

LENGTH_BANDS = [
    (0, 200, "brief"),
    (200, 500, "standard"),
    (500, 1500, "detailed"),
    (1500, float("inf"), "very_detailed"),
]

SCHEME_RE = re.compile(
    r"\b(?:mission|scheme|yojana|programme?|project|policy|act)\b", re.I)
AMOUNT_RE = re.compile(
    r"(?:rs\.?|₹|rupees?)\s*[\d,]+(?:\.\d+)?\s*(?:crore|lakhs?|million)?"
    r"|\b\d[\d,]*\s*(?:crores?|lakhs?)\b", re.I)
DATE_RE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
    r"|\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", re.I)
RESPONSIBLE_RE = re.compile(
    r"\b(?:has been|have been|is being|are being)?\s*(?:directed|instructed|"
    r"asked|ordered)\b.*\b(?:to|by)\b"
    r"|\b(?:dc|district commissioner|secretary|officer|department|agency|"
    r"contractor|mepdcl|phed|pwd)\s+(?:has|have|is|are)\b"
    r"\b(?:directed|instructed|asked)\b", re.I)


def _signals(text, registry):
    """Count signal hits; returns (total_weight, {label: count})."""
    total, found = 0, {}
    for patterns in registry.values():
        for pattern, weight, label in patterns:
            n = len(re.findall(pattern, text, re.I))
            if n:
                total += weight * n
                found[label] = found.get(label, 0) + n
    return total, found


def code_reply(reply_text):
    """Code one reply. Returns a dict of the four dimensions."""
    text = str(reply_text or "")
    clean = _clean(text)

    # A. Substantiveness
    length = len(text)
    band = next((name for lo, hi, name in LENGTH_BANDS if lo <= length < hi),
                "brief")

    # B. Specificity — data-point census
    numbers = len(re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", clean))
    dates = len(DATE_RE.findall(text))
    schemes = len(SCHEME_RE.findall(text))
    amounts = len(AMOUNT_RE.findall(text))
    data_points = numbers + dates + schemes + amounts
    specificity = ("high" if data_points >= 3 else
                   "medium" if data_points >= 1 else "low")

    # C. Assurance vs evasion (ported registries)
    assurance_weight, assurance = _signals(text, ref.SIGNAL_REGISTRY)
    evasion_weight, evasion = _signals(text, ref.EVASION_REGISTRY)
    boilerplate = bool(ref._BOILERPLATE_REPLY_RE.search(text))

    # D. Actionability
    has_timeline = bool(
        any(re.search(p, text, re.I)
            for p, _w, _l in ref.SIGNAL_REGISTRY[ref.SignalType.TIME_BOUND_PLEDGE]))
    has_budget = (amounts > 0
                  or "amount_sanctioned" in assurance
                  or "funding_action" in assurance)
    has_responsible = bool(RESPONSIBLE_RE.search(text))

    # Contradiction: positive claim + negative qualifier in one paragraph
    paragraphs = [p for p in text.splitlines() if len(p.strip()) > 20]
    contradictions = [
        p.strip()[:200] for p in paragraphs
        if ref._CONTRA_POS_RE.search(p) and ref._CONTRA_NEG_RE.search(p)
    ]

    return {
        "substantiveness": {"band": band, "chars": length},
        "specificity": {"level": specificity, "data_points": data_points,
                        "numbers": numbers, "dates": dates,
                        "schemes": schemes, "amounts": amounts},
        "assurance": {"weight": assurance_weight, "signals": assurance},
        "evasion": {"weight": evasion_weight, "signals": evasion},
        "boilerplate": boilerplate,
        "contradiction": {"has_contradiction": bool(contradictions),
                          "paragraphs": contradictions[:3]},
        "actionability": {"has_timeline": has_timeline,
                          "has_budget": has_budget,
                          "has_responsible_party": has_responsible},
    }


def parse_iso(value):
    text = str(value or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return datetime(*map(int, m.groups()))
    return None


# Review notes that disqualify a date pair from timeliness measurement.
# The dates stay in the record (auditable); latency is only computed
# over pairs neither flagged as implausible nor self-contradictory.
# Shared with extract.flag_date_issues, which emits these flags.
DATE_FLAGS = ("far from sitting", "precedes submission")


def dates_trustworthy(record):
    """True when neither date carries an implausibility flag."""
    notes = " ".join(record.get("needs_review", [])).lower()
    return not any(flag in notes for flag in DATE_FLAGS)


def latency(reply_iso, submission_iso):
    """Days from submission to reply; None when either date missing."""
    a, b = parse_iso(reply_iso), parse_iso(submission_iso)
    if a and b:
        return (a - b).days
    return None


def timeliness_summary(records):
    """Aggregate latency over extracted records (Task 2.3)."""
    lats = [r["_latency_days"] for r in records if r.get("_latency_days") is not None]
    if not lats:
        return {"coverage": 0, "n": 0}
    ordered = sorted(lats)
    return {
        "coverage": round(100 * len(lats) / len(records), 1) if records else 0,
        "n": len(lats),
        "median_days": statistics.median(lats),
        "p75_days": ordered[int(0.75 * (len(ordered) - 1))],
        "share_over_30d": round(100 * sum(1 for d in lats if d > 30) / len(lats), 1),
        "share_over_90d": round(100 * sum(1 for d in lats if d > 90) / len(lats), 1),
        "min_days": ordered[0],
        "max_days": ordered[-1],
    }
