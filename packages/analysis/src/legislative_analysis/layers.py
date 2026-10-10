"""Full analytical pipeline: the six layers of PLAN.md Tasks 1-3.

DEPRECATED: use scripts/run_layers.py (question-side layers) and
scripts/build_compendium.py (Layer 4 + synthesis) instead. This module
is retained so `python -m legislative_analysis --layers` keeps working,
but it no longer receives new dimensions (progress evidence, execution
stages, trustworthiness filtering live in scripts/).
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from . import analysis as base
from .codebook import classify_all, normalize_dept, DEPT_THEME
from .geography import tag_all, lookup_mla
from .demand import classify_all as classify_demand_all
from .response import code_reply, timeliness_summary, latency
from . import longitudinal as longi

DEFAULT_CSV = "data/dl_questions_raw.csv"
DEFAULT_OUT = "output/layers"
EXTRACTED_DEFAULT = "data/extracted/extracted.jsonl"


def load_extracted(path):
    """pdf basename -> extracted record."""
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    with open(p, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out[rec.get("pdf", "")] = rec
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Six-layer legislative analysis")
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--out-dir", default=DEFAULT_OUT)
    parser.add_argument("--extracted", default=EXTRACTED_DEFAULT,
                        help="extracted.jsonl from the OCR pipeline")
    args = parser.parse_args(argv)

    rows = base.load(args.csv)
    rows = base.scope_rows(rows)
    subject_of = base.subject_of
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Session ordering (used across layers)
    order = longi.session_order_of(rows)

    # Recurring subjects (exact-match, same as base analysis)
    recurring_keys = set()
    seen = defaultdict(set)
    for r in rows:
        key = base.normalize_subject(subject_of(r))
        if len(key) >= base.MIN_SUBJECT_CHARS:
            seen[key].add((r.get("Assembly") or "", r.get("Session") or ""))
    recurring_keys = {k for k, s in seen.items() if len(s) >= 2}    # ── Layer 1: thematic classification ──
    classify_all(rows, subject_of)
    theme_counts = Counter(r["_theme"] for r in rows)
    subtheme_counts = Counter((r["_theme"], r["_sub_theme"]) for r in rows)
    method_counts = Counter(r["_theme_evidence"]["method"] for r in rows)

    # ── Layer 2: geographic tagging ──
    tag_all(rows, subject_of)
    region_counts = Counter(r["_mla_region"] for r in rows)
    district_counts = Counter(r["_mla_district"] for r in rows)
    scope_counts = Counter(r["_scope"] for r in rows)
    mla_unmatched = sorted({r.get("Asked_By") or "" for r in rows
                            if not r.get("_mla_constituency")})

    # ── Layer 3: demand-type taxonomy ──
    classify_demand_all(rows, subject_of, recurring_keys)
    demand_counts = Counter(r["_demand_type"] for r in rows)

    # ── Layer 4: response quality (join on extracted replies) ──
    extracted = load_extracted(args.extracted)
    reply_records = []
    for r in rows:
        name = str(r.get("Document_Link") or "").rsplit("/", 1)[-1]
        rec = extracted.get(name)
        if not rec or not rec.get("reply"):
            continue
        coding = code_reply(rec["reply"])
        lat = latency(rec.get("reply_date"), rec.get("submission_date"))
        reply_records.append({
            "pdf": name,
            "session": f"{r.get('Assembly', '')} {r.get('Session', '')}",
            "department": str(r.get("Departments") or ""),
            "theme": r["_theme"],
            "demand_type": r["_demand_type"],
            "reply_date": rec.get("reply_date", ""),
            "submission_date": rec.get("submission_date", ""),
            "latency_days": lat,
            **coding,
        })
    dept_quality = defaultdict(lambda: defaultdict(list))
    for rec in reply_records:
        d = normalize_dept(rec["department"])
        theme = DEPT_THEME.get(d, "General / Other")
        for dim in ("substantiveness", "specificity"):
            dept_quality[d][dim].append(rec[dim]["band"] if dim == "substantiveness" else rec[dim]["level"])
        dept_quality[d]["assurance_weight"].append(rec["assurance"]["weight"])
        dept_quality[d]["evasion_weight"].append(rec["evasion"]["weight"])
        dept_quality[d]["boilerplate"].append(rec["boilerplate"])
        dept_quality[d]["contradiction"].append(rec["contradiction"]["has_contradiction"])
        dept_quality[d]["actionability_timeline"].append(rec["actionability"]["has_timeline"])
        dept_quality[d]["actionability_budget"].append(rec["actionability"]["has_budget"])
        dept_quality[d]["actionability_responsible"].append(rec["actionability"]["has_responsible_party"])
        dept_quality[d]["latency"].append(rec["latency_days"])

    dept_quality_summary = {}
    for d, dims in sorted(dept_quality.items(), key=lambda kv: -len(kv[1]["substantiveness"])):
        n = len(dims["substantiveness"])
        dept_quality_summary[d] = {
            "n_replies": n,
            "substantiveness": dict(Counter(dims["substantiveness"])),
            "specificity": dict(Counter(dims["specificity"])),
            "assurance_weight_mean": round(sum(dims["assurance_weight"]) / n, 2),
            "evasion_weight_mean": round(sum(dims["evasion_weight"]) / n, 2),
            "boilerplate_pct": round(100 * sum(dims["boilerplate"]) / n, 1),
            "contradiction_pct": round(100 * sum(dims["contradiction"]) / n, 1),
            "timeline_pct": round(100 * sum(dims["actionability_timeline"]) / n, 1),
            "budget_pct": round(100 * sum(dims["actionability_budget"]) / n, 1),
            "responsible_pct": round(100 * sum(dims["actionability_responsible"]) / n, 1),
            "latency_median": sorted(x for x in dims["latency"] if x is not None)[len([x for x in dims["latency"] if x is not None]) // 2] if any(x is not None for x in dims["latency"]) else None,
        }

    timeliness = timeliness_summary(reply_records)

    # ── Layer 5: longitudinal resolution tracking ──
    families = longi.build_families(rows, subject_of, extracted, order)
    resolution = longi.resolution_summary(families)
    stalled = sorted((f for f in families.values() if f["trajectory"] == "stalled"),
                     key=lambda f: (-f["occurrences"], f["subject"]))

    # ── Layer 6: trends + emerging issues ──
    dept_trends = longi.department_trends(rows, order)
    theme_trends = longi.theme_trends(rows, order)
    nvr = longi.new_vs_recurring(rows, subject_of, order)
    diversity = longi.diversity_index(rows, order)
    emerging = longi.emerging_issues(rows, subject_of, order)

    rising = sorted(dept_trends.items(), key=lambda kv: -kv[1]["mean_delta"])[:10]
    declining = sorted(dept_trends.items(), key=lambda kv: kv[1]["mean_delta"])[:10]

    # ── Write outputs ──
    def dump(name, data):
        (out / name).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                encoding="utf-8")

    dump("layer1_themes.json", {
        "theme_counts": dict(theme_counts.most_common()),
        "subtheme_counts": {f"{t} / {s}": c for (t, s), c in subtheme_counts.most_common()},
        "classification_methods": dict(method_counts),
        "department_theme_map": {d: DEPT_THEME.get(d, "") for d in sorted(set(normalize_dept(r.get("Departments")) for r in rows))},
    })
    dump("layer2_geography.json", {
        "region_counts": dict(region_counts.most_common()),
        "district_counts": dict(district_counts.most_common()),
        "scope_counts": dict(scope_counts.most_common()),
        "mla_unmatched": mla_unmatched,
    })
    dump("layer3_demands.json", {
        "demand_counts": dict(demand_counts.most_common()),
        "demand_by_theme": _crosstab(rows, "_theme", "_demand_type"),
        "demand_by_department": _crosstab(rows, "Departments", "_demand_type"),
    })
    dump("layer4_response.json", {
        "n_replies_coded": len(reply_records),
        "coverage_pct": round(100 * len(reply_records) / len(rows), 1),
        "overall": {
            "substantiveness": dict(Counter(r["substantiveness"]["band"] for r in reply_records)),
            "specificity": dict(Counter(r["specificity"]["level"] for r in reply_records)),
            "boilerplate_pct": round(100 * sum(r["boilerplate"] for r in reply_records) / len(reply_records), 1) if reply_records else 0,
            "contradiction_pct": round(100 * sum(r["contradiction"]["has_contradiction"] for r in reply_records) / len(reply_records), 1) if reply_records else 0,
            "assurance_weight_mean": round(sum(r["assurance"]["weight"] for r in reply_records) / len(reply_records), 2) if reply_records else 0,
            "evasion_weight_mean": round(sum(r["evasion"]["weight"] for r in reply_records) / len(reply_records), 2) if reply_records else 0,
            "timeline_pct": round(100 * sum(r["actionability"]["has_timeline"] for r in reply_records) / len(reply_records), 1) if reply_records else 0,
            "budget_pct": round(100 * sum(r["actionability"]["has_budget"] for r in reply_records) / len(reply_records), 1) if reply_records else 0,
            "responsible_pct": round(100 * sum(r["actionability"]["has_responsible_party"] for r in reply_records) / len(reply_records), 1) if reply_records else 0,
        },
        "by_department": dept_quality_summary,
        "timeliness": timeliness,
    })
    dump("layer5_resolution.json", {
        "n_families": len(families),
        "resolution_counts": resolution,
        "families": families,
        "stalled_subjects": [
            {"subject": f["subject"], "occurrences": f["occurrences"],
             "sessions": f["sessions"], "departments": f["departments"],
             "askers": f["askers"]} for f in stalled],
    })
    dump("layer6_trends.json", {
        "department_trends": dept_trends,
        "theme_trends": theme_trends,
        "new_vs_recurring": nvr,
        "diversity_index": diversity,
        "emerging_issues": emerging,
        "rising_departments": [{"department": d, **t} for d, t in rising],
        "declining_departments": [{"department": d, **t} for d, t in declining],
    })

    report = _report(rows, theme_counts, region_counts, scope_counts,
                     demand_counts, reply_records, timeliness, resolution,
                     families, emerging, rising, declining, nvr, mla_unmatched,
                     len(extracted))
    (out / "layers_report.md").write_text(report, encoding="utf-8")

    print(f"{len(rows)} questions → {out}")
    print(f"  themes: {len(theme_counts)}  geography: {100 - round(100*len(mla_unmatched)/len(rows),1)}% MLA-matched")
    print(f"  demands: {dict(demand_counts)}")
    print(f"  replies coded: {len(reply_records)}/{len(rows)}")
    print(f"  families: {len(families)}  emerging: {len(emerging)}")
    return 0


def _crosstab(rows, col, key):
    tab = defaultdict(Counter)
    for r in rows:
        tab[str(r.get(col) or "")][r[key]] += 1
    return {k: dict(v.most_common()) for k, v in sorted(tab.items(), key=lambda kv: -sum(kv[1].values()))}


def _report(rows, theme_counts, region_counts, scope_counts, demand_counts,
            reply_records, timeliness, resolution, families, emerging,
            rising, declining, nvr, mla_unmatched, n_extracted):
    lines = [
        "# Six-Layer Analysis",
        f"Source: `data/dl_questions_raw.csv` · Generated: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Questions: {len(rows)} · Extracted replies available: {n_extracted} · Coded: {len(reply_records)}",
        "",
        "## Layer 1 — Thematic classification",
        "",
        "| Theme | Questions | Share |",
        "|---|---|---|",
    ]
    total = len(rows)
    for theme, n in theme_counts.most_common():
        lines.append(f"| {theme} | {n} | {100*n/total:.1f}% |")
    lines += ["", "## Layer 2 — Geographic tagging", "",
              "| Region | Questions | Share |", "|---|---|---|"]
    for region, n in region_counts.most_common():
        lines.append(f"| {region} | {n} | {100*n/total:.1f}% |")
    lines += ["", "| Question scope | Count |", "|---|---|"]
    for scope, n in scope_counts.most_common():
        lines.append(f"| {scope} | {n} |")
    if mla_unmatched:
        lines += ["", f"Unmatched askers ({len(mla_unmatched)}): " + ", ".join(mla_unmatched[:10])]
    lines += ["", "## Layer 3 — Demand types", "",
              "| Demand type | Questions | Share |", "|---|---|---|"]
    for dtype, n in demand_counts.most_common():
        lines.append(f"| {dtype} | {n} | {100*n/total:.1f}% |")
    lines += ["", "## Layer 4 — Response quality", "",
              f"- Replies coded: **{len(reply_records)}** of {total} "
              f"({100*len(reply_records)/total:.1f}%)",
              f"- Timeliness coverage: {timeliness.get('coverage', 0)}% "
              f"(median {timeliness.get('median_days', 'n/a')} days, "
              f"P75 {timeliness.get('p75_days', 'n/a')} days, "
              f"{timeliness.get('share_over_30d', 0)}% over 30 days)"]
    lines += ["", "## Layer 5 — Resolution tracking", "",
              f"- Recurring families: **{len(families)}**",
              "| Trajectory | Families |", "|---|---|"]
    for status, n in sorted(resolution.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {status} | {n} |")
    lines += ["", "## Layer 6 — Trends and emerging issues", "",
              "### Rising departments (mean session-over-session delta)", ""]
    for d, t in rising[:8]:
        lines.append(f"- {d}: {t['mean_delta']:+.2f}/session (total {t['total']})")
    lines += ["", "### Declining departments", ""]
    for d, t in declining[:8]:
        lines.append(f"- {d}: {t['mean_delta']:+.2f}/session (total {t['total']})")
    lines += ["", f"### Emerging issues watchlist ({len(emerging)})", ""]
    for e in emerging[:15]:
        lines.append(f"- **{e['subject']}** — first {e['first_session']}, "
                     f"{e['occurrences']} occurrences, {len(e['askers'])} askers, "
                     f"{', '.join(e['departments'][:2])}")
    lines += ["", "## New vs recurring per session", "",
              "| Session | Questions | Recurring | New | Recurring % |",
              "|---|---|---|---|---|"]
    for session, v in nvr.items():
        lines.append(f"| {session} | {v['questions']} | {v['recurring']} | "
                     f"{v['new']} | {v['recurring_pct']}% |")
    lines += ["", "---",
              "Full data: `layer1_themes.json` … `layer6_trends.json` in this directory.",
              "Every dimension is reported separately; no composite scores are computed."]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
