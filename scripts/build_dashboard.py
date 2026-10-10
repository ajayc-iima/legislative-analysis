"""Self-contained HTML dashboard for the Compendium.

Reads output/charts/manifest.json + layer JSONs and writes a single
output/charts/index.html: inline CSS, zero JavaScript, chart SVGs by
relative reference (same folder), summary tables, method notes.
Regenerate any time: python scripts/build_dashboard.py
"""

import html
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))
sys.path.insert(0, str(REPO))

from build_compendium import compute_layer4, load_extracted, pct  # noqa: E402
from legislative_analysis import analysis as base  # noqa: E402
from legislative_analysis.analysis import load as load_rows  # noqa: E402

CHARTS = REPO / "output/charts"
LAYERS = REPO / "output/layers"

CSS = """
:root { --navy:#1A3C6E; --teal:#2A8E9C; --gold:#C9A227; --ink:#222; --mut:#555;
        --line:#E0E0E0; --bg:#FAFAF8; --card:#FFFFFF; }
* { box-sizing:border-box; }
body { font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       color:var(--ink); background:var(--bg); margin:0; line-height:1.55; }
.wrap { max-width:1080px; margin:0 auto; padding:2rem 1.25rem 4rem; }
header.hero { background:linear-gradient(135deg,#1A3C6E 0%,#2A8E9C 100%);
              color:#fff; border-radius:12px; padding:1.8rem 1.6rem; margin-bottom:1rem; }
header.hero h1 { margin:0 0 .4rem; font-size:2rem; }
header.hero p { margin:.2rem 0; color:#DCEBF5; }
header.hero code { background:rgba(255,255,255,.15); color:#fff; }
nav.toc { position:sticky; top:0; z-index:10; background:var(--bg);
          padding:.6rem 0; border-bottom:1px solid var(--line); margin-bottom:1rem; }
nav.toc a { color:var(--navy); text-decoration:none; font-size:.88rem;
            margin-right:1.1rem; font-weight:600; }
nav.toc a:hover { text-decoration:underline; }
.pillar { margin:2.5rem 0 1rem; }
.pillar h2 { color:var(--navy); border-left:6px solid var(--gold);
             padding-left:.6rem; margin-bottom:.25rem; }
.pillar > p { color:var(--mut); margin-top:0; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr));
        gap:1.25rem; }
figure.card { background:var(--card); border:1px solid var(--line);
              border-radius:10px; margin:0; padding:1rem; }
figure.card img { width:100%; height:auto; display:block; }
figure.card h3 { margin:.4rem 0 .3rem; font-size:1.02rem; color:var(--navy); }
figure.card figcaption { font-size:.82rem; color:var(--mut); }
table.data { border-collapse:collapse; width:100%; font-size:.88rem;
             background:var(--card); }
table.data th, table.data td { border:1px solid var(--line); padding:.4rem .6rem;
             text-align:left; }
table.data th { background:var(--navy); color:#fff; }
table.data tr:nth-child(even) td { background:#F4F6F9; }
.kpis { display:flex; flex-wrap:wrap; gap:.75rem; margin:1rem 0; }
.kpi { background:var(--card); border:1px solid var(--line); border-radius:8px;
       padding:.6rem 1rem; min-width:130px; }
.kpi b { display:block; font-size:1.35rem; color:var(--navy); }
.kpi span { font-size:.78rem; color:var(--mut); }
.note { background:#FFF8E6; border:1px solid var(--gold); border-radius:8px;
        padding:.8rem 1rem; font-size:.88rem; }
code { background:#EFF1F4; padding:.1rem .35rem; border-radius:4px; font-size:.85em; }
footer { margin-top:3rem; color:var(--mut); font-size:.82rem;
         border-top:1px solid var(--line); padding-top:1rem; }
.brief { background:var(--card); border:1px solid var(--line); border-radius:10px;
         padding:1rem 1.2rem; margin:0 0 1rem; }
.brief h3 { margin:0 0 .2rem; color:var(--navy); }
.brief .meta { font-size:.82rem; color:var(--mut); margin-bottom:.5rem; }
.brief ul { margin:.3rem 0 .6rem 1.1rem; padding:0; font-size:.9rem; }
.brief li { margin:.15rem 0; }
.tag { display:inline-block; font-size:.75rem; background:#EAF2F8; color:var(--navy);
       border-radius:20px; padding:.05rem .6rem; margin-right:.3rem; }
.gap { display:flex; align-items:center; gap:.6rem; margin:.3rem 0; font-size:.85rem; }
.gap .lbl { width:170px; flex:none; color:var(--mut); }
.gap .bar { flex:1; background:#EDF0F3; border-radius:4px; height:14px; position:relative; }
.gap .fill { background:var(--teal); height:14px; border-radius:4px; }
.gap .fill.hot { background:#C0392B; }
.gap .val { width:90px; flex:none; text-align:right; font-variant-numeric:tabular-nums; }
@media print { body { background:#fff; } figure.card, .brief { break-inside:avoid; } nav.toc { display:none; } }
"""


def esc(value):
    return html.escape(str(value))


def table(headers, rows):
    lines = ["<table class='data'><thead><tr>"]
    lines += [f"<th>{esc(h)}</th>" for h in headers]
    lines += ["</tr></thead><tbody>"]
    for row in rows:
        lines += ["<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>"]
    lines += ["</tbody></table>"]
    return "\n".join(lines)


def _dept_coverage_gap(stats, dept, rows):
    """% of a department's questions with no signed reply (unanswered demand)."""
    from legislative_analysis.codebook import normalize_dept
    n = sum(1 for r in rows if normalize_dept(r.get("Departments")) == dept)
    if not n:
        return 0
    with_reply = sum(1 for r in rows
                    if normalize_dept(r.get("Departments")) == dept
                    and str(r.get("Document_Link") or "").lower().startswith("http"))
    return round(100 * (1 - with_reply / n), 1)


def figures(ids, manifest):
    out = ["<div class='grid'>"]
    by_id = {m["id"]: m for m in manifest}
    for cid in ids:
        m = by_id[cid]
        out.append(
            f"<figure class='card'><h3>{esc(m['title'])}</h3>"
            f"<img src='{esc(m['files'][1])}' alt='{esc(m['title'])}' loading='lazy'>"
            f"<figcaption>{esc(m['caption'])}</figcaption></figure>")
    out.append("</div>")
    return "\n".join(out)


def main():
    manifest = json.loads((CHARTS / "manifest.json").read_text(encoding="utf-8"))
    stats = json.loads((REPO / "output/stats.json").read_text(encoding="utf-8"))
    layers = {}
    for name in ("layer1_themes", "layer2_geography", "layer3_demands",
                 "layer5_resolution", "layer6_trends"):
        layers[name] = json.loads((LAYERS / f"{name}.json").read_text(encoding="utf-8"))
    ov = stats["overview"]
    total = ov["questions"]
    rows = base.scope_rows(load_rows(str(REPO / "data/dl_questions_raw.csv")))
    extracted = load_extracted()
    overall, dept_summary, _records = compute_layer4(rows, extracted)
    try:
        briefs = json.loads((REPO / "output/anticipation/dept_briefs.json").read_text(encoding="utf-8"))
    except OSError:
        briefs = {}

    themes = sorted(layers["layer1_themes"]["theme_counts"].items(), key=lambda kv: -kv[1])
    demands = sorted(layers["layer3_demands"]["demand_counts"].items(), key=lambda kv: -kv[1])
    emerging = layers["layer6_trends"]["emerging_issues"]
    resolution = layers["layer5_resolution"]
    trends = layers["layer6_trends"]
    t = overall.get("timeliness", {})

    L = []
    L.append("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
             "<meta name='viewport' content='width=device-width,initial-scale=1'>"
             "<title>Legislative Oversight in Meghalaya — Dashboard</title>"
             f"<style>{CSS}</style></head><body><div class='wrap'>")
    L.append("<header class='hero'><h1>Legislative Oversight in Meghalaya</h1>"
             "<p>Visual companion to the three-pillar Compendium — descriptive evidence only, "
             "no composite scores. Every figure is reproducible from "
             "<code>data/dl_questions_raw.csv</code> and <code>data/extracted/extracted.jsonl</code>.</p>"
             f"<p>Generated {datetime.now():%Y-%m-%d %H:%M} · "
             f"{total:,} questions in scope · {len(stats['sessions'])} sessions (2021–2026) · "
             f"{ov['departments']} departments · {ov['mlas']} MLAs · "
             f"replies OCR-extracted: {len(extracted):,}/2,246</p></header>")
    L.append("<nav class='toc'><a href='#p1'>Attention</a><a href='#p2'>Oversight quality</a>"
             "<a href='#p3'>Persistent challenges</a><a href='#anticipate'>Anticipate &amp; prepare</a>"
             "<a href='#gaps'>Preparedness gaps</a><a href='#methods'>Methods</a></nav>")

    L.append("<div class='kpis'>")
    for value, label in [
            (f"{total:,}", "questions"),
            (f"{ov['reply_coverage']}%", "reply coverage"),
            (len(resolution.get("families", {})), "recurring subjects"),
            (len(emerging), "emerging issues"),
            (f"{t.get('median_days', '—')}", "median reply latency (days)"),
            (f"{overall.get('boilerplate_pct', 0)}%", "boilerplate replies")]:
        L.append(f"<div class='kpi'><b>{esc(value)}</b><span>{esc(label)}</span></div>")
    L.append("</div>")

    # Pillar 1
    L.append("<section class='pillar' id='p1'><h2>Pillar 1 — Patterns of Legislative Attention</h2>"
             "<p>Which departments, policy domains, places and subjects receive the most attention.</p></section>")
    L.append(figures(["01-dept-attention", "02-dept-session-heatmap", "03-themes",
                      "16-theme-dept-heatmap", "04-districts", "05-recurring-dots",
                      "15-mla-bubble"], manifest))
    L.append("<h3>Policy domains</h3>" + table(
        ["Theme", "Questions", "Share"],
        [[th, n, f"{100 * n / total:.1f}%"] for th, n in themes]))

    # Pillar 2
    L.append("<section class='pillar' id='p2'><h2>Pillar 2 — Dynamics and Quality of Oversight</h2>"
             "<p>What is demanded, how attention moves over time, and how departments respond.</p></section>")
    L.append(figures(["06-demand-by-dept", "07-session-trend", "08-dept-slopes",
                      "14-starred", "11-coverage", "09-substantiveness",
                      "10-assurance-evasion"], manifest))
    L.append("<h3>Demand mix</h3>" + table(
        ["Demand type", "Questions", "Share"],
        [[d, n, f"{100 * n / total:.1f}%"] for d, n in demands]))

    # Pillar 3
    L.append("<section class='pillar' id='p3'><h2>Pillar 3 — Persistent and Emerging Challenges</h2>"
             "<p>What recurs, what is stalled, and what is emerging.</p></section>")
    L.append(figures(["12-resolution", "13-emerging"], manifest))
    L.append("<h3>Emerging issues watchlist</h3>")
    if emerging:
        L.append(table(["Subject", "First seen", "Occurrences", "Askers", "Departments"],
                       [[e["subject"], e["first_session"], e["occurrences"],
                         len(e["askers"]), ", ".join(e["departments"][:2])]
                        for e in emerging]))
    else:
        L.append("<p>No emerging issues meet the watchlist criteria.</p>")

    stalled = resolution.get("stalled_subjects", [])
    L.append("<h3>Stalled issues (recurring, no progress language in latest reply)</h3>")
    if stalled:
        L.append(table(["Subject", "Occurrences", "Sessions", "Departments"],
                       [[f["subject"], f["occurrences"], len(f["sessions"]),
                         ", ".join(f["departments"][:2])] for f in stalled[:20]]))
    else:
        L.append("<p>None coded as stalled yet — trajectories resolve as OCR replies accrue.</p>")

    # Anticipation briefs
    L.append("<section class='pillar' id='anticipate'><h2>Anticipate &amp; prepare by department</h2>"
             "<p>Likely next-session questions and evidence-linked preparation steps. "
             "Full briefs for all departments: <code>output/anticipation/dept_briefs.json</code>.</p></section>")
    if briefs:
        for dept in sorted(briefs, key=lambda d: -briefs[d]["questions"])[:8]:
            b = briefs[dept]
            L.append(f"<div class='brief'><h3>{esc(dept)}</h3>"
                     f"<div class='meta'>{b['questions']} questions ({b['share_pct']}%) · "
                     f"{b['sessions_active']} sessions · coverage {b['reply_coverage_pct']}% · "
                     f"trend {b['trend_delta_per_session']:+.2f}/session · "
                     f"{b['recurring_subjects']} recurring · {b['replies_coded']} replies coded</div>")
            if b["anticipate"]:
                L.append("<b>Anticipate:</b><ul>" + "".join(
                    f"<li>{esc(a['subject'])} <span class='tag'>{esc(a['why'])}</span></li>"
                    for a in b["anticipate"][:6]) + "</ul>")
            if b["prepare"]:
                L.append("<b>Prepare:</b><ul>" + "".join(
                    f"<li>{esc(p)}</li>" for p in b["prepare"]) + "</ul>")
            L.append("</div>")
    else:
        L.append("<p>Briefs not yet built — run <code>python scripts/build_anticipation.py</code>.</p>")

    # Preparedness gap profiles
    L.append("<section class='pillar' id='gaps'><h2>Preparedness gap profiles</h2>"
             "<p>The gap is a profile, not a score: seven separately-reported dimensions per "
             "department. Wider bars = further from answer-ready. Red marks the worst value per row.</p></section>")
    gap_depts = [d for d in sorted(dept_summary, key=lambda d: -dept_summary[d]["n_replies"])[:10]
                 if dept_summary[d]["n_replies"] >= 5]
    if gap_depts:
        for dept in gap_depts:
            v = dept_summary[dept]
            n = v["n_replies"]
            low_spec = v["specificity"].get("low", 0)
            dims = [
                ("Unanswered demand", _dept_coverage_gap(stats, dept, rows), "%"),
                ("Boilerplate replies", v["boilerplate_pct"], "%"),
                ("Contradictory replies", v["contradiction_pct"], "%"),
                ("Thin-evidence replies", round(100 * low_spec / n, 1) if n else 0, "%"),
                ("Replies without timeline", round(100 - v["timeline_pct"], 1), "%"),
                ("Replies without budget", round(100 - v["budget_pct"], 1), "%"),
                ("Median latency", v["latency_median"] if v["latency_median"] is not None else 0, " days"),
            ]
            L.append(f"<div class='brief'><h3>{esc(dept)} <span class='tag'>{n} coded replies</span></h3>")
            for label, val, unit in dims:
                val = val or 0
                L.append(f"<div class='gap'><span class='lbl'>{esc(label)}</span>"
                         f"<span class='bar'><span class='fill' style='width:{min(val, 100):.0f}%'></span></span>"
                         f"<span class='val'>{val}{esc(unit or '')}</span></div>")
            L.append("</div>")
    else:
        L.append("<p>Gap profiles appear once departments have ≥5 coded replies.</p>")

    L.append("<section class='pillar' id='methods'><h2>Methods &amp; limitations</h2></section>")
    L.append("<div class='note'><p><b>Reproducibility.</b> Thematic coding is keyword rules with "
             "department-sector tie-breaks (evidence per row); geography is MLA lookup plus a gazetteer scan; "
             "demand types are Information / Explanation / Action / Accountability; response quality is four "
             "separately-reported dimensions from ported regex registries; recurrence is exact normalized match "
             "across sessions (under-merges paraphrases, never over-merges).</p>"
             "<p><b>Known limits.</b> OCR accuracy is bounded (~0.94/field); flagged date pairs are excluded "
             "from timeliness but kept in the data. MLA-based geography assumes questions concern the asker's "
             "own seat. regenerate everything with "
             "<code>python scripts/run_layers.py &amp;&amp; "
             "python scripts/build_compendium.py &amp;&amp; "
             "python scripts/build_charts.py &amp;&amp; python scripts/build_dashboard.py</code>.</p></div>")

    L.append("<footer>Legislative Analysis · Meghalaya Assembly 10–11 (2018–2026) · "
             "Compendium text: <code>output/compendium/COMPENDIUM.md</code> · "
             "Data: <code>output/layers/*.json</code></footer>")
    L.append("</div></body></html>")

    dest = CHARTS / "index.html"
    dest.write_text("\n".join(L), encoding="utf-8")
    print(f"dashboard -> {dest} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
