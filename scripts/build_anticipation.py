"""Departmental anticipation briefs (Pillar 3, questions 5-6).

For each department: what questions to anticipate next session
(stalled recurring subjects first, then progressing ones, emerging
issues, and rising themes) and what to do in advance — where every
recommendation carries its measured evidence value (no composite
scores, no LLM-generated action plans).

Inputs: output/layers/*.json, output/stats.json, extracted replies.
Outputs: output/anticipation/dept_briefs.json + ANTICIPATION.md.

Regenerate any time: python scripts/build_anticipation.py
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))
sys.path.insert(0, str(REPO))

from legislative_analysis import analysis as base  # noqa: E402
from legislative_analysis.analysis import load as load_rows  # noqa: E402
from legislative_analysis.codebook import normalize_dept  # noqa: E402
from legislative_analysis.geography import tag_all  # noqa: E402
from build_compendium import compute_layer4, load_extracted  # noqa: E402

OUT = REPO / "output/anticipation"

# Presentation cut-points for recommendations. They are not weights:
# each recommendation reports the measured value beside it.
BOILERPLATE_HIGH = 20.0   # % boilerplate replies
CONTRADICTION_HIGH = 10.0  # % contradictory replies
TIMELINE_LOW = 30.0       # % replies committing to a timeline
BUDGET_LOW = 30.0         # % replies citing a budget amount
PROGRESS_LOW = 50.0       # % staged replies citing progress proof
SPECIFICITY_LOW_HIGH = 40.0  # % low-specificity replies
LATENCY_HIGH = 30         # median days submission -> reply
COVERAGE_LOW = 80.0       # % questions with a signed reply


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    get = lambda n: json.loads((REPO / "output/layers" / f"{n}.json").read_text(encoding="utf-8"))
    themes = get("layer1_themes")
    demands = get("layer3_demands")
    resolution = get("layer5_resolution")
    trends = get("layer6_trends")

    rows = base.scope_rows(load_rows(str(REPO / "data/dl_questions_raw.csv")))
    tag_all(rows, base.subject_of)
    extracted = load_extracted()
    _overall, dept_quality, _records = compute_layer4(rows, extracted)

    # demand mix by canonical department
    demand_mix = defaultdict(Counter)
    for raw, counts in demands["demand_by_department"].items():
        demand_mix[normalize_dept(raw)].update(counts)

    # volume, sessions, reply coverage by canonical department (all depts)
    full_volume = Counter(normalize_dept(r.get("Departments")) for r in rows)
    full_sessions = defaultdict(set)
    for r in rows:
        full_sessions[normalize_dept(r.get("Departments"))].add(
            (r.get("Assembly") or "", r.get("Session") or ""))
    with_reply = Counter()
    for r in rows:
        if str(r.get("Document_Link") or "").lower().startswith("http"):
            with_reply[normalize_dept(r.get("Departments"))] += 1

    dept_themes = themes["department_by_theme"]
    slope = {d["department"]: d["mean_delta"]
             for d in trends["rising_departments"] + trends["declining_departments"]}
    full_trends = trends["department_trends"]

    briefs = {}
    for dept in sorted(full_volume, key=lambda d: -full_volume[d]):
        n = full_volume[dept]
        cov = round(100 * with_reply[dept] / n, 1) if n else 0.0
        theme_top = list((dept_themes.get(dept) or {}).items())[:5]
        dmix = dict(demand_mix.get(dept, {}))
        sl = full_trends.get(dept, {}).get("mean_delta", 0.0)

        # recurring subjects touching this department
        touching = [f for f in resolution["families"].values()
                    if dept in {normalize_dept(d) for d in f["departments"]}]
        by_traj = defaultdict(list)
        for f in touching:
            by_traj[f["trajectory"]].append(f["subject"])
        emerging_here = [e for e in trends["emerging_issues"]
                         if dept in {normalize_dept(d) for d in e["departments"]}]

        anticipate = []
        for s in by_traj.get("stalled", [])[:5]:
            anticipate.append({"subject": s, "why": "recurring, no progress language"})
        for s in by_traj.get("progressing", [])[:5]:
            anticipate.append({"subject": s, "why": "recurring, progress under way — expect follow-up"})
        for s in by_traj.get("awaiting_replies", [])[:5]:
            anticipate.append({"subject": s, "why": "recurring, replies not yet coded"})
        for e in emerging_here[:5]:
            anticipate.append({"subject": e["subject"], "why": f"emerging (first {e['first_session']})"})

        prepare = []
        q = dept_quality.get(dept)
        if q:
            if q["boilerplate_pct"] >= BOILERPLATE_HIGH:
                prepare.append(f"Replace stock phrases with specific data "
                               f"({q['boilerplate_pct']}% of {q['n_replies']} coded replies are boilerplate).")
            if q["contradiction_pct"] >= CONTRADICTION_HIGH:
                prepare.append(f"Reconcile completion claims with pending items "
                               f"({q['contradiction_pct']}% of replies contradict themselves in one paragraph).")
            if q["timeline_pct"] < TIMELINE_LOW:
                prepare.append(f"Commit to dated timelines "
                               f"(only {q['timeline_pct']}% of replies name one).")
            if q["budget_pct"] < BUDGET_LOW:
                prepare.append(f"Cite sanctioned/released amounts "
                               f"(only {q['budget_pct']}% of replies name one).")
            if q.get("n_staged", 0) >= 5 and q.get("progress_evidence_pct", 100) < PROGRESS_LOW:
                prepare.append(f"Cite physical progress proof (percentages, measurement "
                               f"records, inspections) on project replies "
                               f"(only {q['progress_evidence_pct']}% of {q['n_staged']} staged replies do).")
            low_spec = q["specificity"].get("low", 0)
            if q["n_replies"] and 100 * low_spec / q["n_replies"] >= SPECIFICITY_LOW_HIGH:
                prepare.append(f"Back claims with numbers, dates or scheme names "
                               f"({low_spec} of {q['n_replies']} replies contain none).")
            if q["latency_median"] is not None and q["latency_median"] > LATENCY_HIGH:
                prepare.append(f"Shorten reply turnaround "
                               f"(median {q['latency_median']} days submission to reply).")
        if cov < COVERAGE_LOW and n >= 10:
            prepare.append(f"Clear the reply backlog ({cov}% of {n} questions have a signed reply).")
        if by_traj.get("stalled"):
            prepare.append(f"Report measurable progress on {len(by_traj['stalled'])} stalled "
                           f"recurring subject(s) — repeated boilerplate invites follow-ups.")

        briefs[dept] = {
            "questions": n,
            "share_pct": round(100 * n / len(rows), 1),
            "sessions_active": len(full_sessions[dept]),
            "reply_coverage_pct": cov,
            "trend_delta_per_session": sl,
            "top_themes": [{"theme": t, "questions": c} for t, c in theme_top],
            "demand_mix": dmix,
            "top_districts": [{"district": d, "questions": c} for d, c in
                              Counter(m for r in rows
                                      if normalize_dept(r.get("Departments")) == dept
                                      for m in [r.get("_mla_district") or ""]
                                      if m).most_common(5)],
            "recurring_subjects": len(touching),
            "trajectories": {k: len(v) for k, v in by_traj.items()},
            "anticipate": anticipate,
            "prepare": prepare,
            "replies_coded": (dept_quality.get(dept) or {}).get("n_replies", 0),
        }

    (OUT / "dept_briefs.json").write_text(json.dumps(briefs, indent=2, ensure_ascii=False),
                                          encoding="utf-8")

    # Markdown: top 20 departments by volume
    L = ["# Departmental Anticipation Briefs",
         f"_Generated {datetime.now():%Y-%m-%d %H:%M} from {len(rows)} questions; "
         f"reply-text evidence covers {len(extracted)} extracted PDFs (regenerates as OCR accrues)._",
         "",
         "> **How to read a brief.** *Anticipate* lists where the next questions will "
         "come from: stalled recurring subjects first (boilerplate invites follow-ups), "
         "then subjects with progress under way, then emerging issues. *Prepare* lists "
         "what to fix before they arrive — each item cites the measured value behind it. "
         "Thresholds are presentation cut-points documented in "
         "`scripts/build_anticipation.py`, not weights.",
         ""]
    for dept in sorted(briefs, key=lambda d: -briefs[d]["questions"])[:20]:
        b = briefs[dept]
        L += [f"## {dept}",
              f"{b['questions']} questions ({b['share_pct']}%) · {b['sessions_active']} sessions · "
              f"reply coverage {b['reply_coverage_pct']}% · trend {b['trend_delta_per_session']:+.2f}/session · "
              f"{b['recurring_subjects']} recurring subjects · {b['replies_coded']} replies coded",
              ""]
        if b["top_themes"]:
            L.append("**Top themes:** " + "; ".join(
                f"{t['theme']} ({t['questions']})" for t in b["top_themes"][:4]))
        if b["demand_mix"]:
            L.append("**Demand mix:** " + ", ".join(
                f"{k} {v}" for k, v in sorted(b["demand_mix"].items(), key=lambda kv: -kv[1])))
        L.append("")
        if b["anticipate"]:
            L.append("**Anticipate:**")
            L += [f"- {a['subject']} — *{a['why']}*" for a in b["anticipate"][:8]]
            L.append("")
        if b["prepare"]:
            L.append("**Prepare:**")
            L += [f"- {p}" for p in b["prepare"]]
            L.append("")
        else:
            L.append("_No measured gaps — replies are specific, timely and committed._")
            L.append("")
    (OUT / "ANTICIPATION.md").write_text("\n".join(L), encoding="utf-8")
    n_rec = sum(len(b["prepare"]) for b in briefs.values())
    n_ant = sum(len(b["anticipate"]) for b in briefs.values())
    print(f"{len(briefs)} briefs -> {OUT} ({n_ant} anticipated subjects, {n_rec} recommendations)")


if __name__ == "__main__":
    main()
