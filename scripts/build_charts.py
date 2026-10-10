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
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
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
    message = fig.axes[0].get_title() if fig.axes else ""
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{chart_id}.{ext}", dpi=150 if ext == "png" else None,
                    bbox_inches="tight")
    plt.close(fig)
    MANIFEST.append({"id": chart_id, "title": title, "pillar": pillar,
                     "caption": caption, "message": message,
                     "files": [f"{chart_id}.png", f"{chart_id}.svg"]})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stats = json.loads((REPO / "output/stats.json").read_text(encoding="utf-8"))
    layers = {}
    for name in ("layer1_themes", "layer2_geography", "layer3_demands",
                 "layer5_resolution", "layer6_trends"):
        layers[name] = json.loads((REPO / "output/layers" / f"{name}.json").read_text(encoding="utf-8"))
    rows = base.scope_rows(load_rows(str(REPO / "data/dl_questions_raw.csv")))
    total = len(rows)
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
    style(ax, xlabel=f"Questions (share of {total:,})")
    top3 = depts[:3]
    top3_share = round(sum(d["share"] for d in top3), 1)
    ax.set_title(f"{', '.join(d['department'].replace(' Department', '') for d in top3)} "
                 f"draw {top3_share}% of all questions", fontsize=13, color=NAVY, pad=12)
    save(fig, "01-dept-attention", "Department attention", "Pillar 1",
         "Questions per department with share of the corpus. Source: stats.json.")

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
    leaders = Counter()
    for j in range(len(order)):
        best = max(range(len(top15)), key=lambda i: mat[i][j])
        if mat[best][j]:
            leaders[top15[best]] += 1
    lead_name, lead_n = leaders.most_common(1)[0] if leaders else ("—", 0)
    ax.set_title(f"{lead_name.replace(' Department', '')} leads {lead_n} of "
                 f"{len(order)} sessions", fontsize=13, color=NAVY, pad=12)
    save(fig, "02-dept-session-heatmap", "Attention matrix", "Pillars 1–2",
         f"Question counts for the top-15 departments across all {len(order)} sessions. Source: CSV.")

    # ── 3. Thematic bar ──
    themes = layers["layer1_themes"]["theme_counts"]
    items = sorted(themes.items(), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(10, 7.5))
    ax.barh([t for t, _ in items][::-1], [n for _, n in items][::-1], color=TEAL, edgecolor="white")
    style(ax, xlabel="Questions")
    top2 = items[:2]
    top2_share = round(100 * sum(n for _, n in top2) / total, 1)
    ax.set_title(f"{top2[0][0]} and {top2[1][0]} take {top2_share}% of all questions",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "03-themes", "Thematic attention", "Pillar 1",
         "Rule-based thematic coding (Layer 1); every row records its evidence. Source: layer1_themes.json.")

    # ── 4. District bar (choropleth substitute) ──
    districts = layers["layer2_geography"]["district_counts"]
    items = sorted(((k, v) for k, v in districts.items() if k), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(10, 6))
    names = [k for k, _ in items][::-1]
    vals = [v for _, v in items][::-1]
    ax.barh(names, vals, color=NAVY, edgecolor="white")
    for i, v in enumerate(vals):
        ax.text(v + 8, i, f"{v} ({100 * v / total:.1f}%)", va="center", fontsize=9, color=GRAY70)
    style(ax, xlabel="Questions (by asker's district; % of corpus)")
    top_d, top_n = items[0]
    ax.set_title(f"{top_d} leads with {top_n} questions "
                 f"({100 * top_n / total:.1f}% of all questions)",
                 fontsize=13, color=NAVY, pad=12)
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
    ax.set_title(f"“{top[0]['subject']}” recurs most — asked in "
                 f"{len(top[0]['sessions'])} of {len(order)} sittings",
                 fontsize=13, color=NAVY, pad=12)
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
    ax.set_title(f"Information is the demand in {100 * layers['layer3_demands']['demand_counts']['Information'] / total:.0f}% "
                 f"of questions; action demands cluster in works departments",
                 fontsize=13, color=NAVY, pad=12)
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
    ax.set_title(f"Question volume peaked at {max(qs)} in "
                 f"{sess_labels[qs.index(max(qs))]}", fontsize=13, color=NAVY, pad=12)
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
    ax.set_title(f"{combined[-1][0].replace(' Department', '')} gains attention fastest "
                 f"(+{combined[-1][1]:.1f}/session); "
                 f"{combined[0][0].replace(' Department', '')} loses it "
                 f"({combined[0][1]:.1f})", fontsize=13, color=NAVY, pad=12)
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
    det = (overall["substantiveness"].get("detailed", 0)
           + overall["substantiveness"].get("very_detailed", 0))
    det_pct = 100 * det / overall["n_coded"] if overall["n_coded"] else 0
    ax.set_title(f"{det_pct:.0f}% of coded replies are detailed or very detailed "
                 f"(n={overall['n_coded']})", fontsize=13, color=NAVY, pad=12)
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
    n_assure = sum(1 for a, e in zip(xs, ys) if a > e)
    ax.set_title(f"Assurance language outweighs evasion in {n_assure} of "
                 f"{len(xs)} departments", fontsize=13, color=NAVY, pad=12)
    save(fig, "10-assurance-evasion", "Response signals", "Pillar 2",
         "Bubble size = coded replies. Ported signal registries; weights, not scores.")

    # ── 11. Reply coverage by session ──
    fig, ax = plt.subplots(figsize=(12, 5))
    cov = [s["coverage"] for s in sessions]
    colors = [GREEN if c >= 99 else (AMBER if c >= 80 else RED) for c in cov]
    ax.bar(sess_labels, cov, color=colors, edgecolor="white")
    ax.axhline(stats["overview"]["reply_coverage"], color=NAVY, linestyle="--",
               label=f"overall {stats['overview']['reply_coverage']}%")
    handles, labels = ax.get_legend_handles_labels()
    handles += [Patch(color=GREEN, label="≥99% covered"),
                Patch(color=AMBER, label="80–99% covered"),
                Patch(color=RED, label="<80% covered")]
    labels += ["≥99% covered", "80–99% covered", "<80% covered"]
    ax.legend(handles, labels, frameon=False, fontsize=9, ncol=2)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    style(ax, ylabel="% questions with a signed reply")
    ax.set_ylim(0, 105)
    full = sum(1 for c in cov if c >= 100)
    ax.set_title(f"Reply coverage hit 100% in {full} of {len(cov)} sessions",
                 fontsize=13, color=NAVY, pad=12)
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
    ax.set_title(f"{res.get('stalled', 0)} of {sum(res.values())} recurring subjects "
                 f"show no progress language", fontsize=13, color=NAVY, pad=12)
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
    n_em = len(emerging)
    firsts = {e["first_session"] for e in emerging}
    ax.set_title(f"{n_em} issues first surfaced in the {len(firsts)} most recent sessions",
                 fontsize=13, color=NAVY, pad=12)
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
    star_total, unstar_total = sum(star), sum(unstar)
    ax.set_title(f"Starred (oral) questions outweigh unstarred "
                 f"{star_total:,} to {unstar_total:,}", fontsize=13, color=NAVY, pad=12)
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
    top_m = mlas[0]
    ax.set_title(f"{top_m['mla']} asks the most ({top_m['questions']}) with the "
                 f"widest departmental reach ({top_m['departments']} departments)",
                 fontsize=13, color=NAVY, pad=12)
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
    # largest single cell for the message title
    mi, mj = np.unravel_index(int(np.argmax(hmat)), hmat.shape)
    ax.set_title(f"“{top_themes[mi]}” × {top_depts[mj].replace(' Department', '')} "
                 f"is the largest single pairing ({int(hmat[mi, mj])} questions)",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "16-theme-dept-heatmap", "Theme × department", "Pillar 1",
         "Which departments face which policy domains. Source: layer1_themes.json.")

    # ── 17. Mentioned geography top 10 (text names, not MLA seats) ──
    mentioned = layers["layer2_geography"]["mentioned"]
    mdistricts = mentioned["districts"][:10]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.barh([m["place"] for m in mdistricts][::-1],
            [m["questions"] for m in mdistricts][::-1], color=TEAL, edgecolor="white")
    for i, m in enumerate([m for m in mdistricts][::-1]):
        ax.text(m["questions"] + 3, i, f"{m['questions']} ({m['share_pct']}%)",
                va="center", fontsize=9, color=GRAY70)
    style(ax, xlabel=f"% of {total:,} questions naming the district "
                     f"({mentioned['share_with_any_mention_pct']}% name any place)")
    ax.set_title(f"{mentioned['share_with_any_mention_pct']}% of questions name a place — "
                 f"{mdistricts[0]['place']} most often ({mdistricts[0]['share_pct']}%)",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "17-mentioned-places", "Mentioned geography", "Pillar 1",
         "What the text names (gazetteer scan) — complements MLA-seat geography. "
         "Source: layer2_geography.json.")

    # ── 18. Scrutiny vs budget ──
    from legislative_analysis import reference_data as ref_data
    budgets = ref_data.DEPT_BUDGET
    q_by_dept = Counter(normalize_dept(r.get("Departments")) for r in rows)
    bx, by, blabels = [], [], []
    for dept, budget in budgets.items():
        if dept in q_by_dept and q_by_dept[dept] >= 5:
            bx.append(budget)
            by.append(q_by_dept[dept])
            blabels.append(dept)
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.scatter(bx, by, s=110, color=NAVY, alpha=0.7, edgecolors="white", zorder=3)
    for x, y, label in zip(bx, by, blabels):
        ax.annotate(shorten(label, width=24, placeholder="…"), (x, y),
                    fontsize=8, color=GRAY70, xytext=(6, 4), textcoords="offset points")
    style(ax, xlabel="Budget allocation 2025–26 (₹ crore)", ylabel="Questions (2021–2026)")
    big_b = blabels[int(np.argmax(bx))]
    big_b_q = by[int(np.argmax(bx))]
    rank = sum(1 for y in by if y > big_b_q) + 1
    ax.set_title(f"Largest budget, {big_b.replace(' Department', '')} "
                 f"(₹{max(bx):,.0f} crore), ranks #{rank} of {len(by)} in questions asked",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "18-budget-scatter", "Scrutiny vs resources", "Pillar 1",
         "Single-year budget vs multi-year questions (limitation noted); "
         "per-100-crore table in the dashboard. Sources: DEPT_BUDGET, CSV.")

    # ── 19. Opposition intensity by session ──
    bbs = layers["layer3_demands"]["bloc_by_session"]
    blabels = list(bbs)
    ruling = [bbs[s]["counts"]["Ruling"] for s in blabels]
    opposition = [bbs[s]["counts"]["Opposition"] for s in blabels]
    unknown = [bbs[s]["counts"]["Unknown"] for s in blabels]
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.bar(slabels, ruling, label="Ruling", color=NAVY, edgecolor="white")
    ax.bar(slabels, opposition, bottom=ruling, label="Opposition", color=GOLD, edgecolor="white")
    ax.bar(slabels, unknown, bottom=np.array(ruling) + np.array(opposition),
           label="Unknown", color=GRAY40, edgecolor="white")
    for i, s in enumerate(blabels):
        pct = bbs[s]["opposition_pct"]
        ax.text(i, ruling[i] + opposition[i] + unknown[i] + 4, f"{pct:.0f}% opp",
                ha="center", fontsize=8, color=GRAY70)
    ax.legend(frameon=False, fontsize=9)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    style(ax, ylabel="Questions")
    opp_total_all = sum(opposition)
    opp_led = sum(1 for o, r in zip(opposition, ruling) if o > r)
    ax.set_title(f"The opposition asked {opp_total_all:,} of {total:,} questions "
                 f"({100 * opp_total_all / total:.0f}%) and led questioning "
                 f"in {opp_led} of {len(blabels)} sessions",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "19-opposition", "Opposition intensity", "Pillar 2",
         "Asker bloc from MLA party records; counts only, no effectiveness claims. "
         "Source: layer3_demands.json.")

    # ── 20. Execution stages by department ──
    stage_order = ["None evidenced", "Concept/Proposal", "Administrative Processing",
                   "Sanction/Funding", "Approval", "Procurement", "Execution/Award",
                   "Implementation", "Completion"]
    stage_depts = [d for d, _ in
                   sorted(((d, v) for d, v in dept_summary.items()),
                          key=lambda kv: -kv[1]["n_replies"])[:10]]
    stage_colors = {"None evidenced": GRAY40, "Concept/Proposal": "#D6C9A8",
                    "Administrative Processing": GOLD, "Sanction/Funding": AMBER,
                    "Approval": "#AF7AC5", "Procurement": "#5DADE2",
                    "Execution/Award": TEAL, "Implementation": "#1E8449",
                    "Completion": GREEN}
    fig, ax = plt.subplots(figsize=(12, 7))
    bottom = np.zeros(len(stage_depts))
    for stage in stage_order:
        vals = np.array([dept_summary[d]["stage_distribution"].get(stage, 0)
                         for d in stage_depts])
        totals = np.array([dept_summary[d]["n_replies"] for d in stage_depts], dtype=float)
        pcts = np.divide(vals, totals, out=np.zeros_like(vals, dtype=float),
                         where=totals > 0) * 100
        ax.bar([shorten(d, width=26, placeholder="…") for d in stage_depts], pcts,
               bottom=bottom, label=stage, color=stage_colors[stage], edgecolor="white")
        bottom += pcts
    ax.legend(frameon=False, fontsize=8, ncol=3)
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    style(ax, ylabel="% of coded replies")
    stage_overall = overall["stage_distribution"]
    n_none = stage_overall.get("None evidenced", 0)
    none_pct = 100 * n_none / overall["n_coded"] if overall["n_coded"] else 0
    top_stage = max((s for s in stage_overall if s != "None evidenced"),
                    key=lambda s: stage_overall.get(s, 0), default="—")
    ax.set_title(f"{none_pct:.0f}% of replies evidence no delivery stage; "
                 f"“{top_stage}” is the most-cited stage",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "20-exec-stages", "Execution stages", "Pillar 2",
         "Highest evidenced lifecycle stage per reply (negation-aware). "
         f"n={overall['n_coded']} coded replies.")

    # ── 21. Latency histogram ──
    lats_all = [x["latency"] for x in _records if x["latency"] is not None]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    if lats_all:
        bins = list(range(0, min(max(lats_all) + 5, 125), 5))
        ax.hist(lats_all, bins=bins, color=NAVY, edgecolor="white", zorder=3)
        med = statistics.median(lats_all)
        ax.axvline(med, color=RED, linestyle="--", linewidth=2,
                   label=f"median {med} days")
        ax.axvline(30, color=AMBER, linestyle=":", linewidth=2, label="30-day mark")
        ax.legend(frameon=False, fontsize=9)
        over30 = 100 * sum(1 for d in lats_all if d > 30) / len(lats_all)
        ax.set_title(f"Median reply time: {med:g} days; "
                     f"{over30:.0f}% take longer than 30 days",
                     fontsize=13, color=NAVY, pad=12)
    else:
        ax.set_title("How long replies take", fontsize=13, color=NAVY, pad=12)
    style(ax, xlabel="Days from submission to reply", ylabel="Replies")
    save(fig, "21-latency", "Reply latency", "Pillar 2",
         "Trustworthy date pairs only; flagged pairs excluded but kept in data.")

    (OUT / "manifest.json").write_text(json.dumps(MANIFEST, indent=2), encoding="utf-8")
    print(f"{len(MANIFEST)} charts -> {OUT}")


if __name__ == "__main__":
    main()
