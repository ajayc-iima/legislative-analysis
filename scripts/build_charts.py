"""Publication charts for the Compendium (PLAN.md Task 4.2).

Reads output/stats.json, output/layers/*.json and the extracted
replies; writes PNG + SVG per chart plus charts/manifest.json.
Every chart carries a data-source caption; dimensions are never
collapsed into composite scores.

Two documented substitutions (both noted in captions):
- district choropleth -> district bar chart (no boundary shapefile
  in the repo; the bar carries identical counts).
- resolution Sankey -> trajectory bar chart until OCR replies
  resolve trajectories (today all families await replies; a
  single-flow Sankey would mislead).

Regenerate any time: python scripts/build_charts.py
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from textwrap import shorten

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))
sys.path.insert(0, str(REPO))

from legislative_analysis import analysis as base  # noqa: E402
from legislative_analysis.analysis import load as load_rows, parse_date  # noqa: E402
from legislative_analysis.codebook import normalize_dept  # noqa: E402
from legislative_analysis import longitudinal as longi  # noqa: E402
from build_compendium import compute_layer4, load_extracted  # noqa: E402

NAVY, TEAL, GOLD = "#1A3C6E", "#2A8E9C", "#C9A227"
GRAY70, GRAY40, GRAY15 = "#4A4A4A", "#9E9E9E", "#E0E0E0"
GREEN, AMBER, RED = "#27AE60", "#E67E22", "#C0392B"
DEMAND_COLORS = {"Information": NAVY, "Action": TEAL, "Explanation": GOLD,
                 "Accountability": RED}
SUBST_COLORS = {"brief": RED, "standard": AMBER, "detailed": TEAL,
                "very_detailed": NAVY}
TRAJ_COLORS = {"resolved": GREEN, "progressing": TEAL, "stalled": AMBER,
               "regressed": RED, "mixed": GRAY40, "awaiting_replies": GRAY15,
               "unknown": GRAY40}

OUT = REPO / "output/charts"
MANIFEST = []


def style(ax, xlabel="", ylabel=""):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRAY40)
    ax.spines["bottom"].set_color(GRAY40)
    ax.tick_params(colors=GRAY70, labelsize=9)
    ax.yaxis.label.set_color(GRAY70)
    ax.xaxis.label.set_color(GRAY70)
    ax.grid(axis="x", color=GRAY15, linewidth=0.6, linestyle="--", alpha=0.9)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10)


def save(fig, chart_id, title, pillar, caption):
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{chart_id}.{ext}", dpi=150 if ext == "png" else None,
                    bbox_inches="tight")
    plt.close(fig)
    MANIFEST.append({"id": chart_id, "title": title, "pillar": pillar,
                     "caption": caption, "files": [f"{chart_id}.png", f"{chart_id}.svg"]})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stats = json.loads((REPO / "output/stats.json").read_text(encoding="utf-8"))
    layers = {}
    for name in ("layer1_themes", "layer2_geography", "layer3_demands",
                 "layer5_resolution", "layer6_trends"):
        layers[name] = json.loads((REPO / "output/layers" / f"{name}.json").read_text(encoding="utf-8"))
    rows = base.scope_rows(load_rows(str(REPO / "data/dl_questions_raw.csv")))
    order = longi.session_order_of(rows)
    first_year = {}
    for r in rows:
        sk = (r.get("Assembly") or "", r.get("Session") or "")
        d = parse_date(r.get("Session_Date"))
        if d and (sk not in first_year or d.year < first_year[sk]):
            first_year[sk] = d.year

    def year_label(assembly, session):
        num = "10" if "Tenth" in str(assembly) else "11"
        kind = str(session).split()[0][:3]
        yy = f"'{first_year.get((assembly, session), 0) % 100:02d}"
        return f"{num} {kind} {yy}"

    slabels = [year_label(a, s) for a, s in order]

    sessions = stats["sessions"]
    sess_labels = [year_label(s["assembly"], s["session"]) for s in sessions]

    # ── 1. Department attention bar (top 20 + share) ──
    depts = stats["departments"][:20]
    fig, ax = plt.subplots(figsize=(10, 8))
    names = [d["department"] for d in depts][::-1]
    vals = [d["questions"] for d in depts][::-1]
    colors = [GOLD if v == max(vals) else NAVY for v in vals]
    ax.barh(names, vals, color=colors, edgecolor="white")
    for i, v in enumerate(vals):
        share = next(d["share"] for d in depts if d["questions"] == v)
        ax.text(v + 2, i, f"{v} ({share}%)", va="center", fontsize=9, color=GRAY70)
    style(ax, xlabel="Questions (share of 2,634)")
    ax.set_title("Legislative attention by department (top 20)", fontsize=13, color=NAVY, pad=12)
    save(fig, "01-dept-attention", "Department attention", "Pillar 1",
         "Questions per department with share of the 2,634-question corpus. Source: stats.json.")

    # ── 2. Department × session heatmap (top 15) ──
    top15 = [d["department"] for d in stats["departments"][:15]]
    mat = np.zeros((len(top15), len(order)), dtype=int)
    canon = {normalize_dept(r.get("Departments")): None for r in rows}
    for r in rows:
        d = normalize_dept(r.get("Departments"))
        disp = next((t for t in top15 if normalize_dept(t) == d), None)
        if disp is None:
            continue
        try:
            j = order.index((r.get("Assembly") or "", r.get("Session") or ""))
        except ValueError:
            continue
        mat[top15.index(disp)][j] += 1
    fig, ax = plt.subplots(figsize=(13, 8))
    im = ax.imshow(mat, aspect="auto", cmap="Blues", vmin=0)
    ax.set_yticks(range(len(top15)))
    ax.set_yticklabels([shorten(t, width=36, placeholder="…") for t in top15], fontsize=9)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(slabels, rotation=45, ha="right", fontsize=8)
    for i in range(len(top15)):
        for j in range(len(order)):
            if mat[i][j]:
                ax.text(j, i, mat[i][j], ha="center", va="center", fontsize=7,
                        color="white" if mat[i][j] > mat.max() / 2 else GRAY70)
    fig.colorbar(im, ax=ax, label="Questions")
    ax.set_title("Department × session attention matrix", fontsize=13, color=NAVY, pad=12)
    save(fig, "02-dept-session-heatmap", "Attention matrix", "Pillars 1–2",
         "Question counts for the top-15 departments across all 16 sessions. Source: CSV.")

    # ── 3. Thematic bar ──
    themes = layers["layer1_themes"]["theme_counts"]
    items = sorted(themes.items(), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(10, 7.5))
    ax.barh([t for t, _ in items][::-1], [n for _, n in items][::-1], color=TEAL, edgecolor="white")
    style(ax, xlabel="Questions")
    ax.set_title("Legislative attention by policy domain", fontsize=13, color=NAVY, pad=12)
    save(fig, "03-themes", "Thematic attention", "Pillar 1",
         "Rule-based thematic coding (Layer 1); every row records its evidence. Source: layer1_themes.json.")

    # ── 4. District bar (choropleth substitute) ──
    districts = layers["layer2_geography"]["district_counts"]
    items = sorted(((k, v) for k, v in districts.items() if k), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh([k for k, _ in items][::-1], [v for _, v in items][::-1], color=NAVY, edgecolor="white")
    style(ax, xlabel="Questions (by asker's district)")
    ax.set_title("Legislative attention by district", fontsize=13, color=NAVY, pad=12)
    save(fig, "04-districts", "Geographic attention", "Pillar 1",
         "Bar substitute for a choropleth (no boundary shapefile in repo); identical counts. Source: layer2_geography.json.")

    # ── 5. Recurring subjects × session dot plot ──
    fams = layers["layer5_resolution"]["families"]
    top = sorted(fams.values(), key=lambda f: (-f["occurrences"], f["subject"]))[:15]
    order_str = [f"{a.split()[0]} {s}" for a, s in order]
    fig, ax = plt.subplots(figsize=(13, 7))
    for i, f in enumerate(top):
        xs = [order_str.index(s) for s in f["sessions"] if s in order_str]
        ax.scatter(xs, [i] * len(xs), s=70, color=NAVY, zorder=3)
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels([shorten(f["subject"], width=54, placeholder="…") for f in top],
                       fontsize=8)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(slabels, rotation=45, ha="right", fontsize=8)
    ax.grid(axis="x", color=GRAY15, linewidth=0.6, linestyle="--", alpha=0.9)
    ax.set_title("Recurring subjects across sessions (top 15)", fontsize=13, color=NAVY, pad=12)
    save(fig, "05-recurring-dots", "Sustained attention", "Pillar 1",
         "Each dot = the subject was asked in that session (exact normalized match). Source: layer5_resolution.json.")

    # ── 6. Demand-type stacked bar by department ──
    crosstab = layers["layer3_demands"]["demand_by_department"]
    agg = defaultdict(Counter)
    for raw, counts in crosstab.items():
        agg[normalize_dept(raw)].update(counts)
    top12 = sorted(agg, key=lambda d: -sum(agg[d].values()))[:12]
    order_d = ["Information", "Action", "Explanation", "Accountability"]
    fig, ax = plt.subplots(figsize=(12, 7))
    bottom = np.zeros(len(top12))
    for dtype in order_d:
        vals = np.array([agg[d][dtype] for d in top12])
        ax.bar([t[:30] for t in top12], vals, bottom=bottom, label=dtype,
               color=DEMAND_COLORS[dtype], edgecolor="white")
        bottom += vals
    ax.legend(frameon=False, fontsize=9)
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    style(ax, ylabel="Questions")
    ax.set_title("Demand types by department (top 12)", fontsize=13, color=NAVY, pad=12)
    save(fig, "06-demand-by-dept", "Demand types", "Pillar 2",
         "What each question demands: data, reasons, action, or follow-up. Source: layer3_demands.json.")

    # ── 7. Session volume trend + assembly shading ──
    fig, ax = plt.subplots(figsize=(12, 5))
    qs = [s["questions"] for s in sessions]
    ax.plot(sess_labels, qs, marker="o", color=NAVY, linewidth=2)
    ax.fill_between(sess_labels, qs, alpha=0.08, color=NAVY)
    tenth_n = sum(1 for s in sessions if "Tenth" in s["assembly"])
    ax.axvspan(-0.5, tenth_n - 0.5, color=GOLD, alpha=0.10)
    ax.text(1, max(qs) * 0.95, "10th Assembly", fontsize=9, color=GRAY70)
    ax.text(tenth_n + 1, max(qs) * 0.95, "11th Assembly", fontsize=9, color=GRAY70)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    style(ax, ylabel="Questions")
    ax.set_title("Questions per session (10th → 11th Assembly)", fontsize=13, color=NAVY, pad=12)
    save(fig, "07-session-trend", "Volume trend", "Pillar 2",
         "Session-level question volume with the assembly transition shaded. Source: stats.json.")

    # ── 8. Department trend slopes ──
    trends = layers["layer6_trends"]
    combined = ([(d["department"], d["mean_delta"]) for d in trends["rising_departments"][:8]] +
                [(d["department"], d["mean_delta"]) for d in trends["declining_departments"][:8]])
    combined.sort(key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(10, 6.5))
    colors = [GREEN if v > 0 else RED for _, v in combined]
    ax.barh([d[:36] for d, _ in combined], [v for _, v in combined], color=colors, edgecolor="white")
    ax.axvline(0, color=GRAY70, linewidth=1)
    style(ax, xlabel="Mean session-over-session change (questions/session)")
    ax.set_title("Rising and declining departments", fontsize=13, color=NAVY, pad=12)
    save(fig, "08-dept-slopes", "Attention shifts", "Pillar 2",
         "Mean per-session change in question volume. Source: layer6_trends.json.")

    # ── 9/10. Response quality (Layer 4; regenerates as OCR accrues) ──
    extracted = load_extracted()
    overall, dept_summary, _records = compute_layer4(rows, extracted)

    topq = list(dept_summary)[:12]
    fig, ax = plt.subplots(figsize=(12, 7))
    bands = ["brief", "standard", "detailed", "very_detailed"]
    bottom = np.zeros(len(topq))
    for band in bands:
        vals = np.array([dept_summary[d]["substantiveness"].get(band, 0) for d in topq])
        totals = np.array([dept_summary[d]["n_replies"] for d in topq], dtype=float)
        pct = np.divide(vals, totals, out=np.zeros_like(vals, dtype=float),
                        where=totals > 0) * 100
        ax.bar([d[:28] for d in topq], pct, bottom=bottom, label=band,
               color=SUBST_COLORS[band], edgecolor="white")
        bottom += pct
    ax.legend(frameon=False, fontsize=9, title="Reply length")
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    style(ax, ylabel="% of coded replies")
    ax.set_title(f"Response substantiveness by department (n={overall['n_coded']} coded)",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "09-substantiveness", "Response quality", "Pillar 2",
         f"Length bands over {overall['n_coded']} OCR-coded replies; regenerates as extraction accrues.")

    fig, ax = plt.subplots(figsize=(9, 7))
    xs = [dept_summary[d]["assurance_weight_mean"] for d in dept_summary]
    ys = [dept_summary[d]["evasion_weight_mean"] for d in dept_summary]
    ns = [dept_summary[d]["n_replies"] for d in dept_summary]
    sizes = [20 + 60 * n / max(ns) for n in ns]
    ax.scatter(xs, ys, s=sizes, color=NAVY, alpha=0.65, edgecolors="white")
    labelled = set()
    for key, idx in (("evasion", int(np.argsort(ys)[-1])),
                     ("assurance", int(np.argsort(xs)[-1]))):
        d = list(dept_summary)[idx]
        labelled.add(d)
    for i, d in enumerate(dept_summary):
        if d in labelled:
            ax.annotate(shorten(d, width=26, placeholder="…"),
                        (xs[i], ys[i]), fontsize=8, color=GRAY70,
                        xytext=(6, 6 if i % 2 == 0 else -12),
                        textcoords="offset points")
    style(ax, xlabel="Assurance-signal weight (mean)", ylabel="Evasion-signal weight (mean)")
    ax.set_title("Assurance vs evasion by department", fontsize=13, color=NAVY, pad=12)
    save(fig, "10-assurance-evasion", "Response signals", "Pillar 2",
         "Bubble size = coded replies. Ported signal registries; weights, not scores.")

    # ── 11. Reply coverage by session ──
    fig, ax = plt.subplots(figsize=(12, 5))
    cov = [s["coverage"] for s in sessions]
    colors = [GREEN if c >= 99 else (AMBER if c >= 80 else RED) for c in cov]
    ax.bar(sess_labels, cov, color=colors, edgecolor="white")
    ax.axhline(stats["overview"]["reply_coverage"], color=NAVY, linestyle="--",
               label=f"overall {stats['overview']['reply_coverage']}%")
    ax.legend(frameon=False, fontsize=9)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    style(ax, ylabel="% questions with a signed reply")
    ax.set_ylim(0, 105)
    ax.set_title("Reply coverage by session", fontsize=13, color=NAVY, pad=12)
    save(fig, "11-coverage", "Reply coverage", "Pillar 2",
         "Whether a signed reply PDF exists per session. Source: stats.json.")

    # ── 12. Resolution trajectories (bar until Sankey is meaningful) ──
    res = layers["layer5_resolution"]["resolution_counts"]
    fig, ax = plt.subplots(figsize=(9, 5))
    keys = sorted(res, key=lambda k: -res[k])
    ax.bar(keys, [res[k] for k in keys],
           color=[TRAJ_COLORS.get(k, GRAY40) for k in keys], edgecolor="white")
    style(ax, ylabel="Recurring families")
    ax.tick_params(axis="x", rotation=20, labelsize=9)
    ax.set_title("Resolution trajectories of recurring subjects", fontsize=13, color=NAVY, pad=12)
    save(fig, "12-resolution", "Resolution tracking", "Pillar 3",
         "Bar until replies resolve trajectories; a Sankey follows once resolved/progressing/stalled split. Source: layer5_resolution.json.")

    # ── 13. Emerging issues timeline ──
    emerging = layers["layer6_trends"]["emerging_issues"]
    fig, ax = plt.subplots(figsize=(12, 4.5))
    if emerging:
        ys = range(len(emerging))
        xs = [order_str.index(e["first_session"]) if e["first_session"] in order_str else len(order_str) - 1
              for e in emerging]
        sizes = [120 + 80 * e["occurrences"] for e in emerging]
        ax.scatter(xs, list(ys), s=sizes, color=TEAL, alpha=0.7, edgecolors="white")
        for i, e in enumerate(emerging):
            ax.text(xs[i] + 0.15, i, f"{e['subject'][:56]} ({e['occurrences']}×, {len(e['askers'])} MLAs)",
                    va="center", fontsize=9, color=GRAY70)
        ax.set_yticks([])
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels(slabels, rotation=45, ha="right", fontsize=8)
        ax.set_xlim(-0.5, len(order) - 0.5)
    style(ax, xlabel="First-appearance session")
    ax.set_title("Emerging issues watchlist", fontsize=13, color=NAVY, pad=12)
    save(fig, "13-emerging", "Emerging issues", "Pillar 3",
         "First seen in the last 3 sessions, ≥2 occurrences, ≥2 askers. Source: layer6_trends.json.")

    # ── 14. Starred vs unstarred trend ──
    by_session = defaultdict(Counter)
    for r in rows:
        value = str(r.get("Question_Type") or r.get("Category") or "")
        kind = "Starred" if "unstarred" not in value.lower() and "starred" in value.lower() else (
            "Unstarred" if "unstarred" in value.lower() else "Unknown")
        by_session[(r.get("Assembly") or "", r.get("Session") or "")][kind] += 1
    star = [by_session[sk]["Starred"] for sk in order]
    unstar = [by_session[sk]["Unstarred"] for sk in order]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(slabels, star, label="Starred", color=NAVY, edgecolor="white")
    ax.bar(slabels, unstar, bottom=star, label="Unstarred", color=GOLD, edgecolor="white")
    ax.legend(frameon=False, fontsize=9)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    style(ax, ylabel="Questions")
    ax.set_title("Starred vs Unstarred questions per session", fontsize=13, color=NAVY, pad=12)
    save(fig, "14-starred", "Question types", "Pillar 2",
         "Starred (oral) vs Unstarred (written) mix per session. Source: CSV Category field.")

    # ── 15. MLA activity bubble ──
    mlas = stats["mlas"]
    fig, ax = plt.subplots(figsize=(10, 7))
    xs = [m["questions"] for m in mlas]
    ys = [m["departments"] for m in mlas]
    ax.scatter(xs, ys, s=[10 + 12 * q for q in xs], color=TEAL, alpha=0.6, edgecolors="white")
    for m in mlas[:8]:
        ax.annotate(m["mla"].split()[-1], (m["questions"], m["departments"]),
                    fontsize=9, color=GRAY70)
    style(ax, xlabel="Questions asked", ylabel="Departments questioned (breadth)")
    ax.set_title("MLA activity: volume × breadth", fontsize=13, color=NAVY, pad=12)
    save(fig, "15-mla-bubble", "Asker activity", "Pillar 1",
         "Each bubble = one MLA; size = questions. Top-8 surnames labelled. Source: stats.json.")

    # ── 16. Theme × department heatmap ──
    tbd = layers["layer1_themes"]["department_by_theme"]
    top_depts = list(tbd)[:12]
    top_themes = [t for t, _ in Counter(
        {t: sum(c.values()) for t, c in layers["layer1_themes"]["theme_by_department"].items()}
    ).most_common(12)]
    hmat = np.zeros((len(top_themes), len(top_depts)), dtype=int)
    for i, theme in enumerate(top_themes):
        for j, dept in enumerate(top_depts):
            hmat[i][j] = layers["layer1_themes"]["theme_by_department"].get(theme, {}).get(dept, 0)
    fig, ax = plt.subplots(figsize=(13, 8))
    im = ax.imshow(hmat, aspect="auto", cmap="Blues", vmin=0)
    ax.set_yticks(range(len(top_themes)))
    ax.set_yticklabels([shorten(t, width=30, placeholder="…") for t in top_themes], fontsize=9)
    ax.set_xticks(range(len(top_depts)))
    ax.set_xticklabels([shorten(d, width=22, placeholder="…") for d in top_depts],
                       rotation=30, ha="right", fontsize=8)
    for i in range(len(top_themes)):
        for j in range(len(top_depts)):
            if hmat[i][j]:
                ax.text(j, i, hmat[i][j], ha="center", va="center", fontsize=7,
                        color="white" if hmat[i][j] > hmat.max() / 2 else GRAY70)
    fig.colorbar(im, ax=ax, label="Questions")
    ax.set_title("Policy domains × departments", fontsize=13, color=NAVY, pad=12)
    save(fig, "16-theme-dept-heatmap", "Theme × department", "Pillar 1",
         "Which departments face which policy domains. Source: layer1_themes.json.")

    (OUT / "manifest.json").write_text(json.dumps(MANIFEST, indent=2), encoding="utf-8")
    print(f"{len(MANIFEST)} charts -> {OUT}")


if __name__ == "__main__":
    main()
