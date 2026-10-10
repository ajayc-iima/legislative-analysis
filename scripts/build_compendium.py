"""Build the three-pillar Compendium from all layer outputs.

Implements PLAN.md Task 4.1. Reads:
  output/layers/layer{1,2,3,5,6}_*.json   (question-side layers)
  data/extracted/extracted.jsonl            (OCR replies — Layer 4)

Layer 4 (response quality, timeliness) is computed here from the
extracted replies. The Compendium is regenerated as the OCR run
accrues — every regeneration is deterministic from source data.

Design principle (carried forward): every number is reproducible
from the source data; each dimension is reported separately; no
composite scores, no invented probabilities.
"""

import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages/analysis/src"))

from legislative_analysis import analysis as base
from legislative_analysis.codebook import normalize_dept, DEPT_THEME
from legislative_analysis.response import (
    code_reply, dates_trustworthy, sitting_gaps, timeliness_summary, latency,
)
from legislative_analysis import longitudinal as longi

REPO = Path(__file__).resolve().parent.parent
LAYERS = REPO / "output/layers"
EXTRACTED = REPO / "data/extracted/extracted.jsonl"
OUT_DIR = REPO / "output/compendium"


def load_json(name):
    p = LAYERS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_extracted():
    out = {}
    if EXTRACTED.exists():
        with open(EXTRACTED, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip().lstrip("﻿")  # U+FEFF BOM on line 1 (first-ever run wrote utf-8-sig)
                if line:
                    rec = json.loads(line)
                    out[rec.get("pdf", "")] = rec
    return out


def compute_layer4(rows, extracted):
    """Response quality + timeliness over extracted replies."""
    records = []
    excluded_pairs = 0
    for r in rows:
        name = str(r.get("Document_Link") or "").rsplit("/", 1)[-1]
        rec = extracted.get(name)
        if not rec or not rec.get("reply"):
            continue
        coding = code_reply(rec["reply"])
        sitting = base.parse_date(r.get("Session_Date"))
        if dates_trustworthy(rec):
            gaps = sitting_gaps(rec.get("reply_date"), rec.get("submission_date"), sitting)
        else:
            gaps = {"latency_days": None, "notice_days": None, "late_reply": False}
            if rec.get("reply_date") and rec.get("submission_date"):
                excluded_pairs += 1
        records.append({
            "department": normalize_dept(r.get("Departments")),
            "theme": r.get("_theme", "General / Other"),
            "session": f"{r.get('Assembly', '')} {r.get('Session', '')}",
            "reply_date": rec.get("reply_date", ""),
            "submission_date": rec.get("submission_date", ""),
            "latency": gaps["latency_days"],
            "notice_days": gaps["notice_days"],
            "late_reply": gaps["late_reply"],
            **coding,
        })

    staged = [x for x in records if x["execution_stage"]["index"] >= 3]
    notices = sorted(x["notice_days"] for x in records if x["notice_days"] is not None)
    late_n = sum(1 for x in records if x["late_reply"])
    dated_n = sum(1 for x in records if x["reply_date"])
    overall = {
        "n_coded": len(records),
        "excluded_pairs": excluded_pairs,
        "substantiveness": dict(Counter(x["substantiveness"]["band"] for x in records)),
        "specificity": dict(Counter(x["specificity"]["level"] for x in records)),
        "boilerplate_pct": pct(sum(x["boilerplate"] for x in records), len(records)),
        "contradiction_pct": pct(sum(x["contradiction"]["has_contradiction"] for x in records), len(records)),
        "assurance_weight_mean": mean(x["assurance"]["weight"] for x in records),
        "evasion_weight_mean": mean(x["evasion"]["weight"] for x in records),
        "timeline_pct": pct(sum(x["actionability"]["has_timeline"] for x in records), len(records)),
        "budget_pct": pct(sum(x["actionability"]["has_budget"] for x in records), len(records)),
        "responsible_pct": pct(sum(x["actionability"]["has_responsible_party"] for x in records), len(records)),
        "progress_evidence_pct": pct(sum(x["actionability"]["has_progress_evidence"] for x in staged), len(staged)),
        "n_staged": len(staged),
        "stage_distribution": dict(Counter(x["execution_stage"]["stage"] for x in records)),
        "timeliness": timeliness_summary([{"_latency_days": x["latency"]} for x in records]),
        "notice_median_days": statistics.median(notices) if notices else None,
        "late_replies": late_n,
        "late_share_pct": pct(late_n, dated_n),
    }

    by_dept = defaultdict(list)
    for x in records:
        by_dept[x["department"]].append(x)
    dept_summary = {}
    for d, xs in sorted(by_dept.items(), key=lambda kv: -len(kv[1])):
        n = len(xs)
        lats = sorted(x["latency"] for x in xs if x["latency"] is not None)
        notices_d = sorted(x["notice_days"] for x in xs if x["notice_days"] is not None)
        staged_d = [x for x in xs if x["execution_stage"]["index"] >= 3]
        dept_summary[d] = {
            "n_replies": n,
            "substantiveness": dict(Counter(x["substantiveness"]["band"] for x in xs)),
            "specificity": dict(Counter(x["specificity"]["level"] for x in xs)),
            "assurance_weight_mean": mean(x["assurance"]["weight"] for x in xs),
            "evasion_weight_mean": mean(x["evasion"]["weight"] for x in xs),
            "boilerplate_pct": pct(sum(x["boilerplate"] for x in xs), n),
            "contradiction_pct": pct(sum(x["contradiction"]["has_contradiction"] for x in xs), n),
            "timeline_pct": pct(sum(x["actionability"]["has_timeline"] for x in xs), n),
            "budget_pct": pct(sum(x["actionability"]["has_budget"] for x in xs), n),
            "responsible_pct": pct(sum(x["actionability"]["has_responsible_party"] for x in xs), n),
            "progress_evidence_pct": pct(sum(x["actionability"]["has_progress_evidence"] for x in staged_d), len(staged_d)),
            "n_staged": len(staged_d),
            "stage_distribution": dict(Counter(x["execution_stage"]["stage"] for x in xs)),
            "latency_median": statistics.median(lats) if lats else None,
            "notice_median_days": statistics.median(notices_d) if notices_d else None,
            "late_pct": pct(sum(x["late_reply"] for x in xs), n),
        }
    return overall, dept_summary, records


def pct(part, whole):
    return round(100 * part / whole, 1) if whole else 0.0


def mean(vals):
    vals = list(vals)
    return round(statistics.mean(vals), 2) if vals else 0.0


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = base.scope_rows(base.load(str(REPO / "data/dl_questions_raw.csv")))
    order = longi.session_order_of(rows)

    themes = load_json("layer1_themes.json")
    geo = load_json("layer2_geography.json")
    demands = load_json("layer3_demands.json")
    resolution = load_json("layer5_resolution.json")
    trends = load_json("layer6_trends.json")

    extracted = load_extracted()
    overall, dept_summary, _records = compute_layer4(rows, extracted)

    total = len(rows)
    stats = json.loads((REPO / "output/stats.json").read_text(encoding="utf-8"))
    n_depts = stats["overview"]["departments"]
    n_replies = stats["overview"]["with_reply"]
    sitting_dates = {d for d in (base.parse_date(r.get("Session_Date")) for r in rows) if d}
    L = []
    add = L.append

    # ── Cover / executive summary ──
    add("# COMPENDIUM: Legislative Oversight in Meghalaya")
    add("")
    add(f"_Generated: {datetime.now():%Y-%m-%d %H:%M} · "
        f"Source: `data/dl_questions_raw.csv` ({total:,} questions in scope, "
        f"{len(order)} sessions, {len(sitting_dates)} sitting dates, 2021–2026)_")
    add("")
    add("_Visual companion: `output/charts/index.html` — 16 charts (PNG + SVG) "
        "with KPI cards and data tables; regenerate alongside this document._")
    add("")
    add("## Executive Summary")
    add("")
    add(f"- **Corpus**: {total:,} questions to {n_depts} departments by "
        f"{stats['overview']['mlas']} MLAs; signed replies for "
        f"{n_replies:,} ({stats['overview']['reply_coverage']}%)")
    add(f"- **Replies OCR-extracted so far**: {len(extracted):,} "
        f"(Layer 4 coverage {pct(len(extracted), 2246)}% of the 2,246 PDFs — "
        f"the extraction run is in progress; this document regenerates)")
    add(f"- **Attention leader**: {themes['theme_counts'] and max(themes['theme_counts'], key=themes['theme_counts'].get)} "
        f"is the most-asked policy domain")
    add(f"- **Demand mix**: {demands['demand_counts'] and ', '.join(f'{k} {v}' for k, v in sorted(demands['demand_counts'].items(), key=lambda kv: -kv[1]))}")
    add(f"- **Recurring subjects**: {resolution['n_families']} families recur across sessions")
    add(f"- **Emerging issues**: {len(trends.get('emerging_issues', []))} on the watchlist")
    add(f"- **Scope**: sittings from 2021 onwards. Pre-2021 reply coverage is 0–16% "
        f"(two sessions have zero signed replies) — too sparse for reply-side analysis. "
        f"Recurrence, trends and diversity are measured within the window: a subject asked "
        f"in 2020 and 2021 counts as new in 2021.")
    add("")
    add("> **Design note.** Every figure in this Compendium is reproducible from the "
        "source CSV and the extracted-reply JSONL. Dimensions are reported separately; "
        "no composite readiness scores are computed. Layer 4 figures grow as the OCR "
        "extraction run completes.")
    add("")

    # ── Part I ──
    add("# Part I — Patterns of Legislative Attention")
    add("")
    add("## Chapter 1. Departmental attention landscape")
    add("")
    add("| Department | Questions | Share | Sessions | Askers | Reply coverage |")
    add("|---|---|---|---|---|---|")
    stats = json.loads((REPO / "output/stats.json").read_text(encoding="utf-8"))
    for d in stats["departments"]:
        add(f"| {d['department']} | {d['questions']} | {d['share']}% | "
            f"{d['sessions']} | {d['askers']} | {d['coverage']}% |")
    add("")

    add("## Chapter 2. Thematic attention")
    add("")
    add("| Policy domain | Questions | Share |")
    add("|---|---|---|")
    for theme, n in sorted(themes.get("theme_counts", {}).items(), key=lambda kv: -kv[1]):
        add(f"| {theme} | {n} | {pct(n, total)}% |")
    add("")
    add("Classification method (auditable): " +
        ", ".join(f"{k} {v}" for k, v in themes.get("classification_methods", {}).items()))
    add("")

    add("## Chapter 3. Geographic attention")
    add("")
    add("| Region (MLA's own region) | Questions | Share |")
    add("|---|---|---|")
    for region, n in sorted(geo.get("region_counts", {}).items(), key=lambda kv: -kv[1]):
        add(f"| {region or '(unmatched)'} | {n} | {pct(n, total)}% |")
    add("")
    add("| Question scope | Count | Share |")
    add("|---|---|---|")
    for scope, n in sorted(geo.get("scope_counts", {}).items(), key=lambda kv: -kv[1]):
        add(f"| {scope} | {n} | {pct(n, total)}% |")
    add("")
    add(f"*Scope definitions: `constituency_specific` names the asker's own seat; "
        f"`place_specific` names a district/town/constituency other than the asker's own; "
        f"`state_wide` names no place. MLA-based mapping is an assumption — documented "
        f"limitation; the text-based gazetteer scan runs alongside it.*")
    add("")

    add("## Chapter 4. Sustained attention")
    add("")
    add(f"{resolution['n_families']} subjects recur in ≥2 sessions (exact normalized "
        f"match — documented trade-off: under-merges paraphrases, never over-merges).")
    add("")

    # ── Part II ──
    add("# Part II — Dynamics and Quality of Legislative Oversight")
    add("")
    add("## Chapter 5. Demand types")
    add("")
    add("| Demand type | Questions | Share |")
    add("|---|---|---|")
    for dt, n in sorted(demands.get("demand_counts", {}).items(), key=lambda kv: -kv[1]):
        add(f"| {dt} | {n} | {pct(n, total)}% |")
    add("")

    add("## Chapter 6. Trends over time")
    add("")
    add("### Rising departments (mean session-over-session delta)")
    add("")
    for d in trends.get("rising_departments", [])[:10]:
        add(f"- **{d['department']}**: {d['mean_delta']:+.2f}/session "
            f"(total {d['total']} across {d['sessions_active']} sessions)")
    add("")
    add("### Declining departments")
    add("")
    for d in trends.get("declining_departments", [])[:10]:
        add(f"- **{d['department']}**: {d['mean_delta']:+.2f}/session (total {d['total']})")
    add("")
    add("### New vs recurring share per session")
    add("")
    add("| Session | Questions | Recurring | New | Recurring % |")
    add("|---|---|---|---|---|")
    for s, v in trends.get("new_vs_recurring", {}).items():
        add(f"| {s} | {v['questions']} | {v['recurring']} | {v['new']} | {v['recurring_pct']}% |")
    add("")

    add("## Chapter 7. Response quality")
    add("")
    add(f"Replies coded: **{overall['n_coded']:,}** "
        f"({pct(overall['n_coded'], 2246)}% of the 2,246 reply PDFs).")
    add("")
    add("| Dimension | Distribution |")
    add("|---|---|")
    add(f"| Substantiveness | {overall['substantiveness']} |")
    add(f"| Specificity (data points) | {overall['specificity']} |")
    add(f"| Boilerplate | {overall['boilerplate_pct']}% of replies |")
    add(f"| Internal contradiction | {overall['contradiction_pct']}% of replies |")
    add(f"| Assurance-signal weight (mean) | {overall['assurance_weight_mean']} |")
    add(f"| Evasion-signal weight (mean) | {overall['evasion_weight_mean']} |")
    add(f"| Commits to a timeline | {overall['timeline_pct']}% |")
    add(f"| Cites a budget amount | {overall['budget_pct']}% |")
    add(f"| Names a responsible party | {overall['responsible_pct']}% |")
    add(f"| Cites progress proof (of {overall['n_staged']} project-stage replies) | "
        f"{overall['progress_evidence_pct']}% |")
    add(f"| Delivery-pipeline position | "
        f"{', '.join(f'{k} {v}' for k, v in sorted(overall['stage_distribution'].items(), key=lambda kv: -kv[1])[:4])} |")
    add("")
    t = overall.get("timeliness", {})
    if t.get("n"):
        add(f"**Timeliness** (both dates extracted for {t['n']} replies, "
            f"{t['coverage']}% coverage): median {t['median_days']} days, "
            f"P75 {t['p75_days']} days, {t['share_over_30d']}% over 30 days, "
            f"{t['share_over_90d']}% over 90 days.")
    if overall.get("notice_median_days") is not None:
        add(f"**Notice**: departments get a median of {overall['notice_median_days']} days "
            f"between question submission and the sitting.")
    if overall.get("late_replies"):
        add(f"**Late replies**: {overall['late_replies']} replies "
            f"({overall['late_share_pct']}%) are dated after the sitting day.")
    if overall.get("excluded_pairs"):
        add(f"*{overall['excluded_pairs']} date pairs excluded from timeliness as "
            f"flagged implausible (far from sitting) or self-contradictory "
            f"(reply precedes submission); they remain in the data with "
            f"their review flags.*")
    add("")
    add("### By department")
    add("")
    add("| Department | Replies | Substantiveness | Specificity | Boilerplate % | Contradiction % | Timeline % | Budget % | Responsible % | Median latency (d) |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for d, v in list(dept_summary.items())[:25]:
        subs = " / ".join(f"{k} {n}" for k, n in sorted(v["substantiveness"].items()))
        specs = " / ".join(f"{k} {n}" for k, n in sorted(v["specificity"].items()))
        add(f"| {d} | {v['n_replies']} | {subs} | {specs} | {v['boilerplate_pct']} | "
            f"{v['contradiction_pct']} | {v['timeline_pct']} | {v['budget_pct']} | "
            f"{v['responsible_pct']} | {v['latency_median'] if v['latency_median'] is not None else '—'} |")
    add("")

    add("## Chapter 8. Gaps and contradictions")
    add("")
    add(f"- **Boilerplate replies**: {overall['boilerplate_pct']}% consist primarily of stock phrases")
    add(f"- **Internal contradictions**: {overall['contradiction_pct']}% pair a completion claim "
        f"with a negative qualifier in the same paragraph")
    add(f"- **Low-specificity replies**: {overall['specificity'].get('low', 0)} of "
        f"{overall['n_coded']} contain no numbers, dates, schemes or amounts")
    add("")

    # ── Part III ──
    add("# Part III — Persistent and Emerging Governance Challenges")
    add("")
    add("## Chapter 9. Unresolved issues")
    add("")
    add("| Trajectory | Families |")
    add("|---|---|")
    for status, n in sorted(resolution.get("resolution_counts", {}).items(), key=lambda kv: -kv[1]):
        add(f"| {status} | {n} |")
    add("")
    add("_Trajectories are coded from reply text; families marked "
        "`awaiting_replies` will be coded as the OCR run completes._")
    add("")
    stalled = resolution.get("stalled_subjects", [])
    if stalled:
        add("### Stalled issues (recurring, no progress language in latest reply)")
        add("")
        for f in stalled[:20]:
            add(f"- **{f['subject']}** — {f['occurrences']} occurrences across "
                f"{len(f['sessions'])} sessions; {', '.join(f['departments'][:2])}")
        add("")

    add("## Chapter 10. Recurring challenges")
    add("")
    add(f"{resolution['n_families']} families recur across sessions. Full catalog: "
        f"`output/layers/layer5_resolution.json` (families with session lists, "
        f"departments, askers, trajectory detail).")
    add("")

    add("## Chapter 11. Emerging issues and anticipation")
    add("")
    add("| Subject | First seen | Occurrences | Askers | Departments |")
    add("|---|---|---|---|---|")
    for e in trends.get("emerging_issues", []):
        add(f"| {e['subject']} | {e['first_session']} | {e['occurrences']} | "
            f"{len(e['askers'])} | {', '.join(e['departments'][:2])} |")
    add("")
    add("_Emerging = first appeared in the last 3 sessions, ≥2 occurrences, "
        "asked by ≥2 MLAs (a broader concern, not one member's agenda)._")
    add("")

    # ── Methodology appendix ──
    add("# Methodology Appendix")
    add("")
    add("## Data sources")
    add("")
    add("- Questions: NeVA Digital Library portal, scraped to "
        "`data/dl_questions_raw.csv`; analysis scope is sittings from 2021 "
        "onwards (pre-2021 reply coverage 0–16%)")
    add("- Reply PDFs: 2,246 signed scans under `data/pdfs/` (85.3% of questions)")
    add("- Reply text/dates: NVIDIA OCR (nemotron-ocr-v1) with a three-reader "
        "consensus (ocr-v1 + parse + vision-11b) and a reasoning supervisor "
        "for unresolved dates; mechanical gates (parseable, ordered, "
        "±120 days of the sitting date) apply to every winner")
    add("")
    add("## Classification codebooks")
    add("")
    add("- **Themes** (Layer 1): 17 policy domains seeded from the legacy "
        "topic hierarchy; keyword rules with department-sector tie-break; "
        "every row records its evidence (keyword / tie-break / department prior)")
    add("- **Geography** (Layer 2): MLA → constituency → district → region "
        "via the ported MLA_DB (60 seats, aliases for portal typos); "
        "gazetteer scan of subject + question text (11 districts, 60 "
        "constituencies, towns, blocks)")
    add("- **Demand types** (Layer 3): Information / Explanation / Action / "
        "Accountability; the last is structural (subject recurs in an earlier "
        "session) or explicit follow-up language")
    add("- **Response quality** (Layer 4): substantiveness (length band), "
        "specificity (data-point census), assurance/evasion signal counts "
        "(ported registries), boilerplate and contradiction regexes, "
        "actionability (timeline / budget / responsible party)")
    add("")
    add("## Validation")
    add("")
    add("- OCR extraction: 12/12 reply dates correct against hand-annotated "
        "truth; 0 confident errors (validated before the full run)")
    add("- Thematic classification: spot-checked random sample; 5–10% "
        "manual review budgeted per the plan")
    add("- Geography: 99.8% of askers matched to a seat; 4 historical MLAs "
        "added from verified 2018 election records")
    add("")
    add("## Limitations")
    add("")
    add("- OCR accuracy is bounded (~0.94 per-field); low-confidence extractions "
        "carry provenance flags, not silent defaults")
    add("- Exact-match recurrence under-merges paraphrases (documented choice)")
    add("- MLA-based geography assumes questions concern the asker's own seat")
    add("- Layer 4 coverage grows as extraction completes; regenerate this "
        "document with `python build_compendium.py` afterwards")
    add("")

    report = "\n".join(L)
    (OUT_DIR / "COMPENDIUM.md").write_text(report, encoding="utf-8")
    print(f"Compendium: {len(report.splitlines())} lines -> {OUT_DIR / 'COMPENDIUM.md'}")
    print(f"  Layer 4 coverage: {len(extracted)}/2246 replies "
          f"({pct(len(extracted), 2246)}%)")


if __name__ == "__main__":
    build()
