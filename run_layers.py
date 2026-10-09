"""Run all analytical layers on the legislative dataset.

Layers:
  L1 - Thematic classification (codebook)
  L2 - Geographic tagging (MLA constituency + gazetteer)
  L3 - Demand-type taxonomy (Information/Explanation/Action/Accountability)
  L5 - Recurring subject tracking (cross-session)
  L6 - Trend analysis (departmental, thematic, emerging issues)

Layer 4 (response quality) is produced separately once the
background OCR extraction completes.
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "packages/analysis/src"))

from legislative_analysis import analysis as base
from legislative_analysis.codebook import classify_all, normalize_dept, DEPT_THEME
from legislative_analysis.geography import tag_all, lookup_mla
from legislative_analysis.demand import classify_all as classify_demand_all
from legislative_analysis import longitudinal as longi

REPO = Path(__file__).parent
CSV_PATH = REPO / "data/dl_questions_raw.csv"
OUT_DIR = REPO / "output/layers"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = base.load(str(CSV_PATH))
    subject_of = base.subject_of

    # ── Session ordering (by first sitting date) ──
    order = longi.session_order_of(rows)

    # ── Recurring subjects (exact normalized match ≥ 2 sessions) ──
    seen = defaultdict(set)
    for r in rows:
        key = base.normalize_subject(subject_of(r))
        if len(key) >= base.MIN_SUBJECT_CHARS:
            seen[key].add((r.get("Assembly") or "", r.get("Session") or ""))
    recurring_keys = {k for k, s in seen.items() if len(s) >= 2}

    # ── L1: Thematic classification ──
    classify_all(rows, subject_of)
    theme_counts = Counter(r["_theme"] for r in rows)
    subtheme_counts = Counter((r["_theme"], r["_sub_theme"]) for r in rows)
    method_counts = Counter(r["_theme_evidence"]["method"] for r in rows)

    # ── L2: Geographic tagging ──
    tag_all(rows, subject_of)
    region_counts = Counter(r["_mla_region"] for r in rows)
    district_counts = Counter(r["_mla_district"] for r in rows)
    scope_counts = Counter(r["_scope"] for r in rows)
    mla_unmatched = sorted({r.get("Asked_By") or "" for r in rows
                              if not r.get("_mla_constituency")})

    # ── L3: Demand-type taxonomy ──
    classify_demand_all(rows, subject_of, recurring_keys)
    demand_counts = Counter(r["_demand_type"] for r in rows)

    # ── L5: Recurring families (resolution tracking, text-free part) ──
    families = longi.build_families(rows, subject_of, {}, order)
    resolution = longi.resolution_summary(families)

    # ── L6: Trends + emerging issues ──
    dept_trends = longi.department_trends(rows, order)
    theme_trends = longi.theme_trends(rows, order)
    nvr = longi.new_vs_recurring(rows, subject_of, order)
    diversity = longi.diversity_index(rows, order)
    emerging = longi.emerging_issues(rows, subject_of, order)

    rising = sorted(dept_trends.items(), key=lambda kv: -kv[1]["mean_delta"])[:10]
    declining = sorted(dept_trends.items(), key=lambda kv: kv[1]["mean_delta"])[:10]

    def dump(name, data):
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    dump("layer1_themes.json", {
        "theme_counts": dict(theme_counts.most_common()),
        "subtheme_counts": {f"{t} / {s}": c for (t, s), c in subtheme_counts.most_common()},
        "classification_methods": dict(method_counts),
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
    dump("layer5_resolution.json", {
        "n_families": len(families),
        "resolution_counts": resolution,
        "families": families,
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
                     demand_counts, families, resolution, emerging,
                     rising, declining, nvr, diversity, mla_unmatched)
    (OUT_DIR / "layers_report.md").write_text(report, encoding="utf-8")

    print(f"{len(rows)} questions processed -> {OUT_DIR}")
    print(f"  L1 themes: {len(theme_counts)} classes")
    print(f"  L2 geography: {100 - round(100 * len(mla_unmatched) / len(rows), 1)}% MLA-matched")
    print(f"  L3 demands: {dict(demand_counts)}")
    print(f"  L5 recurring families: {len(families)}")
    print(f"  L6 emerging issues: {len(emerging)}")


def _crosstab(rows, col, key):
    tab = defaultdict(Counter)
    for r in rows:
        tab[str(r.get(col) or "")][r[key]] += 1
    return {k: dict(v.most_common()) for k, v in sorted(tab.items(), key=lambda kv: -sum(kv[1].values()))}


def _report(rows, theme_counts, region_counts, scope_counts, demand_counts,
            families, resolution, emerging, rising, declining, nvr, diversity,
            mla_unmatched):
    total = len(rows)
    lines = [
        "# Six-Layer Analysis (Question-Side Layers)",
        f"Source: `data/dl_questions_raw.csv` · Generated: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Questions: {total} · Sessions: {len({(r.get('Assembly'), r.get('Session')) for r in rows})}",
        "",
        "> Layer 4 (response quality) is added once the OCR extraction run completes.",
        "",
        "## Layer 1 — Thematic classification",
        "",
        "| Theme | Questions | Share |",
        "|---|---|---|",
    ]
    for theme, n in theme_counts.most_common():
        lines.append(f"| {theme} | {n} | {100 * n / total:.1f}% |")

    lines += ["", "## Layer 2 — Geographic tagging", "",
              "| Region | Questions | Share |", "|---|---|---|"]
    for region, n in region_counts.most_common():
        lines.append(f"| {region} | {n} | {100 * n / total:.1f}% |")
    lines += ["", "| Question scope | Count |", "|---|---|"]
    for scope, n in scope_counts.most_common():
        lines.append(f"| {scope} | {n} |")
    if mla_unmatched:
        lines += ["", f"Unmatched askers ({len(mla_unmatched)}): "
                     + ", ".join(mla_unmatched[:10])]

    lines += ["", "## Layer 3 — Demand types", "",
              "| Demand type | Questions | Share |", "|---|---|---|"]
    for dtype, n in demand_counts.most_common():
        lines.append(f"| {dtype} | {n} | {100 * n / total:.1f}% |")

    lines += ["", "## Layer 5 — Recurring subjects", "",
              f"- Recurring families (same subject in ≥2 sessions): **{len(families)}**",
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

    lines += ["", "## MLA diversity index (mean departments questioned per MLA)", "",
              "| Session | Diversity |", "|---|---|"]
    for session, v in diversity.items():
        lines.append(f"| {session} | {v} |")

    lines += ["", "---",
              "Full data: `layer1_themes.json` … `layer6_trends.json` in this directory.",
              "Every dimension is reported separately; no composite scores are computed."]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
