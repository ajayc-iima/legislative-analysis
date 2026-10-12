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
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
# Real <text> in SVG output (not outlined paths): smaller files, selectable
# and screen-reader-readable text. The report strips the in-figure title when
# it renders its own HTML headline for the same message (no double title);
# standalone PNG/SVG keep it for sharing.
matplotlib.rcParams["svg.fonttype"] = "none"
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_hex
from matplotlib.patches import Patch
from matplotlib.transforms import Bbox
from textwrap import shorten

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))
sys.path.insert(0, str(REPO))

from legislative_analysis import analysis as base  # noqa: E402
from legislative_analysis.analysis import load as load_rows, parse_date  # noqa: E402
from legislative_analysis.codebook import normalize_dept  # noqa: E402
from legislative_analysis.naming import member_labels, shared_surnames  # noqa: E402
from legislative_analysis.recurrence import load as load_recurrence  # noqa: E402
from legislative_analysis import longitudinal as longi  # noqa: E402
from build_compendium import compute_layer4, load_extracted  # noqa: E402

NAVY, TEAL, GOLD = "#1A3C6E", "#2A8E9C", "#C9A227"
GRAY70, GRAY40, GRAY15 = "#4A4A4A", "#9E9E9E", "#E0E0E0"
GREEN, AMBER, RED = "#27AE60", "#E67E22", "#C0392B"
DEMAND_COLORS = {"Information": NAVY, "Action": TEAL, "Explanation": GOLD,
                 "Accountability": RED}
SUBST_COLORS = {"brief": "#B4C7DC", "standard": "#8AA8C8",
                "detailed": "#4E77A8", "very_detailed": NAVY}
# Trajectory is an ORDERED progression (regressed -> stalled -> mixed ->
# progressing -> resolved): an ordered cool ramp carries the progression,
# while the two alarm states (regressed, stalled) wear warm highlight
# colors. The previous green/teal/amber/red set read as a rainbow with no
# order (deck: Mapping + Color).
TRAJ_COLORS = {"resolved": NAVY, "progressing": "#4A75A5", "mixed": GRAY40,
               "stalled": AMBER, "regressed": RED, "awaiting_replies": GRAY15,
               "unknown": GRAY40}

OUT = REPO / "output/charts"
MANIFEST = []

# ── One labelling policy for the whole suite ────────────────────────────────
# Labelling is not decoration: it is the reader's only way to read exact
# values off a chart. The rule is uniform across all 21 figures, and every
# figure that applies a cut says so in its caption.
#   * <= FULL_LABEL_MAX marks  -> label EVERY mark
#   * more marks               -> label by a stated, uniform cut
#     (extremes on each axis for scatters; segments large enough to hold
#     text for stacked bars; tail bins of a histogram)
LABEL_MIN_SEGMENT_PCT = 8.0    # stacked segment must be this tall to be labelled
FULL_LABEL_MAX = 30             # above this, scatters label their extremes
EXTREME_LABELS = 5              # per axis, for dense scatters
# Placement attempts for a scatter label, in order: right of the point, then
# left, then above, then below, then a lower-right diagonal. Tried in this
# order so a label moves rather than disappearing.
LABEL_OFFSETS = ((8, 0, "left"), (-8, 0, "right"), (0, 12, "center"),
                 (0, -13, "center"), (10, -7, "left"))
MARKER_CLEARANCE_PX = 4        # keep label text off neighbouring marks
VERIFIABLE_PAIR_MIN = 10       # questions a theme x department cell needs
                              # before the pairing carries real evidence
POLICY_ALL = "Every mark is labelled."
POLICY_EXTREMES = (f"Labelling: the {EXTREME_LABELS} most active members and the "
                    "3 broadest (overlap removed) — too many bubbles to name "
                    "them all.")
POLICY_SEGMENTS = (f"Labels inside segments >= {LABEL_MIN_SEGMENT_PCT:g}% of a "
                   f"column; smaller segments are left to the axis. ")


def label_points(ax, xs, ys, names, priority_idx=None, width=26, fontsize=8,
                 pad_px=4):
    """Label scatter points so that no two labels overlap.

    `priority_idx` (the volume/breadth or axis leaders) is placed first and
    always kept; every other point is added only if its real, measured text
    box clears every label already placed. Measuring the rendered box
    (rather than guessing a data-space radius) is what keeps long
    department names in a tight cluster from stacking on top of one
    another. Deterministic: the same data always yields the same labels, so
    figures rebuild identically.

    A label that will not fit is *moved* (right, left, above, below) before
    it is given up on — dropping a leader because its neighbour was placed
    first would make the figure's own rule self-defeating.
    """
    n = len(xs)
    if not n:
        return 0
    fig = ax.figure
    fig.canvas.draw()                       # realise transforms before measuring
    renderer = fig.canvas.get_renderer()
    plot_area = ax.get_window_extent(renderer=renderer)
    # marker centres in display space: a label must not be printed on top of
    # another mark, which is how a dense cluster turns into unreadable text
    centres = ax.transData.transform(np.column_stack([xs, ys]))
    boxes, kept = [], []
    for i in dict.fromkeys(list(priority_idx or []) + list(range(n))):
        txt = f"{shorten(names[i], width=width, placeholder='…')} " \
              f"({xs[i]:g}, {ys[i]:g})"
        for dx, dy, ha in LABEL_OFFSETS:
            ann = ax.annotate(txt, (xs[i], ys[i]), fontsize=fontsize, color=GRAY70,
                              xytext=(dx, dy), textcoords="offset points",
                              ha=ha, va="center", zorder=6)
            bb = ann.get_window_extent(renderer=renderer)
            box = Bbox.from_extents(bb.x0 - pad_px, bb.y0 - pad_px,
                                    bb.x1 + pad_px, bb.y1 + pad_px)
            # a label that runs past the plot edge lands on the axis labels
            # or in the figure margin, so treat "outside" like "overlaps"
            inside = (box.x0 >= plot_area.x0 and box.x1 <= plot_area.x1
                      and box.y0 >= plot_area.y0 and box.y1 <= plot_area.y1)
            covers_mark = any(
                j != i and box.x0 - MARKER_CLEARANCE_PX <= cx <= box.x1 + MARKER_CLEARANCE_PX
                and box.y0 - MARKER_CLEARANCE_PX <= cy <= box.y1 + MARKER_CLEARANCE_PX
                for j, (cx, cy) in enumerate(centres))
            clash = next((b for b in boxes if box.overlaps(b["box"])), None)
            if inside and clash is None and not covers_mark:
                boxes.append({"box": box, "text": txt})
                kept.append(i)
                break
            ann.remove()
        else:
            if os.environ.get("CHART_LABEL_DEBUG"):
                print(f"  [label dropped] {txt!r}: no clear placement")
    return len(kept)


def label_stacked(ax, xs_labels, stack_vals, totals, series_names, colors,
                  min_pct=LABEL_MIN_SEGMENT_PCT):
    """Label stacked segments that are large enough to hold text.

    Geometry uses the axis' own units (counts or %); the min_pct gate is
    relative to each column's total, so the rule reads the same whatever
    the axis shows.
    """
    bottom = np.zeros(len(xs_labels))
    for vals, name, color in zip(stack_vals, series_names, colors):
        arr = np.array(vals, dtype=float)
        tot = np.array(totals, dtype=float)
        for i, v in enumerate(arr):
            share = 100 * v / tot[i] if tot[i] else 0
            if share >= min_pct:
                y = bottom[i] + v / 2
                ax.text(xs_labels[i], y, f"{v:,.0f}" if v >= 10 else f"{v:.0f}",
                        ha="center", va="center", fontsize=8,
                        color=label_ink(color))
        bottom += arr


def _luminance(color):
    """WCAG 2.1 relative luminance of a #rrggbb fill."""
    def chan(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(ink, bg):
    hi, lo = sorted((_luminance(ink), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def label_ink(bg):
    """Ink for text sitting on `bg`, chosen by measured contrast rather than
    a guessed 'is this dark?'. Mid-greys get dark ink, not grey - grey on
    grey is the most common way a value label quietly becomes unreadable."""
    best = max(("#FFFFFF", "#141414"), key=lambda ink: contrast_ratio(ink, bg))
    return best if contrast_ratio(best, bg) >= 4.5 else "#141414"


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
    # Recurrence is published from whichever method is available, semantic
    # preferred, and every figure that uses it says which one it used.
    recurrence = load_recurrence()
    layers["recurrence"] = recurrence
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
                        color=label_ink(to_hex(im.cmap(im.norm(mat[i][j])))))
    fig.colorbar(im, ax=ax, label="Questions")
    leaders = Counter()
    for j in range(len(order)):
        best = max(range(len(top15)), key=lambda i: mat[i][j])
        if mat[best][j]:
            leaders[top15[best]] += 1
    lead_name, lead_n = leaders.most_common(1)[0] if leaders else ("—", 0)
    # Make the claimed leader visible: ring each session-maximum cell so the
    # "leads N of M sessions" title can be verified by eye, not trusted.
    for j in range(len(order)):
        best = max(range(len(top15)), key=lambda i: mat[i][j])
        if mat[best][j]:
            ax.add_patch(plt.Rectangle((j - 0.48, best - 0.48), 0.96, 0.96,
                                       fill=False, edgecolor=GOLD, linewidth=1.8, zorder=5))
    ax.set_title(f"{lead_name.replace(' Department', '')} leads {lead_n} of "
                 f"{len(order)} sessions", fontsize=13, color=NAVY, pad=12)
    save(fig, "02-dept-session-heatmap", "Attention matrix", "Pillars 1–2",
         f"Question counts for the top-15 departments across all {len(order)} sessions. Source: CSV.")

    # ── 3. Thematic bar ──
    themes = layers["layer1_themes"]["theme_counts"]
    items = sorted(themes.items(), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(10, 7.5))
    ax.barh([t for t, _ in items][::-1], [n for _, n in items][::-1], color=TEAL, edgecolor="white")
    for i, (t, n) in enumerate(reversed(items)):
        ax.text(n + 4, i, f"{n} ({100 * n / total:.1f}%)", va="center", fontsize=9, color=GRAY70)
    ax.set_xlim(0, max(n for _, n in items) * 1.22)
    style(ax, xlabel=f"Questions (share of {total:,})")
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
    ax.set_yticklabels([f"{shorten(f['subject'], width=48, placeholder='…')}  ·  "
                        f"{len(f['sessions'])} sittings"
                        for f in top], fontsize=8)
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
    stack_vals = []
    for dtype in order_d:
        vals = np.array([agg[d][dtype] for d in top12])
        stack_vals.append(vals)
        ax.bar([t[:30] for t in top12], vals, bottom=bottom, label=dtype,
               color=DEMAND_COLORS[dtype], edgecolor="white")
        bottom += vals
    label_stacked(ax, range(len(top12)), stack_vals,
                  [sum(agg[d].values()) for d in top12], order_d,
                  [DEMAND_COLORS[d] for d in order_d])
    ax.legend(frameon=False, fontsize=9, loc="upper center",
              bbox_to_anchor=(0.5, -0.22), ncol=4)
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    style(ax, ylabel="Questions")
    ax.set_title(f"Information is the demand in {100 * layers['layer3_demands']['demand_counts']['Information'] / total:.0f}% "
                 f"of questions; action demands cluster in works departments",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "06-demand-by-dept", "Demand types", "Pillar 2",
         "What each question demands: data, reasons, action, or follow-up. "
         f"Segments >= {LABEL_MIN_SEGMENT_PCT:g}% of a column are labelled. "
         "Source: layer3_demands.json.")

    # ── 7. Session volume trend + assembly shading ──
    fig, ax = plt.subplots(figsize=(12, 5))
    qs = [s["questions"] for s in sessions]
    ax.plot(sess_labels, qs, marker="o", color=NAVY, linewidth=2)
    ax.fill_between(sess_labels, qs, alpha=0.08, color=NAVY)
    # Headroom first, then labels with a halo: a value label crossed by the
    # line (or by an annotation) is a value the reader cannot read.
    top = max(qs)
    ax.set_ylim(0, top * 1.24)
    halo = dict(facecolor="white", alpha=0.9, edgecolor="none", pad=0.8)
    for xi, q in enumerate(qs):
        ax.annotate(f"{q}", (xi, q), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=8, color=GRAY70, bbox=halo, zorder=5)
    tenth_n = sum(1 for s in sessions if "Tenth" in s["assembly"])
    ax.axvspan(-0.5, tenth_n - 0.5, color=GOLD, alpha=0.10)
    ax.text(1, top * 1.20, "10th Assembly", fontsize=9, color=GRAY70, va="top")
    ax.text(tenth_n + 1, top * 1.20, "11th Assembly", fontsize=9, color=GRAY70,
            va="top")
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    style(ax, ylabel="Questions")
    ax.set_title(f"Question volume peaked at {max(qs)} in "
                 f"{sess_labels[qs.index(max(qs))]}", fontsize=13, color=NAVY, pad=12)
    save(fig, "07-session-trend", "Volume trend", "Pillar 2",
         f"Session-level question volume with the assembly transition shaded; "
         f"all {len(qs)} points labelled. Source: stats.json.")

    # ── 8. Department trend slopes ──
    trends = layers["layer6_trends"]
    combined = ([(d["department"], d["mean_delta"]) for d in trends["rising_departments"][:8]] +
                [(d["department"], d["mean_delta"]) for d in trends["declining_departments"][:8]])
    combined.sort(key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(10, 6.5))
    # Diverging = two hues from the deck palette (navy up, gold down), not
    # red/green: the deck's Color test is "purposeful AND accessible", and
    # sign is already encoded redundantly by position around the zero line.
    colors = [NAVY if v > 0 else GOLD for _, v in combined]
    ax.barh([d[:36] for d, _ in combined], [v for _, v in combined], color=colors, edgecolor="white")
    ax.axvline(0, color=GRAY70, linewidth=1)
    span = max(abs(v) for _, v in combined)
    for i, (_, v) in enumerate(combined):
        off = 0.06 * span * (1 if v >= 0 else -1)
        ax.text(v + off, i, f"{v:+.1f}", va="center",
                ha="left" if v >= 0 else "right", fontsize=8, color=GRAY70)
    ax.set_xlim(-span * 1.18, span * 1.18)
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
    fig, ax = plt.subplots(figsize=(12, 7.8))
    bands = ["brief", "standard", "detailed", "very_detailed"]
    bottom = np.zeros(len(topq))
    subst_pcts = []
    subst_totals = []
    for band in bands:
        vals = np.array([dept_summary[d]["substantiveness"].get(band, 0) for d in topq])
        totals = np.array([dept_summary[d]["n_replies"] for d in topq], dtype=float)
        pct = np.divide(vals, totals, out=np.zeros_like(vals, dtype=float),
                        where=totals > 0) * 100
        subst_pcts.append(pct)
        subst_totals.append(totals)
        ax.bar([d[:28] for d in topq], pct, bottom=bottom,
                   label=band.replace("_", " "),
                   color=SUBST_COLORS[band], edgecolor="white")
        bottom += pct
    label_stacked(ax, range(len(topq)), subst_pcts,
                  [100] * len(topq), bands, [SUBST_COLORS[b] for b in bands],
                  min_pct=LABEL_MIN_SEGMENT_PCT)
    ax.legend(frameon=False, fontsize=9, title="Reply detail band (ordered)",
              loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4)
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    style(ax, ylabel="% of coded replies")
    det = (overall["substantiveness"].get("detailed", 0)
           + overall["substantiveness"].get("very_detailed", 0))
    det_pct = 100 * det / overall["n_coded"] if overall["n_coded"] else 0
    ax.set_title(f"{det_pct:.0f}% of coded replies are detailed or very detailed "
                 f"(n={overall['n_coded']})", fontsize=13, color=NAVY, pad=12)
    save(fig, "09-substantiveness", "Response quality", "Pillar 2",
         f"Length bands over {overall['n_coded']} OCR-coded replies; regenerates "
         f"as extraction accrues. Segments >= {LABEL_MIN_SEGMENT_PCT:g}% of a "
         "column are labelled; smaller bands are left to the axis.")

    fig, ax = plt.subplots(figsize=(9, 7))
    xs = [dept_summary[d]["assurance_weight_mean"] for d in dept_summary]
    ys = [dept_summary[d]["evasion_weight_mean"] for d in dept_summary]
    ns = [dept_summary[d]["n_replies"] for d in dept_summary]
    sizes = [20 + 60 * n / max(ns) for n in ns]
    ax.scatter(xs, ys, s=sizes, color=NAVY, alpha=0.65, edgecolors="white")
    n_pts = len(xs)
    prio = (sorted(range(n_pts), key=lambda i: xs[i])[-EXTREME_LABELS:]
            + sorted(range(n_pts), key=lambda i: xs[i])[:2]
            + sorted(range(n_pts), key=lambda i: ys[i])[-EXTREME_LABELS:])
    ax.set_xlim(min(xs) - 0.03 * ((max(xs) - min(xs)) or 1),
                max(xs) + 0.16 * ((max(xs) - min(xs)) or 1))
    ax.set_ylim(min(ys) - 0.05 * ((max(ys) - min(ys)) or 1),
                max(ys) + 0.07 * ((max(ys) - min(ys)) or 1))
    n_lab = label_points(ax, xs, ys, list(dept_summary),
                         priority_idx=prio, width=22)
    style(ax, xlabel="Assurance-signal weight (mean)", ylabel="Evasion-signal weight (mean)")
    n_assure = sum(1 for a, e in zip(xs, ys) if a > e)
    ax.set_title(f"Assurance language outweighs evasion in {n_assure} of "
                 f"{len(xs)} departments", fontsize=13, color=NAVY, pad=12)
    save(fig, "10-assurance-evasion", "Response signals", "Pillar 2",
         "Bubble size = coded replies. Labels: assurance and evasion extremes "
         f"first, then every department whose label fits clear of both the "
         f"other labels and the marks ({n_lab} of {n_pts} labelled; the "
         "remaining departments sit inside one dense cluster). "
         "Ported signal registries; weights, not scores.")

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
    for i, c in enumerate(cov):
        ax.text(i, c + 1.5, f"{c:.0f}", ha="center", fontsize=8, color=GRAY70)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    style(ax, ylabel="% questions with a signed reply")
    ax.set_ylim(0, 105)
    full = sum(1 for c in cov if c >= 100)
    ax.set_title(f"Reply coverage hit 100% in {full} of {len(cov)} sessions",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "11-coverage", "Reply coverage", "Pillar 2",
         "Whether a signed reply PDF exists per session; every bar labelled. Source: stats.json.")

    # ── 12. Resolution trajectories (bar until Sankey is meaningful) ──
    res = layers["layer5_resolution"]["resolution_counts"]
    fig, ax = plt.subplots(figsize=(9, 5))
    keys = sorted(res, key=lambda k: -res[k])
    ax.bar(keys, [res[k] for k in keys],
           color=[TRAJ_COLORS.get(k, GRAY40) for k in keys], edgecolor="white")
    for i, k in enumerate(keys):
        ax.text(i, res[k] + 0.6, f"{res[k]} ({100 * res[k] / sum(res.values()):.0f}%)",
                ha="center", fontsize=9, color=GRAY70)
    ax.set_ylim(0, max(res.values()) * 1.16)
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
    # Stacked column like 06/09/19/20: segments big enough to hold text are
    # labelled inside, and the total plus starred share rides above.
    label_stacked(ax, range(len(star)), [star, unstar],
                  [s + u for s, u in zip(star, unstar)],
                  ["Starred", "Unstarred"], [NAVY, GOLD])
    for i, (s, u) in enumerate(zip(star, unstar)):
        if s + u:
            ax.text(i, s + u + 5, f"{s + u} ({100 * s / (s + u):.0f}% starred)",
                    ha="center", fontsize=8, color=GRAY70)
    ax.set_ylim(0, max((s + u for s, u in zip(star, unstar)), default=1) * 1.16)
    ax.legend(frameon=False, fontsize=9)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    style(ax, ylabel="Questions")
    star_total, unstar_total = sum(star), sum(unstar)
    ax.set_title(f"Starred (oral) questions outweigh unstarred "
                 f"{star_total:,} to {unstar_total:,}", fontsize=13, color=NAVY, pad=12)
    save(fig, "14-starred", "Question types", "Pillar 2",
         "Starred (oral) vs Unstarred (written) mix per session; every column "
         "labelled with its total and starred share, and segments >= "
         f"{LABEL_MIN_SEGMENT_PCT:g}% of a column labelled inside. "
         "Source: CSV Category field.")

    # ── 15. MLA activity bubble ──
    mlas = stats["mlas"]
    n_points = len(mlas)
    fig, ax = plt.subplots(figsize=(12, 7.5))
    xs = [m["questions"] for m in mlas]
    ys = [m["departments"] for m in mlas]
    ax.scatter(xs, ys, s=[10 + 12 * q for q in xs], color=TEAL, alpha=0.6, edgecolors="white")
    # Bubbles are sized by volume, so the volume and breadth leaders are named
    # first; every other bubble is named only when its label fits without
    # colliding - a fixed, rebuild-stable rule.
    #
    # Labels identify *people*: 13 members share the surname Sangma and 8
    # share Lyngdoh, so a surname alone names a family, not a legislator.
    # member_labels() gives the shortest form that identifies one member —
    # judged against every asker in the WHOLE corpus, not the in-scope
    # subset plotted here and not just the 20 bubbles: a member who asked no
    # question after 2021, or fell outside the top 20, still makes
    # "Nongrum" the name of two people.
    all_askers = {str(r.get("Asked_By") or "").strip()
                  for r in load_rows(str(REPO / "data/dl_questions_raw.csv"))}
    asker_labels = member_labels(all_askers)
    by_x = sorted(range(n_points), key=lambda i: xs[i])
    by_y = sorted(range(n_points), key=lambda i: ys[i])
    priority = by_x[-EXTREME_LABELS:] + by_y[-3:]
    ax.set_xlim(min(xs) - 0.06 * ((max(xs) - min(xs)) or 1),
                max(xs) + 0.22 * ((max(xs) - min(xs)) or 1))
    ax.set_ylim(min(ys) - 0.07 * ((max(ys) - min(ys)) or 1),
                max(ys) + 0.10 * ((max(ys) - min(ys)) or 1))
    n_lab = label_points(ax, xs, ys,
                         [asker_labels.get(m["mla"], m["mla"]) for m in mlas],
                         priority_idx=priority, width=22)
    style(ax, xlabel="Questions asked", ylabel="Departments questioned (breadth)")
    top_m = mlas[0]
    ax.set_title(f"{top_m['mla']} asks the most ({top_m['questions']}) with the "
                 f"widest departmental reach ({top_m['departments']} departments)",
                 fontsize=13, color=NAVY, pad=12)
    n_points = len(mlas)
    save(fig, "15-mla-bubble", "Asker activity", "Pillar 1",
         f"Each bubble = one of the {n_points} most active members; size = "
         "questions. Labels: the 5 most active and 3 broadest first, then "
         f"every other bubble whose label fits clear of both the other labels "
         f"and the marks ({n_lab} labelled). Members are named by the shortest "
         "form that identifies one of them: "
         f"{len(shared_surnames(asker_labels))} surnames are carried by more "
         "than one member. Source: stats.json.")

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

    # How much of this matrix is actually evidence? The distribution is
    # long-tailed - median cell 1, largest 213 - so a linear colour scale
    # spends its whole range on a handful of cells and leaves the rest
    # looking empty. Colour therefore follows a square-root law (the printed
    # numbers stay exact counts), and the caption states how many pairings
    # are verifiable at all.
    cells = [int(v) for v in hmat.ravel()]
    non_empty = [v for v in cells if v]
    verifiable = [v for v in non_empty if v >= VERIFIABLE_PAIR_MIN]
    total_cells_questions = sum(cells)
    top10_share = (100 * sum(sorted(non_empty, reverse=True)[:10])
                   / total_cells_questions) if total_cells_questions else 0
    median_cell = statistics.median(cells) if cells else 0

    fig, ax = plt.subplots(figsize=(13.5, 8))
    im = ax.imshow(hmat, aspect="auto", cmap="Blues",
                   norm=matplotlib.colors.PowerNorm(gamma=0.5, vmin=0,
                                                    vmax=max(1, max(cells))))
    col_totals = [int(sum(hmat[:, j])) for j in range(len(top_depts))]
    ax.set_yticks(range(len(top_themes)))
    ax.set_yticklabels([shorten(t, width=30, placeholder="…") for t in top_themes], fontsize=9)
    ax.set_xticks(range(len(top_depts)))
    # column totals on the axis: the matrix shows *which* pairing, the
    # margin shows how much, which a colour ramp alone cannot carry
    ax.set_xticklabels([f"{shorten(d, width=20, placeholder='…')}  ({t:,})"
                        for d, t in zip(top_depts, col_totals)],
                       rotation=30, ha="right", fontsize=8)
    for i in range(len(top_themes)):
        for j in range(len(top_depts)):
            if hmat[i][j]:
                ax.text(j, i, hmat[i][j], ha="center", va="center", fontsize=7,
                        color=label_ink(to_hex(im.cmap(im.norm(hmat[i][j])))))
    fig.colorbar(im, ax=ax, label="Questions (square-root colour scale)")
    # largest single cell, for the caption's method note
    mi, mj = np.unravel_index(int(np.argmax(hmat)), hmat.shape)
    ax.set_title(f"{len(verifiable)} of {len(cells)} theme × department pairings "
                 f"carry {VERIFIABLE_PAIR_MIN}+ questions — and they hold "
                 f"{100 * sum(verifiable) / total_cells_questions:.0f}% of the evidence",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "16-theme-dept-heatmap", "Theme × department", "Pillar 1",
         f"{len(non_empty)} of {len(cells)} cells hold at least one question; "
         f"{len(verifiable)} hold {VERIFIABLE_PAIR_MIN} or more and carry "
         f"{100 * sum(verifiable) / total_cells_questions:.0f}% of the "
         f"{total_cells_questions:,} questions in the matrix; the top 10 "
         f"pairings alone hold {top10_share:.0f}%. The distribution is "
         f"long-tailed (median cell {median_cell:g}, largest {max(cells)}), "
         "so colour uses a square-root scale while every cell prints its exact "
         f"count. Largest single pairing: {top_themes[mi]} × {top_depts[mj]} "
         f"({int(hmat[mi, mj])}). Column totals in brackets. "
         "Source: layer1_themes.json.")

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

    # ── 18. Scrutiny relative to size ──
    # A budget-vs-questions scatter asks the reader to do the division in
    # their head across a 45x spread in x. The same comparison is stated
    # directly as a rate - questions per Rs 100 crore - as a ranked bar with
    # the median marked, so "questioned more/less than its size warrants" is
    # a length to compare, not a slope to infer.
    from legislative_analysis import reference_data as ref_data
    budgets = ref_data.DEPT_BUDGET
    q_by_dept = Counter(normalize_dept(r.get("Departments")) for r in rows)
    # (department, budget crore, questions, questions per Rs 100 crore)
    rates = [(dept, budget, q_by_dept[dept], q_by_dept[dept] / budget * 100)
             for dept, budget in budgets.items()
             if dept in q_by_dept and q_by_dept[dept] >= 5]
    rates.sort(key=lambda r: -r[3])
    med_rate = statistics.median(r[3] for r in rates)
    names = [r[0].replace(" Department", "") for r in rates]
    values = [r[3] for r in rates]
    above = [r >= med_rate for r in values]          # position + colour + label
    fig, ax = plt.subplots(figsize=(11, 7.2))
    ax.barh(names[::-1], values[::-1],
            color=[NAVY if a else GOLD for a in above[::-1]], edgecolor="white")
    ax.axvline(med_rate, color=NAVY, linestyle="--", linewidth=1.5,
               label=f"median {med_rate:.1f}")
    # every bar carries its rate and both inputs, so the rate can be checked
    top_rate = max(values)
    for i, (dept, budget, n, rate) in enumerate(rates[::-1]):
        ax.text(rate + top_rate * 0.015, i,
                f"{rate:.1f}   ({n:,} questions · ₹{budget:,.0f} crore)",
                va="center", fontsize=8, color=GRAY70, zorder=6,
                bbox=dict(facecolor="white", alpha=0.9, edgecolor="none", pad=0.8))
    ax.set_xlim(0, top_rate * 1.45)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    style(ax, xlabel="Questions asked per ₹100 crore of budget allocation "
                     "(2025–26 allocation)")
    ax.tick_params(axis="y", labelsize=9)
    ax.set_ylim(-0.7, len(rates) - 0.3)
    most, least = rates[0], rates[-1]
    ax.set_title(f"{most[0].replace(' Department', '')} is asked {most[3] / least[3]:.0f}× "
                 f"more per rupee than {least[0].replace(' Department', '')} — "
                 f"which holds the largest budget (₹{least[1]:,.0f} crore) and "
                 f"{least[2]:,} questions",
                 fontsize=13, color=NAVY, pad=12)
    save(fig, "18-scrutiny-intensity", "Scrutiny vs resources", "Pillar 1",
         f"Rate = questions (2021–2026) ÷ budget allocation (2025–26), ×100; "
         f"{len(rates)} departments with at least 5 questions; median "
         f"{med_rate:.1f} questions per ₹100 crore. Navy = at or above the "
         "median, gold = below; sign is also carried by bar length and by the "
         "printed value, never by colour alone. Every bar shows its rate and "
         "both inputs. Limitation: one budget year against a five-year "
         "question count, so this compares *levels*, not trends. "
         "Sources: DEPT_BUDGET, CSV.")

    # ── 19. Opposition intensity by session ──
    bbs = layers["layer3_demands"]["bloc_by_session"]
    blabels = list(bbs)
    ruling = [bbs[s]["counts"]["Ruling"] for s in blabels]
    opposition = [bbs[s]["counts"]["Opposition"] for s in blabels]
    unknown = [bbs[s]["counts"]["Unknown"] for s in blabels]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(slabels, ruling, label="Ruling", color=NAVY, edgecolor="white")
    ax.bar(slabels, opposition, bottom=ruling, label="Opposition", color=GOLD, edgecolor="white")
    ax.bar(slabels, unknown, bottom=np.array(ruling) + np.array(opposition),
           label="Unknown", color=GRAY40, edgecolor="white")
    # Same rule as every other stacked column chart: segments big enough to
    # hold text are labelled inside; the bloc share rides above the column.
    opp_stack = [ruling, opposition, unknown]
    opp_colors = [NAVY, GOLD, GRAY40]
    label_stacked(ax, range(len(blabels)), opp_stack,
                  [r + o + u for r, o, u in zip(ruling, opposition, unknown)],
                  ["Ruling", "Opposition", "Unknown"], opp_colors)
    # Headroom before the labels, so the tallest column's share cannot run
    # into the title.
    ax.set_ylim(0, max(r + o + u for r, o, u in zip(ruling, opposition, unknown)) * 1.16)
    for i, s in enumerate(blabels):
        pct = bbs[s]["opposition_pct"]
        ax.text(i, ruling[i] + opposition[i] + unknown[i] + 6, f"{pct:.0f}% opp",
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
         "Asker bloc from MLA party records; counts only, no effectiveness "
         f"claims. Segments >= {LABEL_MIN_SEGMENT_PCT:g}% of a column are "
         "labelled; the opposition share sits above each column. "
         "Source: layer3_demands.json.")

    # ── 20. Execution stages by department ──
    stage_order = ["None evidenced", "Concept/Proposal", "Administrative Processing",
                   "Sanction/Funding", "Approval", "Procurement", "Execution/Award",
                   "Implementation", "Completion"]
    stage_depts = [d for d, _ in
                   sorted(((d, v) for d, v in dept_summary.items()),
                          key=lambda kv: -kv[1]["n_replies"])[:10]]
    # Ordered variable (delivery stage progresses) -> ordered single-hue
    # ramp; "no stage evidenced" is the absence of evidence, so it wears
    # neutral grey. The previous 9-hue rainbow was neither ordered nor
    # colorblind-safe (deck: Mapping + Color).
    stage_colors = {"None evidenced": GRAY40, "Concept/Proposal": "#DCE6F2",
                    "Administrative Processing": "#B8CCE4", "Sanction/Funding": "#94AFCF",
                    "Approval": "#6F92BA", "Procurement": "#4A75A5",
                    "Execution/Award": "#2A5890", "Implementation": TEAL,
                    "Completion": "#146B4B"}
    fig, ax = plt.subplots(figsize=(12, 7))
    bottom = np.zeros(len(stage_depts))
    # Mute non-essential series: only the stages carrying real mass get
    # their own band; the thin tail is summed into one honest "Other
    # stages" row (deck: Density - appropriate aggregation).
    _tot = overall["stage_distribution"]
    _n_coded = overall["n_coded"] or 1
    _major = sorted((s for s in stage_order if s != "None evidenced"),
                    key=lambda s: _tot.get(s, 0), reverse=True)[:3]
    _major = [s for s in _major if _tot.get(s, 0) / _n_coded >= 0.02]
    _minor = [s for s in stage_order if s != "None evidenced" and s not in _major]
    bands = ["None evidenced"] + _major + ["Other stages"]
    band_color = {**{s: stage_colors[s] for s in ["None evidenced"] + _major},
                  "Other stages": "#C9D4E0"}
    stage_pcts, stage_totals = {}, []
    for stage in bands:
        if stage == "Other stages":
            vals = np.array([sum(dept_summary[d]["stage_distribution"].get(s, 0)
                                for s in _minor) for d in stage_depts], dtype=float)
        else:
            vals = np.array([dept_summary[d]["stage_distribution"].get(stage, 0)
                             for d in stage_depts], dtype=float)
        totals = np.array([dept_summary[d]["n_replies"] for d in stage_depts], dtype=float)
        pcts = np.divide(vals, totals, out=np.zeros_like(vals, dtype=float),
                         where=totals > 0) * 100
        label = (f"Other stages ({len(_minor)}: "
                 f"{', '.join(s.split('/')[0] for s in _minor)})" if stage == "Other stages"
                 else stage)
        ax.bar([shorten(d, width=26, placeholder="…") for d in stage_depts], pcts,
               bottom=bottom, label=label, color=band_color[stage], edgecolor="white")
        stage_pcts[stage] = pcts
        stage_totals.append(totals)
        bottom += pcts
    label_stacked(ax, range(len(stage_depts)), list(stage_pcts.values()),
                  stage_totals[0], bands,
                  [band_color[b] for b in bands])
    ax.legend(frameon=False, fontsize=8, ncol=2,
              loc="upper center", bbox_to_anchor=(0.5, -0.18))
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
         f"n={overall['n_coded']} coded replies. Segments >= "
         f"{LABEL_MIN_SEGMENT_PCT:g}% of a column are labelled; smaller bands "
         "are left to the axis.")

    # ── 21. Latency histogram ──
    lats_all = [x["latency"] for x in _records if x["latency"] is not None]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    if lats_all:
        bins = list(range(0, min(max(lats_all) + 5, 125), 5))
        counts, _, _ = ax.hist(lats_all, bins=bins, color=NAVY, edgecolor="white",
                               zorder=3)
        # Label the bins that carry the mass; the thin tail is read off the
        # axis (stated in the caption). Headroom + halo so a bin count is
        # never crossed by the median rule.
        tallest = counts.max() if len(counts) else 0
        if tallest:
            ax.set_ylim(0, tallest * 1.18)
        halo = dict(facecolor="white", alpha=0.9, edgecolor="none", pad=0.8)
        for left, c in zip(bins[:-1], counts):
            if tallest and c / tallest >= 0.10:
                ax.text(left + 2.5, c, f"{int(c)}", ha="center", va="bottom",
                        fontsize=8, color=GRAY70, bbox=halo, zorder=6)
        med = statistics.median(lats_all)
        ax.axvline(med, color=RED, linestyle="--", linewidth=2, zorder=2,
                   label=f"median {med} days")
        ax.axvline(30, color=AMBER, linestyle=":", linewidth=2, zorder=2,
                   label="30-day mark")
        ax.legend(frameon=False, fontsize=9)
        over30 = 100 * sum(1 for d in lats_all if d > 30) / len(lats_all)
        ax.set_title(f"Median reply time: {med:g} days; "
                     f"{over30:.0f}% take longer than 30 days",
                     fontsize=13, color=NAVY, pad=12)
    else:
        ax.set_title("How long replies take", fontsize=13, color=NAVY, pad=12)
    style(ax, xlabel="Days from submission to reply", ylabel="Replies")
    save(fig, "21-latency", "Reply latency", "Pillar 2",
         "Trustworthy date pairs only; flagged pairs excluded but kept in data. "
         "Bins holding >= 10% of the tallest bin are labelled.")

    (OUT / "manifest.json").write_text(json.dumps(MANIFEST, indent=2), encoding="utf-8")
    print(f"{len(MANIFEST)} charts -> {OUT}")


if __name__ == "__main__":
    main()
