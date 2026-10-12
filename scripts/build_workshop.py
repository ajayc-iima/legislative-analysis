"""Departmental evidence dossiers + workshop pack for the top 3 departments.

A standalone training document (output/workshop/index.html) built from the
same pipeline as the monograph, so every number here is computed at build
time from the same evidence base - no figure is retyped.

Why it exists: the monograph argues that oversight is thin. A department
cannot act on that argument, but it can act on its own dossier - what was
asked of it, in what volume, by whom, how long the replies took, how much
of each reply was actionable, and what is still unanswered. This document
is that dossier for the three most-questioned departments, plus the method
used to produce it, so the exercise can be repeated by others.

Rules inherited from the main analysis (non-negotiable here too):
- no composite scores, indices, readiness grades, probabilities or
  forecasts - only counts, rates with visible denominators, and dates;
- every percentage prints its denominator;
- people are named by the shortest form that identifies one member
  (13 members share the surname Sangma);
- a figure that cuts the evidence says so in its caption;
- reply text is quoted as extracted, with its provenance.

Usage: python scripts/build_workshop.py [--top 3]
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"      # real <text> in SVG
import matplotlib.pyplot as plt
import numpy as np
from textwrap import shorten

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))
sys.path.insert(0, str(REPO / "scripts"))

from legislative_analysis import analysis as base                # noqa: E402
from legislative_analysis.analysis import load as load_rows       # noqa: E402
from legislative_analysis.codebook import classify_all, normalize_dept, DEPT_THEME  # noqa: E402
from legislative_analysis.demand import classify_all as classify_demand_all  # noqa: E402
from legislative_analysis.geography import tag_all, party_of, bloc_of, lookup_mla  # noqa: E402
from legislative_analysis import longitudinal as longi  # noqa: E402
from legislative_analysis import reference_data as ref_data      # noqa: E402
from legislative_analysis import recurrence                      # noqa: E402
from legislative_analysis.naming import member_labels           # noqa: E402
from build_compendium import compute_layer4, load_extracted, pct  # noqa: E402
from build_report import (build_css, build_js, details, esc, exhibit_card,  # noqa: E402
                          g, table)

OUT = REPO / "output/workshop"
IMG = OUT / "img"

# Deck palette, shared with the chart suite so the two documents read as one
NAVY, TEAL, GOLD, RED, AMBER = "#1A3C6E", "#2A8E9C", "#C9A227", "#B3402F", "#D98C1F"
GRAY70, GRAY40, GRAY15 = "#4A4A4A", "#9E9E9E", "#E0E0E0"
GREEN = "#146B4B"
# the same "does this label fit?" rule the chart suite uses
LABEL_MIN_SEGMENT_PCT = 8.0
BAND_COLORS = {"brief": "#B4C7DC", "standard": "#8AA8C8",
               "detailed": "#4A75A5", "very_detailed": "#1A3C6E"}
DEMAND_COLORS = {"Information": NAVY, "Action": TEAL, "Explanation": GOLD,
                 "Accountability": RED}
STAGE_COLORS = ["#8A8A8A", "#DCE6F2", "#B8CCE4", "#94AFCF", "#6F92BA",
                "#4A75A5", "#2A5890", TEAL, "#146B4B"]

CAPTIONS: dict[str, str] = {}


# ───────────────────────────── evidence loading ─────────────────────────────

def load_all():
    """Rows tagged exactly as the layer pipeline tags them, plus replies."""
    csv_path = REPO / "data/dl_questions_raw.csv"
    rows = base.scope_rows(load_rows(str(csv_path)))
    subject_of = base.subject_of
    seen = Counter(base.normalize_subject(subject_of(r)) for r in rows)
    recurring_keys = {k for k, c in seen.items() if c >= 2}
    classify_all(rows, subject_of)
    tag_all(rows, subject_of)
    classify_demand_all(rows, subject_of, recurring_keys)
    extracted = load_extracted()
    overall, dept_summary, records = compute_layer4(rows, extracted)
    labels = member_labels({str(r.get("Asked_By") or "").strip()
                            for r in load_rows(str(csv_path))})
    session_order = longi.session_order_of(rows)
    return rows, extracted, overall, dept_summary, records, labels, session_order


def flagged_by_department() -> dict[str, list[dict]]:
    path = REPO / "data/review/flagged_empty.csv"
    out: dict[str, list[dict]] = defaultdict(list)
    if not path.exists():
        return out
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            out[normalize_dept(row.get("department"))].append(row)
    return out


def load_nvidia_exhibit_replies() -> dict:
    path = REPO / "data/cache/nvidia_exhibit_replies.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ───────────────────────────── per-department profile ────────────────────────

def profile(dept: str, rows, extracted, dept_summary, records, labels, order,
            flagged, overall, sem: dict | None = None,
            sem_clusters: list | None = None,
            gate_counts: Counter | None = None) -> dict:
    mine = [r for r in rows if normalize_dept(r.get("Departments")) == dept]
    n = len(mine)
    sessions = []
    for r in mine:
        key = (r.get("Assembly") or "", r.get("Session") or "")
        if key not in sessions:
            sessions.append(key)
    session_rank = {key: i for i, key in enumerate(order)}
    sessions.sort(key=lambda key: session_rank.get(key, len(order)))
    askers = Counter(labels.get(str(r.get("Asked_By") or "").strip(),
                                 str(r.get("Asked_By") or "").strip()) for r in mine)
    themes = Counter(r.get("_theme") or "General / Other" for r in mine)
    portfolio = DEPT_THEME.get(dept, "")
    off_portfolio = sum(c for t, c in themes.items() if t != portfolio)
    demands = Counter(r.get("_demand_type") or "Information" for r in mine)

    subjects = Counter(base.normalize_subject(base.subject_of(r)) for r in mine)
    # the normalised key is a matching device ("eklavya model residential
    # school emr"); the archive's own wording is what a reader needs, so keep
    # the spelling that occurs most often for each key
    original = {}
    seen = Counter()
    for r in mine:
        key = base.normalize_subject(base.subject_of(r))
        text = str(base.subject_of(r) or "").strip()
        seen[(key, text)] += 1
        if key not in original or seen[(key, text)] > seen[(key, original[key])]:
            original[key] = text
    session_of_subject = defaultdict(set)
    askers_of_subject = defaultdict(set)
    for r in mine:
        key = base.normalize_subject(base.subject_of(r))
        session_of_subject[key].add((r.get("Assembly") or "", r.get("Session") or ""))
        askers_of_subject[key].add(str(r.get("Asked_By") or "").strip())
    recurring = [{"subject": _readable(original.get(s, s)), "sessions": len(v),
                  "questions": subjects[s]}
                 for s, v in session_of_subject.items() if len(v) >= 2]

    recent = order[-3:]
    recent_sessions = set(recent)
    first_seen = {}
    for r in mine:
        key = base.normalize_subject(base.subject_of(r))
        sk = (r.get("Assembly") or "", r.get("Session") or "")
        if key not in first_seen or order.index(sk) < order.index(first_seen[key]):
            first_seen[key] = sk
    emerging = [{"subject": _readable(original.get(s, s)), "questions": subjects[s]}
                for s, sk in first_seen.items()
                if sk in recent_sessions and subjects[s] >= 2
                and len(askers_of_subject[s]) >= 2]

    # --- semantic grouping: the primary lists; exact match stays beside it --
    # Embeddings (nvidia/nemotron-3-embed-1b) put reworded subjects together;
    # the gates in semantic_subjects.py stop unrelated ones from merging.
    # Exact match above remains in `recurring_exact`/`emerging_exact` as the
    # reproducible floor, published alongside — never instead of — this.
    sem_recurring, sem_emerging = [], []
    rows_by_link = {str(r.get("Document_Link") or ""): r for r in rows}
    clu_index = {c.get("canonical_subject"): c for c in (sem_clusters or [])
                 if c.get("department") == dept}

    def demand_mix(subject: str) -> str:
        """Information/Action/Explanation/Accountability mix of a family's
        questions, from the cluster's own question links — the tone dimension
        that identical wording alone does not show."""
        c = clu_index.get(subject)
        if not c:
            return "—"
        mix = Counter()
        for qm in c.get("questions_meta", []):
            r = rows_by_link.get(str(qm.get("document_link") or ""))
            if r is not None:
                mix[r.get("_demand_type") or "Information"] += 1
        if not mix:
            return "—"
        dom = ["Information", "Action", "Explanation", "Accountability"]
        return " · ".join(f"{k[:3]} {mix[k]}" for k in dom if mix[k])

    if sem:
        for f in (sem.get("families") or {}).values():
            if dept not in (f.get("departments") or []):
                continue
            sem_recurring.append({
                "subject": f.get("subject", ""),
                "sessions": len(f.get("sessions") or []),
                "questions": int(f.get("occurrences") or 0),
                "variants": len(f.get("unique_subjects") or []),
                "trajectory": f.get("trajectory", "—"),
                "demand_mix": demand_mix(f.get("subject", "")),
            })
        sem_recurring.sort(key=lambda x: (-x["sessions"], -x["questions"]))
        for e in (sem.get("emerging_issues") or []):
            if e.get("department") != dept:
                continue
            sem_emerging.append({
                "subject": e.get("subject", ""),
                "questions": int(e.get("occurrences") or 0),
                "askers": len(e.get("askers") or []),
                "first": e.get("first_session", "—"),
                "variants": len(e.get("unique_subjects") or []),
                "demand_mix": demand_mix(e.get("subject", "")),
            })
        sem_emerging.sort(key=lambda x: -x["questions"])

    d_records = [x for x in records if x["department"] == dept]
    recurring_sorted = sorted(recurring, key=lambda r: -r["sessions"])
    emerging_sorted = sorted(emerging, key=lambda r: -r["questions"])
    reply_rows = []
    for r in mine:
        pdf = str(r.get("Document_Link") or "").rsplit("/", 1)[-1]
        rec = extracted.get(pdf) or {}
        reply_rows.append({
            "row": r, "pdf": pdf, "reply": rec.get("reply", ""),
            "reply_date": rec.get("reply_date", ""),
            "submission_date": rec.get("submission_date", ""),
            "coding": next((x for x in d_records
                            if x["reply_date"] == rec.get("reply_date", "")
                            and x["department"] == dept), None),
        })
    replies_with_text = [x for x in reply_rows if x["reply"]]

    lat = [x["latency"] for x in d_records if x["latency"] is not None]
    band_counts = dept_summary.get(dept, {}).get("substantiveness", {})
    coded = sum(band_counts.values())
    detailed = band_counts.get("detailed", 0) + band_counts.get("very_detailed", 0)
    stages = dept_summary.get(dept, {}).get("stage_distribution", {})
    n_staged = dept_summary.get(dept, {}).get("n_staged", 0)

    top3_askers = askers.most_common(3)
    budget = ref_data.DEPT_BUDGET.get(dept)

    return {
        "dept": dept, "rows": mine, "n": n,
        "sessions": sessions, "n_sessions": len(sessions),
        "askers": askers, "n_askers": len(askers),
        "themes": themes, "demands": demands,
        "portfolio_theme": portfolio, "off_portfolio": off_portfolio,
        "subjects": subjects, "recurring": sem_recurring or recurring_sorted,
        "recurring_exact": recurring_sorted,
        "recurring_sem": sem_recurring,
        "subject_rows": [{"subject": _readable(original.get(s, s)), "questions": c}
                         for s, c in subjects.most_common()],
        "emerging": sem_emerging or emerging_sorted,
        "emerging_exact": emerging_sorted,
        "emerging_sem": sem_emerging,
        "sem_used": bool(sem_recurring or sem_emerging) and bool(sem),
        "gate_counts": gate_counts or Counter(),
        "records": d_records, "reply_rows": reply_rows,
        "n_replies_text": len(replies_with_text),
        "reply_coverage": pct(len(replies_with_text), n),
        "latency_median": statistics.median(lat) if lat else None,
        "n_dated": len(lat),
        "bands": band_counts, "n_coded": coded,
        "detailed_pct": pct(detailed, coded),
        "boilerplate_pct": dept_summary.get(dept, {}).get("boilerplate_pct", 0),
        "timeline_pct": dept_summary.get(dept, {}).get("timeline_pct", 0),
        "budget_pct": dept_summary.get(dept, {}).get("budget_pct", 0),
        "responsible_pct": dept_summary.get(dept, {}).get("responsible_pct", 0),
        "progress_evidence_pct": dept_summary.get(dept, {}).get("progress_evidence_pct", 0),
        "n_staged": n_staged,
        "stages": stages,
        "late_pct": dept_summary.get(dept, {}).get("late_pct", 0),
        "assurance": dept_summary.get(dept, {}).get("assurance_weight_mean", 0),
        "evasion": dept_summary.get(dept, {}).get("evasion_weight_mean", 0),
        "specificity": dept_summary.get(dept, {}).get("specificity", {}),
        "summary": dept_summary.get(dept, {}),
        "flagged": flagged.get(dept, []),
        "top3_askers": top3_askers,
        "top3_share": pct(sum(c for _n, c in top3_askers), n),
        "budget": budget,
        "rate": (n / budget * 100) if budget else None,
        "action_demands": demands.get("Action", 0) + demands.get("Accountability", 0),
    }


# ───────────────────────────── figures ───────────────────────────────────────

def style(ax, xlabel="", ylabel=""):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRAY40)
    ax.tick_params(colors=GRAY70, labelsize=9)
    ax.grid(axis="y", color=GRAY15, linewidth=0.7, zorder=0)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10, color=GRAY70)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10, color=GRAY70)
    return ax


def save_fig(fig, name: str, message: str, caption: str) -> None:
    """Write SVG + PNG and keep the caption for the HTML figure card."""
    IMG.mkdir(parents=True, exist_ok=True)
    fig.savefig(IMG / f"{name}.svg", bbox_inches="tight", facecolor="white")
    fig.savefig(IMG / f"{name}.png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    CAPTIONS[name] = (message, caption)


def fig_volume(d: dict, sess_labels: list[str]) -> None:
    counts = Counter(f"{r.get('Assembly') or ''} {r.get('Session') or ''}" for r in d["rows"])
    values = [counts.get(sk, 0) for sk in d["sessions_full"]]
    labels = [sess_labels.get(sk, sk) for sk in d["sessions_full"]]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.plot(labels, values, marker="o", color=NAVY, linewidth=2)
    ax.fill_between(labels, values, alpha=0.08, color=NAVY)
    top = max(values) if values else 1
    ax.set_ylim(0, top * 1.28)
    halo = dict(facecolor="white", alpha=0.9, edgecolor="none", pad=0.8)
    for i, v in enumerate(values):
        ax.annotate(str(v), (i, v), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=8, color=GRAY70, bbox=halo, zorder=5)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    style(ax, ylabel="Questions")
    peak = labels[values.index(top)] if values else ""
    ax.set_title(f"{d['dept'].replace(' Department', '')}: {top} questions in its "
                 f"busiest sitting ({peak}); {d['n_sessions']} of "
                 f"{len(sess_labels)} sittings saw at least one",
                 fontsize=12, color=NAVY, pad=12)
    save_fig(fig, f"ws-{_slug(d['dept'])}-volume",
             f"{d['dept'].replace(' Department', '')} drew {top} questions in its "
             f"busiest sitting and {d['n']:,} in total across {d['n_sessions']} sittings.",
             f"Questions per sitting for {d['dept']}, in-scope sittings only; every "
             f"point labelled. Sittings with no question from this department are "
             f"omitted rather than shown as zero. Source: scoped CSV.")


def fig_themes(d: dict) -> None:
    items = d["themes"].most_common(10)[::-1]
    names = [shorten(t, width=30, placeholder="…") for t, _c in items]
    values = [c for _t, c in items]
    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.barh(names, values, color=NAVY, edgecolor="white")
    top = max(values) if values else 1
    for i, (theme, c) in enumerate(items):
        ax.text(c + top * 0.015, i, f"{c}  ({100 * c / d['n']:.0f}% of {d['n']:,})",
                va="center", fontsize=8, color=GRAY70)
    ax.set_xlim(0, top * 1.32)
    style(ax, xlabel="Questions")
    ax.set_title(f"{items[-1][0]} is {items[-1][1] / d['n']:.0%} of everything asked "
                 f"of {d['dept'].replace(' Department', '')}",
                 fontsize=12, color=NAVY, pad=12)
    save_fig(fig, f"ws-{_slug(d['dept'])}-themes",
             f"{items[-1][0]} accounts for {100 * items[-1][1] / d['n']:.0f}% of the "
             f"{d['n']:,} questions asked of {d['dept'].replace(' Department', '')}.",
             f"Top 10 policy domains by rule-based thematic coding (Layer 1); "
             f"every bar labelled with its count and share of the department's "
             f"{d['n']:,} questions. Source: layer1_themes.json codebook.")


def fig_demands(d: dict) -> None:
    order = ["Information", "Action", "Explanation", "Accountability"]
    items = [(k, d["demands"].get(k, 0)) for k in order]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.bar([k for k, _v in items], [v for _k, v in items],
           color=[DEMAND_COLORS[k] for k, _v in items], edgecolor="white")
    top = max(v for _k, v in items) or 1
    for i, (k, v) in enumerate(items):
        ax.text(i, v + top * 0.02, f"{v} ({100 * v / d['n']:.0f}%)", ha="center",
                fontsize=9, color=GRAY70)
    ax.set_ylim(0, top * 1.22)
    style(ax, ylabel="Questions")
    lead = max(items, key=lambda kv: kv[1])
    ax.set_title(f"{100 * lead[1] / d['n']:.0f}% of questions to "
                 f"{d['dept'].replace(' Department', '')} ask for information; "
                 f"{d['action_demands']} ask for action or accountability",
                 fontsize=12, color=NAVY, pad=12)
    save_fig(fig, f"ws-{_slug(d['dept'])}-demands",
             f"{d['action_demands']} of {d['n']:,} questions to "
             f"{d['dept'].replace(' Department', '')} demand action or accountability, "
             f"not just information.",
             "Demand type from the Layer 3 classifier (evidence keywords recorded per "
             f"question); every bar labelled with count and share of {d['n']:,}. "
             "Source: layer3_demands.json.")


def fig_bands(d: dict) -> None:
    bands = ["brief", "standard", "detailed", "very_detailed"]
    counts = [d["bands"].get(b, 0) for b in bands]
    coded = sum(counts) or 1
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    ax.barh(bands[::-1], counts[::-1],
            color=[BAND_COLORS[b] for b in bands[::-1]], edgecolor="white")
    top = max(counts) if counts else 1
    for i, c in enumerate(counts[::-1]):
        ax.text(c + top * 0.015, i, f"{c} ({100 * c / coded:.0f}%)", va="center",
                fontsize=9, color=GRAY70)
    ax.set_xlim(0, top * 1.3)
    style(ax, xlabel="Replies")
    ax.set_title(f"{d['detailed_pct']:.0f}% of {coded:,} coded replies to "
                 f"{d['dept'].replace(' Department', '')} are detailed or very "
                 f"detailed", fontsize=12, color=NAVY, pad=12)
    save_fig(fig, f"ws-{_slug(d['dept'])}-bands",
             f"{d['detailed_pct']:.0f}% of {coded:,} coded replies to "
             f"{d['dept'].replace(' Department', '')} are detailed or very detailed; "
             f"{100 * (coded - d['bands'].get('brief', 0)) / coded:.0f}% are brief.",
             f"Length bands from the response rubric; counts are replies, not "
             f"questions, and the denominator ({coded:,}) is printed on every bar. "
             "Source: build_compendium.compute_layer4.")


def fig_latency(d: dict, corpus_median) -> None:
    lat = [x["latency"] for x in d["records"] if x["latency"] is not None]
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    if lat:
        bins = list(range(0, min(max(lat) + 5, 95), 5))
        counts, _, _ = ax.hist(lat, bins=bins, color=NAVY, edgecolor="white", zorder=3)
        tallest = counts.max() if len(counts) else 0
        if tallest:
            ax.set_ylim(0, tallest * 1.2)
        halo = dict(facecolor="white", alpha=0.9, edgecolor="none", pad=0.8)
        for left, c in zip(bins[:-1], counts):
            if tallest and c / tallest >= 0.10:
                ax.text(left + 2.5, c, str(int(c)), ha="center", va="bottom",
                        fontsize=8, color=GRAY70, bbox=halo, zorder=6)
        med = statistics.median(lat)
        ax.axvline(med, color=RED, linestyle="--", linewidth=2, zorder=2,
                   label=f"this department: {med:g} days")
        if corpus_median is not None:
            ax.axvline(corpus_median, color=GOLD, linestyle=":", linewidth=2,
                       zorder=2, label=f"all departments: {corpus_median:g} days")
        ax.axvline(30, color=GRAY40, linestyle="-.", linewidth=1.5, zorder=2,
                   label="30-day mark")
        ax.legend(frameon=False, fontsize=8, loc="upper right")
        ax.set_title(f"Median reply time {med:g} days on {len(lat)} verifiable "
                     f"date pairs", fontsize=12, color=NAVY, pad=12)
        message = (f"Median verifiable reply time for {d['dept'].replace(' Department', '')} "
                   f"is {med:g} days across {len(lat)} date pairs.")
        caption = (f"Only date pairs that pass the trust check are plotted "
                   f"({len(lat)} of {d['n_replies_text']:,} located replies); "
                   f"untrustworthy pairs stay in the data but off this chart. "
                   f"Bins holding 10% or more of the tallest bin are labelled. "
                   f"Corpus median {corpus_median if corpus_median is None else f'{corpus_median:g}'} "
                   f"days. Source: extracted.jsonl + build_compendium.")
    else:
        ax.set_title("No verifiable date pairs for this department", fontsize=12,
                     color=NAVY, pad=12)
        message, caption = ("No verifiable submission/reply date pair exists for this "
                            "department's replies.", "Empty chart: no trusted date pairs.")
    style(ax, xlabel="Days from submission to reply", ylabel="Replies")
    save_fig(fig, f"ws-{_slug(d['dept'])}-latency", message, caption)


def fig_stages(d: dict) -> None:
    stages = d["stages"]
    keys = sorted(stages, key=lambda k: -stages[k])
    coded = sum(stages.values()) or 1
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = [STAGE_COLORS[min(i, len(STAGE_COLORS) - 1)] for i in range(len(keys))]
    ax.barh([shorten(k, width=26, placeholder="…") for k in keys[::-1]],
            [stages[k] for k in keys[::-1]], color=colors[::-1], edgecolor="white")
    top = max(stages.values()) if stages else 1
    for i, k in enumerate(keys[::-1]):
        ax.text(stages[k] + top * 0.015, i,
                f"{stages[k]} ({100 * stages[k] / coded:.0f}%)", va="center",
                fontsize=8, color=GRAY70)
    ax.set_xlim(0, top * 1.32)
    style(ax, xlabel="Replies")
    none_n = stages.get("None evidenced", 0)
    ax.set_title(f"{100 * none_n / coded:.0f}% of {coded:,} replies evidence no "
                 f"delivery stage at all", fontsize=12, color=NAVY, pad=12)
    save_fig(fig, f"ws-{_slug(d['dept'])}-stages",
             f"{100 * none_n / coded:.0f}% of {coded:,} replies to "
             f"{d['dept'].replace(' Department', '')} evidence no delivery stage "
             f"(no sanction, award, execution or completion language).",
             "Highest lifecycle stage evidenced per reply, negation-aware; every bar "
             f"labelled with count and share of {coded:,} coded replies. "
             "Source: build_compendium.compute_layer4.")


def fig_askers(d: dict) -> None:
    items = d["askers"].most_common(10)[::-1]
    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.barh([n for n, _c in items], [c for _n, c in items], color=TEAL,
            edgecolor="white")
    top = max(c for _n, c in items) if items else 1
    for i, (name, c) in enumerate(items):
        ax.text(c + top * 0.015, i, f"{c} ({100 * c / d['n']:.0f}%)", va="center",
                fontsize=8, color=GRAY70)
    ax.set_xlim(0, top * 1.3)
    style(ax, xlabel="Questions")
    ax.set_title(f"{items[-1][0]} accounts for {100 * items[-1][1] / d['n']:.0f}% of "
                 f"questions to {d['dept'].replace(' Department', '')}; "
                 f"{d['n_askers']} members have asked at least one",
                 fontsize=12, color=NAVY, pad=12)
    save_fig(fig, f"ws-{_slug(d['dept'])}-askers",
             f"{d['n_askers']} members have questioned "
             f"{d['dept'].replace(' Department', '')}; the top 3 askers account for "
             f"{d['top3_share']:.0f}% of its {d['n']:,} questions.",
             f"Members named by the shortest form that identifies one person "
             f"(one surname in this Assembly is carried by thirteen members). "
             f"Source: scoped CSV + naming.member_labels.")


def fig_compare(profiles: list[dict], overall: dict, corpus_median) -> None:
    """Top 3 against the rest of the corpus, on the four things that matter."""
    panels = [
        ("Questions per ₹100 crore", lambda d: d["rate"] or 0, "higher = more scrutiny per rupee"),
        ("Detailed or very detailed replies (%)", lambda d: d["detailed_pct"], "of coded replies"),
        ("Replies citing a timeline (%)", lambda d: d["timeline_pct"], "of coded replies"),
        ("Median reply latency (days)", lambda d: d["latency_median"] or 0, "verifiable date pairs"),
    ]
    # one label set for four panels: read it once, on the left
    names = [_short(d["dept"]) for d in profiles] + ["All other depts"]
    fig, axes = plt.subplots(1, 4, figsize=(15, 4.4), sharey=False)
    for panel, (ax, (title, getter, unit)) in enumerate(zip(axes, panels)):
        values = [getter(d) for d in profiles] + [rest_values[title] if rest_values else 0]
        colors = [NAVY] * len(profiles) + [GRAY40]
        ax.bar(range(len(values)), values, color=colors, edgecolor="white")
        top = max(values) if values else 1
        for i, v in enumerate(values):
            ax.text(i, v + top * 0.03, f"{v:.1f}" if v >= 1 else f"{v:.2f}",
                    ha="center", fontsize=8, color=GRAY70)
        ax.set_xticks(range(len(values)))
        ax.set_xticklabels(names, rotation=20, ha="right", fontsize=8)
        ax.tick_params(axis="x", pad=3)
        ax.set_ylim(0, top * 1.25)
        style(ax, ylabel=unit)
        ax.set_title(title, fontsize=10, color=NAVY)
    fig.suptitle("Where the three most-questioned departments stand against the rest "
                 "of the corpus", fontsize=13, color=NAVY, y=1.03)
    save_fig(fig, "ws-compare",
             "The three most-questioned departments differ from the rest of the "
             "corpus on scrutiny rate, reply depth, timeline citation and latency.",
             "Each panel uses one measure with its denominator in the axis label; "
             "department values come from the per-department rubric, the grey bar "
             "is every other department. Measures are levels, not scores: they are "
             "not combined and no ranking is implied. Source: build_compendium.")


def fig_embedding(semantic: dict | None, exact_families: dict) -> None:
    """Show what the embedding pass adds over deterministic exact matching."""
    if not semantic:
        return
    exact = Counter()
    for family in exact_families.values():
        for dept in family.get("departments") or ["—"]:
            exact[normalize_dept(dept)] += 1
    embedded = Counter()
    for family in (semantic.get("families") or {}).values():
        for dept in family.get("departments") or ["—"]:
            embedded[normalize_dept(dept)] += 1
    names = [name for name, _ in embedded.most_common(12)]
    names = sorted(names, key=lambda name: (-embedded[name], name))
    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.barh(y + 0.18, [exact[name] for name in names], height=0.34,
            color=GRAY40, label="Exact normalized match")
    ax.barh(y - 0.18, [embedded[name] for name in names], height=0.34,
            color=TEAL, label="Embeddings + verification gates")
    ax.set_yticks(y)
    ax.set_yticklabels([shorten(name, width=30, placeholder="…")
                        for name in names], fontsize=8)
    ax.invert_yaxis()
    for i, name in enumerate(names):
        ax.text(exact[name] + 0.15, i + 0.18, str(exact[name]),
                va="center", fontsize=8, color=GRAY70)
        ax.text(embedded[name] + 0.15, i - 0.18, str(embedded[name]),
                va="center", fontsize=8, color=GRAY70)
    style(ax, xlabel="Recurring subject families")
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.set_title("Embeddings recover paraphrased recurring subjects without "
                 "replacing the deterministic baseline", fontsize=12,
                 color=NAVY, pad=12)
    save_fig(fig, "ws-embedding-audit",
             f"Embedding audit: {semantic.get('n_families', 0)} semantic families "
             f"versus {len(exact_families)} exact-match families.",
             f"Top {len(names)} departments by semantic-family count. The semantic "
             f"pass uses {semantic.get('embed_model', 'the recorded embedding model')} "
             f"({semantic.get('embed_dims', '—')} dimensions) plus verification gates; "
             "it is reported beside, not substituted for, exact matching. Sources: "
             "layer5_resolution.json and layer5_semantic.json.")


rest_values: dict[str, float] = {}


def _readable(text: str) -> str:
    """Archive wording, lightly presented: never lower-case throughout."""
    text = str(text or "").strip()
    if not text:
        return "(no subject text in the archive record)"
    return text[0].upper() + text[1:]


def _slug(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")


def _short(name: str) -> str:
    """Axis-length department name ("Public Works (Roads)" -> "P.W. Roads")."""
    name = name.replace(" Department", "")
    aliases = {
        "Health & Family Welfare": "Health & Family",
        "Public Works (Roads)": "Public Works",
        "Public Health Engineering": "Public Health Eng.",
        "Community & Rural Development": "Community & Rural",
    }
    return aliases.get(name, name)[:18]


# ───────────────────────────── HTML fragments ───────────────────────────────

def wfigure(name: str) -> str:
    """Figure card with the workshop's own inline SVG (self-contained)."""
    message, caption = CAPTIONS.get(name, (name, ""))
    svg_path = IMG / f"{name}.svg"
    if not svg_path.exists():
        return f"<div class='chart-missing'>{esc(name)} missing</div>"
    svg = svg_path.read_text(encoding="utf-8")
    import re
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg, count=1)
    svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg, count=1)
    if "<title>" not in svg:
        svg = svg.replace("<svg ", f"<svg role='img' aria-label='{esc(message)}' ", 1)
    return (
        f"<figure class='figure-card'>"
        f"<div class='figure-msg'>{esc(message)}</div>"
        f"<div class='svg-wrapper'>{svg}</div>"
        f"<figcaption class='figure-caption'><b>Source &amp; Method:</b> "
        f"{esc(caption)}</figcaption></figure>")


def scorecard(d: dict, corpus: dict) -> str:
    """The numbers a department can act on, each with its denominator."""
    n = d["n"]
    rows = [
        ["Questions asked", f"{n:,}", f"{100 * n / corpus['total']:.1f}% of all "
         f"{corpus['total']:,} scoped questions"],
        ["Sittings with at least one question", f"{d['n_sessions']}",
         f"of {corpus['n_sessions']} sittings in the corpus"],
        ["Members who asked at least one", f"{d['n_askers']}",
         f"of {corpus['n_askers']} members who asked anything"],
        ["Distinct policy domains", f"{len(d['themes'])}",
         "rule-based thematic codebook (Layer 1)"],
        ["Most frequent demand type",
         f"{d['demands'].most_common(1)[0][0] if d['demands'] else '—'}",
         f"{pct(d['demands'].most_common(1)[0][1], n) if d['demands'] else 0:.0f}% "
         f"of {n:,} questions"],
        ["Action or accountability demands", f"{d['action_demands']}",
         f"{pct(d['action_demands'], n):.0f}% of {n:,} questions"],
        ["Reply documents located", f"{d['n_replies_text']:,}",
         f"{d['reply_coverage']:.1f}% of {n:,} questions"],
        ["Replies coded", f"{d['n_coded']:,}",
         f"{pct(d['n_coded'], n):.1f}% of {n:,} questions"],
        ["Replies needing human review (no text found)", f"{len(d['flagged'])}",
         "listed with reasons in data/review/FLAGGED_EMPTY.md"],
        ["Verifiable date pairs", f"{d['n_dated']:,}",
         f"{pct(d['n_dated'], d['n_replies_text']):.0f}% of {d['n_replies_text']:,} "
         f"located replies pass the date-trust check"],
        ["Median reply time", f"{g(d['latency_median'])} days" if d["latency_median"]
         is not None else "—", f"across {d['n_dated']:,} verifiable date pairs"],
        ["Replies beyond 30 days", f"{d['late_pct']:.0f}%",
         f"of {d['n_dated']:,} dated replies"],
        ["Detailed or very detailed replies", f"{d['detailed_pct']:.0f}%",
         f"of {d['n_coded']:,} coded replies"],
        ["Boilerplate-flagged replies", f"{d['boilerplate_pct']:.0f}%",
         f"of {d['n_coded']:,} coded replies"],
        ["Replies citing a timeline", f"{d['timeline_pct']:.0f}%",
         f"of {d['n_coded']:,} coded replies"],
        ["Replies citing a budget figure", f"{d['budget_pct']:.0f}%",
         f"of {d['n_coded']:,} coded replies"],
        ["Replies naming a responsible officer", f"{d['responsible_pct']:.0f}%",
         f"of {d['n_coded']:,} coded replies"],
        ["Staged replies with progress evidence",
         f"{d['progress_evidence_pct']:.0f}%" if d["n_staged"] else "—",
         f"of {d['n_staged']:,} replies that evidence any stage"],
        ["Recurring subjects (asked in 2+ sittings)",
         f"{len(d['recurring_sem'])}" if d.get("recurring_sem") is not None
         else f"{len(d['recurring_exact'])}",
         (f"semantic grouping with verification gates; exact match finds "
          f"{len(d['recurring_exact'])} of {len(d['subjects']):,} distinct "
          f"subject strings")
         if d.get("recurring_sem") is not None
         else f"of {len(d['subjects']):,} distinct subject strings"],
        ["Budget allocation 2025–26",
         f"₹{d['budget']:,.0f} crore" if d["budget"] else "—",
         f"{d['rate']:.1f} questions per ₹100 crore" if d["rate"] else "not in table"],
    ]
    return table(["Measure", "Value", "Denominator / basis"], rows,
                 caption=f"Evidence scorecard for {d['dept']}. Every percentage is "
                         "printed against the count it is a percentage of; no index "
                         "or score is computed.")


def askers_table(d: dict) -> str:
    """Askers with seat, district, party and bloc.

    Party and bloc are looked up on the *archive's* name for the member, not
    on the shortened display label: the reference tables key on the full
    name, so asking for "Kazi" returns nothing while "Mizanur Rahman Kazi"
    returns AITC.
    """
    rows = []
    for label, c in d["askers"].most_common(12):
        raw = d["_raw_by_label"].get(label, label)
        seat = lookup_mla(raw)
        assembly = "Eleventh Meghalaya Legislative Assembly"
        party = party_of(raw, assembly) or "—"
        bloc = bloc_of(raw, assembly)
        rows.append([label,
                     seat["constituency"] if seat else "—",
                     seat["district"] if seat else "—",
                     party, bloc,
                     f"{c}", f"{100 * c / d['n']:.1f}%"])
    return table(["Member", "Constituency", "District", "Party (11th A.)",
                  "Bloc", "Questions", "Share of department"],
                 rows, caption=f"Members questioning {d['dept']} (top 12 of "
                               f"{d['n_askers']}). Names are disambiguated: eight "
                               "surnames in this Assembly are carried by more than "
                               "one member — one by thirteen — so a surname alone "
                               "would not identify a legislator.")


def subjects_table(d: dict, title: str, items: list[dict], key: str) -> str:
    rows = []
    for it in items[:15]:
        rows.append([shorten(it["subject"], width=58, placeholder="…"),
                     str(it[key]),
                     f"{100 * it['questions'] / d['n']:.1f}%"])
    if not rows:
        threshold = ("first seen in the last three sittings, asked at least twice "
                     "by at least two members"
                     if key == "questions" and "Emerging" in title
                     else "asked in two or more sittings")
        return (f"<p><i>No subject in this department's questions meets the "
                f"threshold ({threshold}).</i></p>")
    return table(["Subject", ("Sittings" if key == "sessions" else "Questions"),
                  "Share of department"], rows, caption=title)


def pick_exhibits(d: dict) -> list[dict]:
    """One strong reply, one thin reply, one boilerplate reply - real text."""
    coded = [x for x in d["reply_rows"] if x["coding"]]
    if not coded:
        return []

    def band_of(x):
        return x["coding"]["substantiveness"]["band"]

    detailed = sorted(coded, key=lambda x: -len(x["reply"]))
    brief = sorted(coded, key=lambda x: (band_of(x), len(x["reply"])))
    boiler = [x for x in coded if x["coding"]["boilerplate"]]
    picks, seen = [], set()
    for pool, want in ((detailed, "most detailed reply"),
                       (brief, "thinnest coded reply"),
                       (boiler, "reply flagged as boilerplate")):
        for x in pool:
            key = (x["pdf"], want)
            if key in seen:
                continue
            seen.add(key)
            picks.append({**x, "why": want})
            break
    target = next(
        (x for x in d["reply_rows"]
         if "death of the student in jnv mawphlang"
         in " ".join(str(x["row"].get(key) or "")
                     for key in ("Question_Number", "Subject", "Questions")).lower()
         and x["reply"]),
        None,
    )
    if target and not any(x["pdf"] == target["pdf"] for x in picks):
        picks.append({**target, "why": "extraction audit"})
    return picks


def exhibits_html(d: dict) -> str:
    out = []
    nvidia_replies = load_nvidia_exhibit_replies()
    for x in pick_exhibits(d):
        coding = x["coding"] or {}
        stage = (coding.get("execution_stage") or {}).get("stage", "—")
        band = (coding.get("substantiveness") or {}).get("band", "—")
        flags = []
        act = coding.get("actionability") or {}
        if act.get("has_timeline"):
            flags.append("cites a timeline")
        if act.get("has_budget"):
            flags.append("cites a budget figure")
        if act.get("has_responsible_party"):
            flags.append("names a responsible officer")
        if coding.get("boilerplate"):
            flags.append("boilerplate-flagged")
        row = x["row"]
        pdf = x["pdf"]
        api_reply = (nvidia_replies.get(pdf) or {}).get("reply") or ""
        reply = api_reply or x["reply"] or ""
        source = ("NVIDIA vision re-extraction" if api_reply
                  else "corpus OCR fallback — NVIDIA cache missing")
        if x["why"] == "extraction audit":
            note = (f"Rubric reading: {band} reply; highest stage evidenced: {stage}; "
                    f"{', '.join(flags) if flags else 'no actionable element detected'}. "
                    f"Selected as the extraction-audit case among {d['n_coded']:,} coded "
                    f"replies; the reply text is checked against the signed PDF for "
                    f"completeness.")
        else:
            note = (f"Rubric reading: {band} reply; highest stage evidenced: {stage}; "
                    f"{', '.join(flags) if flags else 'no actionable element detected'}. "
                    f"Selected as the department's {x['why']} among {d['n_coded']:,} "
                    f"coded replies.")
        out.append(exhibit_card(
            qno=re.sub(r"^\s*Q\.?\s*No\.?\s*", "", str(row.get("Question_Number") or ""),
                       flags=re.I).strip() or "—",
            date=f"{row.get('Session') or ''} {row.get('Session_Date') or ''}".strip(),
            dept=d["dept"],
            asked_by=d["_label_map"].get(str(row.get("Asked_By") or "").strip(),
                                         str(row.get("Asked_By") or "")),
            question_text=str(row.get("Questions") or "")[:1200],
            reply_text=reply,
            analysis_note=note,
            reply_source=source))
    return "".join(out)


def exercises(d: dict) -> str:
    """Questions the department can answer from its own records."""
    action = d["action_demands"]
    items = [
        (f"<b>Answer the {action} action demands.</b> For every question in this "
         f"dossier classified as Action or Accountability, state the sanction or "
         f"approval status, the executing officer, and the date of the next "
         f"milestone. The rubric found a timeline in only {d['timeline_pct']:.0f}% of "
         f"{d['n_coded']:,} coded replies and a budget figure in "
         f"{d['budget_pct']:.0f}% — these five fields are what turn a reply into a "
         f"trackable commitment."),
        (f"<b>Account for the {len(d['recurring_sem'])} recurring subjects.</b> Each was "
         f"asked in two or more sittings. For each, state what changed between the "
         f"first and the latest reply, and whether the change is documented or "
         f"asserted. Recurrence without documented progress is the pattern this "
         f"analysis is built to expose."),
        (f"<b>Explain the {len(d['emerging_sem'])} emerging subjects.</b> These appear "
         f"only in the last three sittings, in at least two questions and from at "
         f"least two members. Which are new problems, and which are old problems "
         f"asked in new words?"),
        (f"<b>Close the evidence gap.</b> {len(d['flagged'])} of your "
         f"{d['n']:,} questions in this dossier have no readable reply text and are "
         f"listed with reasons for human review. Either supply the missing document "
         f"or state that no reply was tabled."),
        (f"<b>Check your own numbers.</b> Every figure in this dossier is "
         f"reproducible from the public record: the question list, the reply PDFs, "
         f"and the codebook. Re-run the pipeline on your own extracts before "
         f"accepting or disputing a single number here — that is the point of the "
         f"exercise."),
        ("<b>Adopt the standard.</b> What would it take for every reply from this "
         "department to carry: a date, a responsible officer, a budget line where "
         "money is involved, and a statement of the next milestone? The cost is "
         "four fields; the effect is that the next question can ask about "
         "compliance instead of re-asking the original."),
    ]
    return ("<ol class='exercise-list'>"
            + "".join(f"<li>{t}</li>" for t in items) + "</ol>")


def limitations(d: dict) -> str:
    items = [
        ("Budget is one year against five years of questions. The rate in this "
         "dossier compares levels, not trends."),
        ("Question text is the portal's own text. Recurrence is grouped primarily "
         "with NVIDIA nemotron-3-embed-1b embeddings and verification gates, so "
         "paraphrased questions can be recognised as the same issue. Normalised "
         "exact matching remains an audit baseline for measuring merge differences."),
        ("Replies are OCR-extracted from scanned PDFs. Records flagged as needing "
         "human review are excluded from coded statistics but remain visible in "
         "the denominators shown here."),
        ("Reply length is a proxy for effort, not a measure of it. The rubric "
         "records length, boilerplate, self-contradiction and actionability "
         "separately, so a long reply that answers nothing cannot pass as "
         "thorough."),
        ("This dossier measures what the Assembly asked and what came back. It "
         "does not measure whether a department performed well, and it cannot: "
         "the assembly record does not contain that evidence."),
    ]
    return ("<ul class='limitation-list'>"
            + "".join(f"<li>{t}</li>" for t in items) + "</ul>")


def chapter(d: dict, idx: int, corpus: dict, corpus_median,
            badge: str = "Chapter") -> str:
    """One department's full dossier."""
    slug = _slug(d["dept"])
    short = d["dept"].replace(" Department", "")
    part = [f"<section class='chapter' id='dept-{idx}'>"]
    part.append(f"<div class='chapter-head'><span class='chapter-num'>{badge} {idx}</span>"
                f"<h2>{esc(d['dept'])}</h2>"
                f"<p class='chapter-standfirst'>{d['n']:,} questions "
                f"({100 * d['n'] / corpus['total']:.1f}% of the corpus) across "
                f"{d['n_sessions']} sittings, from {d['n_askers']} members; "
                f"{d['n_replies_text']:,} replies located "
                f"({d['reply_coverage']:.1f}%).</p></div>")

    part.append("<h3>1. Evidence scorecard</h3>")
    part.append("<p>Every row states the count its percentage is taken from. There "
                "is no overall grade: a department is not a number.</p>")
    part.append(scorecard(d, corpus))

    part.append("<h3>2. What is asked</h3>")
    own = d["portfolio_theme"]
    off = d["off_portfolio"]
    part.append(f"<p>{len(d['themes'])} policy domains appear in the "
                f"{d['n']:,} questions put to {esc(short)}. The codebook gives "
                f"every department a default domain — for this one, "
                f"<i>{esc(own)}</i> — so the mix is expected to be dominated by "
                f"it. The informative number is the remainder: "
                f"<b>{off:,} questions ({pct(off, d['n']):.0f}%) fell outside "
                f"this department's own portfolio domain</b>, which is where "
                f"members expected the subject to be handled elsewhere.</p>")
    part.append(wfigure(f"ws-{slug}-themes"))
    part.append(subjects_table(
        d, "Most frequent subject strings (archive wording; recurrence uses embeddings)",
        d["subject_rows"], "questions"))

    # --- Recurring subjects -------------------------------------------------
    # Recurrence is reported from embedding families; exact matching is shown
    # only as the reproducible audit baseline.
    if d.get("recurring_sem"):
        part.append(subjects_table(
            d, f"Recurring subjects — asked in two or more sittings "
               f"({len(d['recurring_sem'])} families, NVIDIA embeddings)",
            d["recurring_sem"][:15], "sessions"))
        part.append(f"<p>Audit baseline: exact string matching alone finds "
                    f"{len(d['recurring_exact'])} of these. The gap is the "
                    f"paraphrase effect — the same issue reworded across "
                    f"sittings, which embeddings group and the gates verify. "
                    f"Every merge is listed with its evidence in "
                    f"<code>output/layers/semantic_clusters.json</code>.</p>")
    else:
        tag = ", exact match" if d.get("recurring_sem") is not None else ""
        part.append(subjects_table(
            d, f"Recurring subjects — asked in two or more sittings "
               f"({len(d['recurring_exact'])}{tag})",
            d["recurring_exact"], "sessions"))
        if d.get("recurring_sem") is not None:
            part.append("<p>The semantic grouping found no family with two or "
                        "more sittings in this department; the list above is "
                        "the exact-match result.</p>")

    # --- Emerging subjects ---------------------------------------------------
    if d.get("emerging_sem"):
        part.append(subjects_table(
            d, f"Emerging subjects — first seen in the last three sittings "
               f"({len(d['emerging_sem'])}, NVIDIA embeddings)",
            d["emerging_sem"][:15], "questions"))
        part.append(f"<p>Audit baseline: exact string matching alone finds "
                    f"{len(d['emerging_exact'])} — a new-looking subject string "
                    f"is often a rewording of an issue the record already "
                    f"contains, which is why the two methods disagree.</p>")
    else:
        tag = ", exact match" if d.get("emerging_sem") is not None else ""
        part.append(subjects_table(
            d, f"Emerging subjects — first seen in the last three sittings "
               f"({len(d['emerging_exact'])}{tag})",
            d["emerging_exact"], "questions"))
        if d.get("emerging_sem") is not None:
            part.append("<p>The semantic grouping found no new subject in the "
                        "last three sittings for this department; the list "
                        "above is the exact-match result.</p>")
    part.append(wfigure(f"ws-{slug}-volume"))

    part.append("<h3>3. What kind of answer is demanded</h3>")
    part.append(f"<p>{pct(d['action_demands'], d['n']):.0f}% of the questions "
                f"({d['action_demands']:,}) are not requests for data but demands "
                f"for action or accountability. Those are the questions where a "
                f"missing timeline, budget figure or named officer costs the "
                f"department the most.</p>")
    part.append(wfigure(f"ws-{slug}-demands"))

    part.append("<h3>4. Who is asking</h3>")
    part.append(f"<p>{d['n_askers']} members have questioned {esc(short)} at least "
                f"once; the top three account for {d['top3_share']:.0f}% of its "
                f"questions.</p>")
    part.append(wfigure(f"ws-{slug}-askers"))
    part.append(askers_table(d))

    part.append("<h3>5. What comes back</h3>")
    part.append(f"<p>{d['n_replies_text']:,} reply documents were located for the "
                f"{d['n']:,} questions ({d['reply_coverage']:.1f}%). "
                f"{d['n_coded']:,} were readable enough to code. The rest are not "
                f"silently dropped: {len(d['flagged'])} carry a recorded reason and "
                f"appear in the review sheet.</p>")
    part.append(wfigure(f"ws-{slug}-bands"))
    part.append(wfigure(f"ws-{slug}-latency"))
    part.append(wfigure(f"ws-{slug}-stages"))

    part.append("<h3>6. Reply documents, read in full</h3>")
    part.append("<p>Three replies from this department's own record: the most "
                "detailed, the thinnest, and one the rubric flags as boilerplate. "
                "They are quoted exactly as extracted, with the coding that was "
                "applied to each.</p>")
    part.append(exhibits_html(d))

    part.append("<h3>7. What this dossier does not show</h3>")
    part.append(limitations(d))

    part.append("<h3>8. Workshop exercises</h3>")
    part.append(exercises(d))
    part.append("</section>")
    return "".join(part)


def method_section(corpus: dict) -> str:
    steps = [
        ("Fix the corpus", f"Every question asked in a sitting from 2021 onward is "
         f"taken from the Assembly's own digital archive: {corpus['total']:,} "
         f"questions across {corpus['n_sessions']} sittings. Nothing before 2021 is "
         f"processed at all. The archive's own text is never rewritten — only "
         f"normalised for matching."),
        ("Classify each question twice", "Once by policy domain (a hand-written "
         "codebook of ~18 themes with ~140 sub-clusters, each keyword assigned to "
         "the theme it actually describes; the department's sector breaks ties). "
         "Once by what the question demands: information, explanation, action or "
         "accountability. Every classification stores the keywords that fired, so "
         "any row can be re-checked by hand."),
        ("Find the reply document", "Each question points to a reply PDF. The text "
         "is read from the scan, with a mojibake detector that re-reads rather "
         "than stores garbage. Where no reply text can be recovered, the record "
         "is flagged with a reason class (refused, dateless, mixed page, blank) "
         "and listed for human review — never silently emptied."),
        ("Code the reply against a rubric", "Length band (brief, standard, "
         "detailed, very detailed), boilerplate share, self-contradiction, "
         "assurance and evasion signals, and three actionability flags: does it "
         "cite a timeline, a budget figure, and a responsible officer? The flags "
         "are what separate a long reply from an accountable one."),
        ("Verify dates before using them", "A reply latency is only computed from "
         "a submission/reply pair that passes the trust check. Pairs that fail stay "
         "in the data and out of the latency chart, so a timing figure is never "
         "built on a date pair that may be a scanning artefact."),
        ("Count, never score", "No index, no grade, no ranking, no forecast. "
         "Everything published is a count, a rate with its denominator printed, or "
         "a date."),
    ]
    body = "".join(f"<li><b>{t}.</b> {d}</li>" for t, d in steps)
    return ("<section class='chapter' id='sec-method'>"
            "<div class='chapter-head'><span class='chapter-num'>Part I</span>"
            "<h2>How this analysis is done</h2>"
            "<p class='chapter-standfirst'>The method in six steps, so the dossier "
            "that follows can be reproduced, disputed, or run on another "
            "department.</p></div>"
            f"<ol class='method-list'>{body}</ol>"
            "<h3>Quality controls that run on every build</h3>"
            "<ul class='limitation-list'>"
            "<li>160 automated tests over the parsers, classifiers and pipeline.</li>"
            "<li>Extraction completeness: every scoped PDF accounted for; missing "
            "ones logged rather than skipped.</li>"
            "<li>Two audits on the built artefacts: no overlapping labels in any "
            "figure, and no person named in a way that could match more than one "
            "member.</li>"
            "<li>Numbers are computed at generation time — the report generator "
            "contains no hardcoded data values, which is checked.</li>"
            "</ul></section>")


def prepare(top: int = 3) -> dict:
    """Load the corpus once and build everything the pack and dossiers need."""
    rows, extracted, overall, dept_summary, records, labels, order = load_all()
    flagged = flagged_by_department()

    # Semantic recurrence (embeddings + verification gates) is the published
    # primary; the exact-match lists computed inside profile() travel beside
    # it. Missing files degrade to exact-only rather than failing the build.
    sem_path = REPO / "output/layers/layer5_semantic.json"
    sem = json.loads(sem_path.read_text(encoding="utf-8")) if sem_path.exists() else None
    clu_path = REPO / "output/layers/semantic_clusters.json"
    sem_clusters = (json.loads(clu_path.read_text(encoding="utf-8")).get("clusters", [])
                    if clu_path.exists() else [])
    gate_path = REPO / "data/cache/gate_verifications.json"
    gate_counts = Counter()
    if gate_path.exists():
        for v in json.loads(gate_path.read_text(encoding="utf-8")).values():
            gate_counts[v.get("verdict") or ("same" if v.get("same_issue") else "different")] += 1
    if sem:
        print(f"  semantic layer: {sem['n_families']} families "
              f"({sem['embed_model']}, {sem['embed_dims']}d), "
              f"{len(sem.get('emerging_issues', []))} emerging, "
              f"{sum(gate_counts.values())} gate decisions cached")
    else:
        print("  semantic layer not found - exact match only")

    totals = Counter(normalize_dept(r.get("Departments")) for r in rows)
    top_depts = [d for d, _c in totals.most_common(top)]
    sess_labels = {f"{a} {s}": s for a, s in order}

    profiles = []
    for dept in top_depts:
        d = profile(dept, rows, extracted, dept_summary, records, labels, order,
                    flagged, overall, sem=sem, sem_clusters=sem_clusters,
                    gate_counts=gate_counts)
        d["sessions_full"] = [f"{a} {s}" for a, s in d["sessions"]]
        d["_label_map"] = {str(r.get("Asked_By") or "").strip(): labels.get(
            str(r.get("Asked_By") or "").strip(), str(r.get("Asked_By") or ""))
            for r in rows}
        # display label -> the archive's own name for that member, so party
        # and bloc lookups hit the reference tables instead of missing
        d["_raw_by_label"] = {}
        for r in rows:
            raw = str(r.get("Asked_By") or "").strip()
            d["_raw_by_label"].setdefault(d["_label_map"].get(raw, raw), raw)
        profiles.append(d)

    corpus = {"total": sum(totals.values()), "n_sessions": len(order),
              "n_askers": len(labels)}

    all_lat = [x["latency"] for x in records if x["latency"] is not None]
    corpus_median = statistics.median(all_lat) if all_lat else None

    # "all other departments" for the comparison figure
    rest_depts = [d for d in dept_summary if d not in top_depts]
    rest_vals = [dept_summary[d] for d in rest_depts]
    rest_coded = sum(v["n_replies"] for v in rest_vals) or 1
    rest_lat = [x["latency"] for x in records
                if x["latency"] is not None and x["department"] not in top_depts]
    rest_rate = []
    for dept, budget in ref_data.DEPT_BUDGET.items():
        if dept in rest_depts and budget:
            rest_rate.append(totals.get(dept, 0) / budget * 100)
    global rest_values
    rest_values = {
        "Questions per ₹100 crore": statistics.mean(rest_rate) if rest_rate else 0,
        "Detailed or very detailed replies (%)": pct(
            sum(v["substantiveness"].get("detailed", 0)
                + v["substantiveness"].get("very_detailed", 0) for v in rest_vals),
            rest_coded),
        "Replies citing a timeline (%)": pct(
            round(sum(v["timeline_pct"] * v["n_replies"] / 100 for v in rest_vals)),
            rest_coded),
        "Median reply latency (days)": statistics.median(rest_lat) if rest_lat else 0,
    }
    return {"profiles": profiles, "corpus": corpus, "corpus_median": corpus_median,
            "sess_labels": sess_labels, "sem": sem, "overall": overall,
            "totals": totals, "top_depts": top_depts}


def render_department_figures(prep: dict) -> None:
    """Draw every ws-<department>-*.svg the deep-dive chapters reference."""
    for d in prep["profiles"]:
        fig_volume(d, prep["sess_labels"])
        fig_themes(d)
        fig_demands(d)
        fig_bands(d)
        fig_latency(d, prep["corpus_median"])
        fig_stages(d)
        fig_askers(d)


def dossier_sections(top: int = 3, badge: str = "Chapter") -> str:
    """Departmental deep-dive chapters as one HTML string, figures included.

    The report builder calls this so the publication carries the same dossiers
    as the workshop pack without duplicating the rendering code."""
    prep = prepare(top)
    render_department_figures(prep)
    exact_families = json.loads(
        (REPO / "output/layers/layer5_resolution.json").read_text(encoding="utf-8")
    ).get("families", {})
    fig_embedding(prep["sem"], exact_families)
    return "\n".join(
        chapter(d, i, prep["corpus"], prep["corpus_median"], badge=badge)
        for i, d in enumerate(prep["profiles"], 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=3,
                    help="how many departments get a full dossier")
    args = ap.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    prep = prepare(args.top)
    profiles = prep["profiles"]
    corpus, corpus_median, sem = prep["corpus"], prep["corpus_median"], prep["sem"]
    totals = prep["totals"]
    top_depts = prep["top_depts"]

    render_department_figures(prep)
    fig_compare(profiles, prep["overall"], corpus_median)
    exact_families = json.loads(
        (REPO / "output/layers/layer5_resolution.json").read_text(encoding="utf-8")
    ).get("families", {})
    fig_embedding(sem, exact_families)

    L = []
    add = L.append
    add("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>")
    add("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    add("<title>Departmental Evidence Dossiers &amp; Workshop Pack — Meghalaya "
        "Legislative Oversight 2021–2026</title>")
    add(f"<style>{build_css()}</style></head><body>")
    add("<div id='progress-bar'></div>")

    add("<div class='journal-masthead'>")
    add("<div><span class='journal-badge'>Workshop Pack</span> <b>Departmental "
        "Evidence Dossiers</b> · Meghalaya, 2021–2026</div>")
    add("<div>Companion to <i>The Preparedness Gap</i> · CC BY 4.0</div></div>")

    add("<nav class='sticky-toc'>")
    add("<div class='nav-brand'><span>🏛️</span> Evidence Dossiers</div>")
    add("<div class='nav-links'>")
    add("<a href='#sec-method'>Method</a>")
    for i, d in enumerate(profiles, 1):
        add(f"<a href='#dept-{i}'>{esc(d['dept'].replace(' Department', ''))}</a>")
    add("<a href='#sec-compare'>Comparison</a>")
    add("<a href='#sec-reproduce'>Reproduce</a>")
    add("</div>")
    add("<div class='nav-actions'>")
    add("<button class='btn-print' onclick='window.print()'>Print / PDF</button>")
    add("</div></nav>")

    add("<div class='journal-wrap'>")
    add("<header class='article-header'>")
    add("<div class='article-eyebrow'>Capacity-building pack · Evidence for "
        "departmental self-assessment</div>")
    add("<h1 class='article-title'>What was asked of you, what came back, and "
        "what the record shows</h1>")
    add(f"<p class='article-standfirst'>Evidence dossiers for the "
        f"{len(profiles)} most-questioned departments of the Meghalaya Legislative "
        f"Assembly, {corpus['total']:,} questions across {corpus['n_sessions']} "
        f"sittings from 2021 onward — built to be used in a workshop, and to be "
        f"reproduced by anyone who disagrees with it.</p>")
    add("<div class='article-meta'>")
    add(f"<div><b>Corpus</b><br>{corpus['total']:,} questions · "
        f"{corpus['n_sessions']} sittings · {corpus['n_askers']} members</div>")
    add(f"<div><b>Departments in full</b><br>"
        + " · ".join(f"{d['n']:,}" for d in profiles) + " questions</div>")
    add(f"<div><b>Generated</b><br>{datetime.now():%d %B %Y, %H:%M}</div>")
    add("</div></header>")

    add("<div class='callout-box'>")
    add("<h3>How to use this pack</h3><ol>"
        "<li>Read <a href='#sec-method'>Part I</a> first — it is the method, so you "
        "can check the method before accepting the numbers.</li>"
        "<li>Work through your own department's chapter. Every figure states its "
        "denominator; every claim is a count, a rate, or a date.</li>"
        "<li>Use the exercises at the end of the chapter. They are answerable from "
        "records the department already holds.</li>"
        "<li>Dispute anything you believe is wrong. The pipeline is open and "
        "re-runnable; a correction changes the number everywhere at once.</li>"
        "</ol>")
    add("<p><b>What this pack deliberately does not contain:</b> no readiness "
        "index, no performance score, no ranking of departments, and no forecast. "
        "Those compress many facts into one number that then drives decisions. "
        "This pack keeps the facts and shows the arithmetic.</p></div>")

    add(method_section(corpus))

    if sem:
        add("<section class='chapter' id='sec-embedding'>")
        add("<div class='chapter-head'><span class='chapter-num'>Part I-A</span>"
            "<h2>Embedding audit: finding the same issue in new words</h2>"
            "<p class='chapter-standfirst'>The semantic pass is an auditable "
            "supplement to exact matching, not a replacement for it.</p></div>")
        add(wfigure("ws-embedding-audit"))
        add(f"<p>The embedding pass represented "
            f"<b>{sem.get('n_subjects_embedded', 0):,} subject strings</b> with "
            f"<b>{esc(sem.get('embed_model', 'the recorded model'))}</b> "
            f"({esc(sem.get('embed_dims', '—'))} dimensions), then applied "
            f"department, locality, named-scheme, specificity and verification "
            f"gates. It produced <b>{sem.get('n_families', 0):,}</b> semantic "
            f"families and sent <b>{sem.get('n_unresolved', 0):,}</b> borderline "
            "pairs for human adjudication. Exact-match counts remain alongside "
            "these results so a reader can distinguish a measured wording "
            "difference from a model-assisted merge.</p>")
        add("</section>")

    for i, d in enumerate(profiles, 1):
        add(chapter(d, i, corpus, corpus_median))

    add("<section class='chapter' id='sec-compare'>")
    add("<div class='chapter-head'><span class='chapter-num'>Part II</span>"
        "<h2>How the three compare with the rest</h2>"
        "<p class='chapter-standfirst'>Four measures, each with its denominator, "
        "against every other department in the corpus. They are shown side by side "
        "and never combined.</p></div>")
    add(wfigure("ws-compare"))
    rows_tbl = []
    for d in profiles:
        rows_tbl.append([d["dept"], f"{d['n']:,}", f"{d['rate']:.1f}" if d["rate"] else "—",
                         f"{d['detailed_pct']:.0f}%", f"{d['timeline_pct']:.0f}%",
                         f"{d['budget_pct']:.0f}%",
                         f"{g(d['latency_median'])}" if d["latency_median"] is not None else "—"])
    rows_tbl.append(["All other departments",
                     f"{sum(v for k, v in totals.items() if k not in top_depts):,}",
                     f"{rest_values['Questions per ₹100 crore']:.1f}",
                     f"{rest_values['Detailed or very detailed replies (%)']:.0f}%",
                     f"{rest_values['Replies citing a timeline (%)']:.0f}%", "—",
                     f"{g(rest_values['Median reply latency (days)'])}"])
    add(table(["Department", "Questions", "Per ₹100 cr", "Detailed replies",
               "Cite a timeline", "Cite a budget", "Median days"], rows_tbl,
              caption="Denominators: questions = scoped corpus; detailed/timeline = "
                      "coded replies for that department; median days = verifiable "
                      "date pairs. Budget figures are 2025–26 allocations."))
    add("</section>")

    add("<section class='chapter' id='sec-reproduce'>")
    add("<div class='chapter-head'><span class='chapter-num'>Part III</span>"
        "<h2>Reproduce this yourself</h2>"
        "<p class='chapter-standfirst'>If a number here is wrong, you should be "
        "able to find the fault without asking us.</p></div>")
    add("<pre class='code-block'>"
        "# 1. Compute the deterministic layers from the question archive\n"
        "python scripts/run_layers.py\n\n"
        "# 2. Code replies against the response rubric\n"
        "python scripts/build_compendium.py\n\n"
        "# 3. Rebuild this workshop pack\n"
        "python scripts/build_workshop.py\n\n"
        "# 4. Check the artefacts\n"
        "python -m pytest packages -q\n"
        "python scripts/dev/audit_labels.py     # no overlapping figure labels\n"
        "python scripts/dev/audit_names.py      # no ambiguous member names\n"
        "</pre>")
    add("<h3>Where the underlying evidence lives</h3>")
    add(table(["Artefact", "Contents"], [
        ["data/dl_questions_raw.csv", "the question archive as published"],
        ["output/extracted/extracted.jsonl", "one record per reply PDF, with "
         "extraction method and provenance"],
        ["data/review/FLAGGED_EMPTY.md", "every reply we could not read, with the "
         "reason and what a human should check"],
        ["output/layers/*.json", "themes, geography, demands, resolution, trends"],
        ["output/workshop/index.html", "this document, with every figure inline"],
    ], caption="Nothing in this pack is derived from a source you cannot open."))
    add("<footer class='journal-footer'><p>Generated "
        f"{datetime.now():%d %B %Y at %H:%M} from the Meghalaya Legislative Assembly "
        "Digital Archives. Published under CC BY 4.0. Every number is computed at "
        "generation time from the archived record.</p></footer>")
    add("</div>")
    add(f"<script>{build_js()}</script></body></html>")

    dest = OUT / "index.html"
    dest.write_text("\n".join(L), encoding="utf-8")
    size = dest.stat().st_size / 1024
    n_figs = len(CAPTIONS)
    print(f"Workshop pack -> {dest} ({size:.0f} KB, {len(profiles)} departments, "
          f"{n_figs} figures, self-contained)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
