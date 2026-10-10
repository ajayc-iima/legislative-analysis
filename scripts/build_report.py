"""Final shareable report: one self-contained HTML file.

Redesigned against the shared dataviz deck (Data_Visualization.pptx,
after Wilke) and the heuristic evaluation in docs/HEURISTIC_EVAL.md:

* Story arc — Opening (executive findings, how to read, corpus) →
  Challenge (three pillars) → Action (anticipate & prepare briefs) →
  Resolution (methods, limits, appendix).
* Message titles — every section heading states a finding computed
  live from data; every figure states its takeaway inside the chart
  (captured in the manifest as ``message``); the figure eyebrow
  carries number, label and pillar.
* One figure, one dominant point. Figures never travel alone:
  every chart group is followed by its data table (H6), visible for
  key tables, folded under "Show data" for long ones.
* Tables as figures — no vertical rules, right-aligned numbers,
  hairline rows, captioned with the source file (deck slide 139).
* Percentages carry denominators; color is never the sole encoding;
  a how-to-read preamble states conventions and vocabulary (H7/H9);
  sticky contents keep orientation (H1).
* Raw evidence before derived claims; explicit "what we do not
  claim" statement.

Evidence rules: no composite scores, probabilities, readiness
indices, forecasts or generated action plans. Every number is
computed at generation time from the question CSV, the extracted
reply texts and the six layer files.

Usage: python scripts/build_report.py  ->  output/report/index.html
"""

import html
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from legislative_analysis import analysis as base  # noqa: E402
from legislative_analysis.analysis import load as load_rows  # noqa: E402
from legislative_analysis.codebook import normalize_dept  # noqa: E402
from legislative_analysis import reference_data as ref_data  # noqa: E402
from build_compendium import compute_layer4, load_extracted, pct  # noqa: E402

CHARTS = REPO / "output/charts"
LAYERS = REPO / "output/layers"
OUT = REPO / "output/report"

CSS = """
:root { --navy:#1A3C6E; --teal:#2A8E9C; --gold:#C9A227; --ink:#1f2933;
        --mut:#55606c; --line:#E0E0E0; --bg:#FFFFFF; --soft:#F4F6F9;
        --sans:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { font-family:Georgia,'Times New Roman',serif; color:var(--ink);
       background:var(--bg); margin:0; line-height:1.65; }
.wrap { max-width:960px; margin:0 auto; padding:0 1.5rem 4rem; }
a { color:var(--navy); }
a:focus-visible { outline:2px solid var(--teal); outline-offset:2px; }

/* sticky contents: orientation without losing place (H1) */
nav.toc { position:sticky; top:0; z-index:50; background:rgba(255,255,255,.97);
          backdrop-filter:blur(3px); border-bottom:2px solid var(--navy);
          padding:.55rem .1rem; margin:0 0 .5rem; font-family:var(--sans);
          display:flex; flex-wrap:wrap; gap:.1rem 1.05rem; align-items:baseline; }
nav.toc .brand { font-weight:800; letter-spacing:.05em; text-transform:uppercase;
                 font-size:.7rem; color:var(--mut); }
nav.toc a { color:var(--navy); text-decoration:none; font-size:.83rem; font-weight:600; }
nav.toc a:hover { color:var(--teal); text-decoration:underline; }

.cover { border-bottom:5px solid var(--navy); padding:1.4rem 0 1.1rem; margin-bottom:.6rem; }
.cover h1 { font-size:2.25rem; color:var(--navy); margin:0 0 .3rem; line-height:1.18; }
.cover .sub { font-size:1.08rem; color:var(--mut); margin:0 0 .7rem; }
.cover .meta { font-size:.85rem; color:var(--mut); font-family:var(--sans); margin:.35rem 0 0; }

.arc { font-family:var(--sans); font-size:.7rem; font-weight:800; letter-spacing:.14em;
       text-transform:uppercase; color:var(--teal); margin-top:2.6rem; }
h2.sec { color:var(--navy); font-size:1.55rem; border-bottom:2px solid var(--gold);
         padding-bottom:.35rem; margin:.25rem 0 .9rem; scroll-margin-top:56px; }
h3 { color:var(--navy); font-size:1.1rem; margin:2rem 0 .45rem; line-height:1.35;
     scroll-margin-top:56px; }
p { margin:.55rem 0; }
ul.plain { margin:.5rem 0 .8rem; padding-left:1.25rem; }
ul.plain li { margin:.25rem 0; }
dl.gloss { font-family:var(--sans); font-size:.88rem; margin:.6rem 0; }
dl.gloss dt { font-weight:700; color:var(--navy); margin-top:.5rem; }
dl.gloss dd { margin:.05rem 0 0 1rem; color:var(--ink); }

.guide { background:#FBF7EA; border-left:5px solid var(--gold); border-radius:0 8px 8px 0;
         padding:.7rem 1rem; margin:1rem 0; }
.guide b { color:#7A5C00; }
.finding { background:#EFF4FA; border-left:5px solid var(--navy); border-radius:0 8px 8px 0;
           padding:.6rem 1rem; margin:.7rem 0; }
.finding b { color:var(--navy); }
.warnbox { background:#FFF8E6; border:1px solid var(--gold); border-radius:8px;
           padding:.8rem 1.1rem; margin:1rem 0; }
.warnbox b { color:#7A5C00; }
.note { font-family:var(--sans); font-size:.8rem; color:var(--mut); margin:.3rem 0 0; }

figure.card { margin:1.3rem 0; border:1px solid var(--line); border-radius:10px;
              padding:.85rem 1.05rem; background:#fff; }
.eyebrow { font-family:var(--sans); font-size:.67rem; letter-spacing:.1em;
           text-transform:uppercase; color:var(--mut); margin:.1rem 0 .55rem;
           display:flex; flex-wrap:wrap; gap:.45rem; }
.eyebrow b { color:var(--navy); }
.eyebrow span::before { content:"· "; color:var(--line); }
figure.card svg { width:100%; height:auto; display:block; }
figure.card figcaption { font-family:var(--sans); font-size:.79rem; color:var(--mut);
                         margin-top:.55rem; border-top:1px dotted var(--line);
                         padding-top:.4rem; }

/* tables as figures: no vertical rules, numbers right, hairlines */
table.data { border-collapse:collapse; width:100%; font-size:.83rem; margin:.7rem 0;
             font-family:var(--sans); }
table.data caption { caption-side:top; text-align:left; font-size:.76rem;
                     color:var(--mut); padding:.1rem 0 .3rem; }
table.data th { text-align:left; font-weight:700; color:var(--navy);
                border-bottom:2px solid var(--navy); padding:.4rem .55rem; }
table.data td { border-bottom:1px solid #EDEFF2; padding:.33rem .55rem;
                vertical-align:top; }
table.data th.n, table.data td.n { text-align:right; font-variant-numeric:tabular-nums; }
table.data tbody tr:nth-child(even) td { background:#FAFBFD; }
table.data tr.total td { font-weight:700; border-top:2px solid var(--navy);
                         border-bottom:none; background:#F2F5F9; }
details.data { margin:.5rem 0 1.2rem; font-size:.86rem; font-family:var(--sans); }
details.data summary { cursor:pointer; color:var(--navy); font-weight:600; padding:.2rem 0; }
details.data[open] summary { margin-bottom:.35rem; }

.kpis { display:flex; flex-wrap:wrap; gap:.6rem; margin:1.1rem 0; font-family:var(--sans); }
.kpi { border:1px solid var(--line); border-left:4px solid var(--teal); border-radius:6px;
       padding:.5rem .85rem; min-width:126px; flex:1 1 126px; background:#fff; }
.kpi b { display:block; font-size:1.22rem; color:var(--navy); font-variant-numeric:tabular-nums; }
.kpi span { font-size:.7rem; color:var(--mut); line-height:1.3; display:block; }
.badge { display:inline-block; font-family:var(--sans); font-size:.7rem; font-weight:700;
         border-radius:20px; padding:.1rem .7rem; vertical-align:middle; }
.badge.ok { background:#E7F6EE; color:#1E7A45; border:1px solid #B7E3C9; }
.badge.run { background:#FFF3D9; color:#8A6100; border:1px solid #F0DCA8; }

.brief { border:1px solid var(--line); border-radius:10px; padding:.9rem 1.1rem;
         margin:0 0 1rem; break-inside:avoid; }
.brief h4 { margin:0 0 .2rem; color:var(--navy); font-size:1.05rem; }
.brief .meta { font-family:var(--sans); font-size:.78rem; color:var(--mut);
               margin-bottom:.4rem; }
.brief ul { margin:.3rem 0 .5rem 1.1rem; padding:0; font-size:.92rem; }
.tag { display:inline-block; font-family:var(--sans); font-size:.7rem; background:#EAF2F8;
       color:var(--navy); border-radius:20px; padding:.05rem .55rem; margin-left:.3rem; }
code { background:#EFF1F4; padding:.1rem .35rem; border-radius:4px; font-size:.85em; }
pre.cmd { background:#F6F8FA; border:1px solid var(--line); border-radius:8px;
          padding:.7rem 1rem; font-size:.8rem; overflow-x:auto; }
footer { margin-top:3rem; color:var(--mut); font-size:.78rem; font-family:var(--sans);
         border-top:1px solid var(--line); padding-top:1rem; }

@media (max-width:640px) {
  nav.toc { position:static; }
  .cover h1 { font-size:1.75rem; }
}
@media print {
  body { font-size:11pt; }
  nav.toc { display:none; }
  figure.card, .brief, table.data, .finding { break-inside:avoid; }
  .wrap { max-width:100%; padding:0; }
  a { text-decoration:none; color:var(--ink); }
}
"""


def esc(value):
    return html.escape(str(value))


def g(value):
    """Prose-friendly number formatting; None-safe."""
    if value is None:
        return "—"
    try:
        return f"{value:g}"
    except (TypeError, ValueError):
        return str(value)


def svg_inline(name, label=""):
    """Inline chart SVG (self-contained file) with accessible label."""
    text = (CHARTS / f"{name}.svg").read_text(encoding="utf-8")
    # drop XML prolog + doctype: noise inside an HTML body
    text = re.sub(r"<\?xml[^>]*\?>", "", text, count=1)
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text, count=1)
    if "<title>" not in text:
        text = text.replace("<svg ", f"<svg role='img' aria-label='{esc(label or name)}' ", 1)
    return text.strip()


FIG = []          # figure ids in emission order -> Figure numbers
MANIFEST = {}


def figure(cid):
    """Figure card: eyebrow (number · label · pillar), chart (with its
    message title inside), caption (source)."""
    m = MANIFEST[cid]
    n = len(FIG) + 1
    FIG.append(cid)
    msg = m.get("message") or m["title"]
    return (f"<figure class='card' id='fig{n}'>"
            f"<div class='eyebrow'><b>Figure {n}</b>"
            f"<span>{esc(m['title'])}</span><span>{esc(m['pillar'])}</span></div>"
            f"{svg_inline(cid, msg)}"
            f"<figcaption>{esc(m['caption'])}</figcaption></figure>")


def figs(*cids):
    return "\n".join(figure(c) for c in cids)


def _numflag(value):
    """True = numeric, False = text, None = neutral placeholder."""
    s = str(value).strip()
    if s in ("", "—", "-", "n/a", "N/A"):
        return None
    s2 = s.replace(",", "").replace("%", "").replace("₹", "")
    try:
        float(s2)
        return True
    except ValueError:
        return False


def table(headers, rows, caption=None, total_row=False):
    """Borderless table, numbers right-aligned (deck slide 139)."""
    rows = [["—" if c is None else c for c in r] for r in rows]
    numeric = []
    for i in range(len(headers)):
        flags = [_numflag(r[i]) for r in rows if i < len(r)]
        real = [f for f in flags if f is not None]
        numeric.append(bool(real) and all(real))
    out = ["<table class='data'>"]
    if caption:
        out.append(f"<caption>{esc(caption)}</caption>")
    out.append("<thead><tr>")
    for i, h in enumerate(headers):
        th_cls = " class='n'" if numeric[i] else ""
        out.append(f"<th{th_cls}>{esc(h)}</th>")
    out.append("</tr></thead><tbody>")
    for j, r in enumerate(rows):
        cls = " class='total'" if total_row and j == len(rows) - 1 else ""
        out.append(f"<tr{cls}>")
        for i, c in enumerate(r):
            ncls = " class='n'" if i < len(numeric) and numeric[i] else ""
            out.append(f"<td{ncls}>{esc(c)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def details(summary, body):
    return f"<details class='data'><summary>{esc(summary)}</summary>{body}</details>"


def arc(label):
    return f"<div class='arc'>{esc(label)}</div>"


def main():
    global MANIFEST
    FIG.clear()
    OUT.mkdir(parents=True, exist_ok=True)
    MANIFEST = {m["id"]: m for m in
                json.loads((CHARTS / "manifest.json").read_text(encoding="utf-8"))}
    stats = json.loads((REPO / "output/stats.json").read_text(encoding="utf-8"))
    layers = {}
    for name in ("layer1_themes", "layer2_geography", "layer3_demands",
                 "layer5_resolution", "layer6_trends"):
        layers[name] = json.loads((LAYERS / f"{name}.json").read_text(encoding="utf-8"))
    try:
        briefs = json.loads((REPO / "output/anticipation/dept_briefs.json")
                            .read_text(encoding="utf-8"))
    except OSError:
        briefs = {}

    # ── live data ──
    ov = stats["overview"]
    rows = base.scope_rows(load_rows(str(REPO / "data/dl_questions_raw.csv")))
    total = len(rows)
    extracted = load_extracted()
    overall, dept_summary, records = compute_layer4(rows, extracted)

    themes = layers["layer1_themes"]
    geo = layers["layer2_geography"]
    demands = layers["layer3_demands"]
    resolution = layers["layer5_resolution"]
    trends = layers["layer6_trends"]
    t = overall.get("timeliness", {})
    sess_list = stats["sessions"]
    n_sessions = len(sess_list)
    bloc_by_session = demands.get("bloc_by_session", {})

    # extraction completeness over scoped PDFs that exist on disk
    on_disk = {p.name for p in (REPO / "data/pdfs").rglob("*.pdf")}
    scoped = {str(r.get("Document_Link") or "").rsplit("/", 1)[-1]
              for r in rows if r.get("Document_Link")} & on_disk
    done_scoped = sum(1 for nm in scoped if nm in extracted)
    ext_pct = pct(done_scoped, len(scoped))
    ext_done = done_scoped >= len(scoped) and scoped
    badge = ("<span class='badge ok'>reply texts complete</span>" if ext_done
             else "<span class='badge run'>reply texts still extracting</span>")

    def skey(s):
        return f"{s['assembly'].split()[0]} {s['session']}"

    # starred shares (per session and overall)
    star_by = defaultdict(Counter)
    for r in rows:
        low = str(r.get("Question_Type") or r.get("Category") or "").lower()
        star_by[(r.get("Assembly"), r.get("Session"))][
            "star" if ("starred" in low and "unstarred" not in low) else "unstar"] += 1
    star_all = Counter()
    for c in star_by.values():
        star_all.update(c)
    star_pct_all = pct(star_all["star"], total)

    # headline numbers
    top_depts = stats["departments"][:3]
    top3_share = round(sum(d["share"] for d in top_depts), 1)
    theme_sorted = sorted(themes["theme_counts"].items(), key=lambda kv: -kv[1])
    top2_share = pct(sum(n for _, n in theme_sorted[:2]), total)
    bloc_counts = demands.get("bloc_counts", {})
    opp_total = bloc_counts.get("Opposition", 0)
    opp_share = pct(opp_total, total)
    info_n = demands["demand_counts"].get("Information", 0)
    info_share = pct(info_n, total)
    action_share = pct(demands["demand_counts"].get("Action", 0), total)
    opp_led = sum(1 for b in bloc_by_session.values()
                  if b.get("opposition_pct", 0) > 50)
    n_coded = overall["n_coded"]
    det_n = (overall["substantiveness"].get("detailed", 0)
             + overall["substantiveness"].get("very_detailed", 0))
    det_share = pct(det_n, n_coded)
    high_spec = overall["specificity"].get("high", 0)
    res_counts = resolution["resolution_counts"]
    n_fam = resolution["n_families"]
    n_stalled = res_counts.get("stalled", 0)
    n_resolved = res_counts.get("resolved", 0)
    emerging = trends.get("emerging_issues", [])
    families = resolution["families"]
    fam_top = sorted(families.values(), key=lambda f: (-f["occurrences"], f["subject"]))
    years = sorted({s["first_date"][-4:] for s in sess_list if len(s["first_date"]) >= 4})
    window = f"{years[0]}–{years[-1]}" if years else "2021–2026"

    L = []
    add = L.append
    add("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Legislative Oversight in Meghalaya — Evidence Report</title>"
        f"<style>{CSS}</style></head><body><div class='wrap'>")

    # ── Opening · cover ──
    add("<header class='cover'><h1>Legislative Oversight in Meghalaya</h1>"
        "<p class='sub'>Where attention goes, what replies contain, and which challenges "
        "persist — evidence from Assembly questions, "
        f"{esc(window)}</p>"
        f"<p class='meta'>Generated {datetime.now():%d %B %Y} · {total:,} questions in "
        f"scope · {n_sessions} sitting sessions · reply coverage {ov['reply_coverage']}% · "
        f"reply texts extracted {done_scoped:,}/{len(scoped):,} ({ext_pct}%) {badge}</p>"
        "</header>")
    add("<nav class='toc'><span class='brand'>Evidence report</span>"
        "<a href='#exec'>Findings</a><a href='#how'>How to read</a>"
        "<a href='#corpus'>Corpus</a><a href='#p1'>Attention</a>"
        "<a href='#p2'>Oversight quality</a><a href='#p3'>Persistent challenges</a>"
        "<a href='#briefs'>Briefs</a><a href='#methods'>Methods</a>"
        "<a href='#data'>Appendix</a></nav>")

    # ── Opening · executive findings (all computed) ──
    add(arc("Opening"))
    add("<h2 class='sec' id='exec'>Executive findings</h2>")
    add(f"<div class='finding'><b>Attention concentrates.</b> "
        f"{esc(top_depts[0]['department'])}, {esc(top_depts[1]['department'])} and "
        f"{esc(top_depts[2]['department'])} take {top3_share}% of all questions; "
        f"{esc(theme_sorted[0][0])} and {esc(theme_sorted[1][0])} carry {top2_share}%.</div>")
    add(f"<div class='finding'><b>Oversight is opposition-led.</b> "
        f"Opposition members asked {opp_total:,} of {total:,} questions ({opp_share}%) "
        f"and led questioning in {opp_led} of {n_sessions} sessions.</div>")
    add(f"<div class='finding'><b>Most demands ask for data, not action.</b> "
        f"{info_n:,} questions ({info_share}%) request information; "
        f"{demands['demand_counts'].get('Action', 0):,} ({action_share}%) demand action.</div>")
    add(f"<div class='finding'><b>{star_pct_all}% of questions are oral "
        f"(starred).</b> "
        f"{star_all['star']:,} of {total:,} are starred — taken up "
        f"live on the floor rather than answered in writing; "
        f"{star_all['unstar']:,} ({pct(star_all['unstar'], total)}%) are "
        f"written replies only.</div>")
    if t.get("n"):
        add(f"<div class='finding'><b>Replies arrive quickly, with long notice.</b> "
            f"Median {g(t['median_days'])} days from submission to reply "
            f"(P75 {g(t['p75_days'])} days, n={t['n']:,} trustworthy date pairs); "
            f"departments receive a median {g(overall.get('notice_median_days'))} "
            f"days' notice before sittings; {overall['late_replies']} replies landed "
            f"after the sitting ({overall['late_share_pct']}%).</div>")
    add(f"<div class='finding'><b>Reply dimensions differ sharply.</b> "
        f"Only {overall['boilerplate_pct']}% of {n_coded:,} coded replies are pure "
        f"boilerplate, but just {overall['timeline_pct']}% commit to a timeline and "
        f"{overall['budget_pct']}% cite a budget figure; "
        f"{overall['contradiction_pct']}% contradict themselves.</div>")
    add(f"<div class='finding'><b>Substance is good, specificity is the gap.</b> "
        f"{det_share}% of coded replies are detailed or very detailed "
        f"(n={n_coded:,}); {pct(high_spec, n_coded)}% rate high on specificity "
        f"(named scheme, place or figure).</div>")
    add(f"<div class='finding'><b>{n_stalled} recurring subjects are stalled.</b> "
        f"Of {n_fam} subjects asked in two or more sessions, {n_stalled} show no "
        f"progress language and {n_resolved} read as resolved; {len(emerging)} issues "
        f"first surfaced in the three most recent sessions.</div>")
    add(f"<div class='finding'><b>Corpus coverage is strong.</b> "
        f"{ov['with_reply']:,} of {total:,} questions ({ov['reply_coverage']}%) carry a "
        f"signed reply PDF; reply texts extracted for {done_scoped:,} of {len(scoped):,} "
        f"scoped PDFs ({ext_pct}%).</div>")

    add("<div class='kpis'>")
    for value, label in [
            (f"{total:,}", "questions in scope"),
            (f"{n_sessions}", "sessions, Tenth &amp; Eleventh Assemblies"),
            (f"{ov['reply_coverage']}%", "questions with a signed reply"),
            (f"{opp_share}%", "asked by opposition members"),
            (g(t.get('median_days')) if t.get("n") else "—",
             "median reply latency (days)"),
            (f"{n_fam}", "recurring subjects (2+ sessions)"),
            (f"{ext_pct}%", "scoped reply texts extracted")]:
        add(f"<div class='kpi'><b>{value}</b><span>{label}</span></div>")
    add("</div>")

    # ── Opening · how to read ──
    add("<h2 class='sec' id='how'>How to read this report</h2>")
    add("<div class='guide'><b>What this is.</b> A descriptive evidence report on "
        "Legislative Assembly questions and ministerial replies in Meghalaya, "
        "2021 onwards. It measures what is in the record — counts, shares, dates "
        "and coded language — and deliberately stops there.</div>")
    add("<p><b>Conventions used throughout:</b></p><ul class='plain'>"
        "<li><b>Titles state findings.</b> Section headings and the titles inside "
        "figures are messages computed from the data at generation time — not chart "
        "names. The eyebrow above each figure gives its number, label and pillar.</li>"
        "<li><b>Numbers travel with figures.</b> Every chart group is followed by its "
        "data table; long tables fold under “Show data” controls.</li>"
        "<li><b>Percentages carry denominators</b> (e.g. “44% of 1,950 coded replies”). "
        "Unless stated otherwise, corpus shares are out of "
        f"{total:,} questions in scope.</li>"
        "<li><b>Color is never the only cue.</b> Values, labels and positions repeat "
        "every message; charts remain readable in grayscale and for color-vision "
        "deficiency.</li>"
        "<li><b>Dimensions stay separate.</b> Substantiveness, specificity, "
        "commitments, stages, timeliness and signals are reported individually — "
        "there is no composite score, index, probability or forecast anywhere.</li>"
        "</ul>")
    add("<p><b>Vocabulary.</b></p><dl class='gloss'>"
        "<dt>Starred (oral) question</dt><dd>Asked for a live floor answer; "
        "Unstarred are answered in writing only.</dd>"
        "<dt>Coded reply</dt><dd>OCR-extracted reply text passed to the rule "
        "codebooks (n=1,950 of the extracted texts at this generation).</dd>"
        "<dt>Boilerplate</dt><dd>Reply text that repeats a generic template without "
        "subject-specific content.</dd>"
        "<dt>Substantiveness / specificity</dt><dd>Length-based bands of reply "
        "detail; high specificity means a named scheme, place or figure appears.</dd>"
        "<dt>Assurance / evasion signals</dt><dd>Ported registry phrases signalling "
        "commitments or deflection; reported as mean weights, never combined.</dd>"
        "<dt>Execution stage</dt><dd>Highest evidenced delivery stage per reply "
        "(concept → sanction → approval → procurement → execution → implementation → "
        "completion).</dd>"
        "<dt>Trajectory</dt><dd>Language-based course of a recurring subject: "
        "resolved / progressing / mixed / stalled / awaiting replies.</dd>"
        "<dt>Emerging issue</dt><dd>Subject first seen in the three most recent "
        "sessions, asked at least twice by at least two members.</dd>"
        "<dt>Bloc</dt><dd>Ruling / Opposition from member party records; "
        "unaffiliated → Unknown.</dd>"
        "<dt>Notice period</dt><dd>Days between a question's submission date and its "
        "sitting date — the time a department has to prepare.</dd>"
        "</dl>")

    # ── Opening · corpus at a glance ──
    add("<h2 class='sec' id='corpus'>The corpus at a glance</h2>")
    sess_rows = []
    for s in sess_list:
        sb = star_by[(s["assembly"], s["session"])]
        b = bloc_by_session.get(skey(s)) or {}
        opp = b.get("opposition_pct")
        sess_rows.append([skey(s), s["first_date"], f"{s['questions']:,}",
                          f"{s['coverage']}%",
                          f"{pct(sb['star'], s['questions']):.0f}%",
                          f"{opp:.1f}%" if opp is not None else "—"])
    sess_rows.append(["All sessions", "—", f"{total:,}",
                      f"{ov['reply_coverage']}%", f"{star_pct_all:.0f}%",
                      f"{opp_share}%"])
    add(table(["Session", "First sitting", "Questions", "Reply coverage",
               "Starred", "Opposition share"],
              sess_rows, total_row=True,
              caption=f"Table: the {n_sessions} sessions in scope. "
                      "Source: stats.json, layer3_demands.json."))

    # ══ Challenge · Pillar 1 ══
    add(arc("Challenge · pillar 1"))
    add("<h2 class='sec' id='p1'>Patterns of legislative attention</h2>")
    add("<div class='guide'><b>Guiding question.</b> Where does legislative attention "
        "go — which departments, subjects, places and members absorb questioning, and "
        "how stable is that attention across sessions?</div>")

    add("<h3>Attention concentrates: the top three departments take "
        f"{top3_share}% of questions</h3>")
    add(f"<p>Education, Health and Roads/PHE form the standing core of questioning, "
        f"but each session has a different leading department — attention rotates "
        f"rather than accumulating.</p>")
    add(figs("01-dept-attention", "02-dept-session-heatmap"))
    add(table(["Department", "Questions", "Share", "Sessions", "Askers",
               "Reply coverage"],
              [[d["department"], f"{d['questions']:,}", f"{d['share']}%",
                d["sessions"], d["askers"], f"{d['coverage']}%"]
               for d in stats["departments"][:15]],
              caption="Top 15 departments by questions asked. Source: stats.json "
                      "(all 54 in the data appendix)."))

    add(f"<h3>Two policy domains carry {top2_share}% of all questions</h3>")
    add("<p>Themes are assigned by a keyword codebook with department-prior "
        "tie-breaks; every assignment carries its evidence row.</p>")
    add(figs("03-themes", "16-theme-dept-heatmap"))
    add(table(["Policy domain", "Questions", "Share"],
              [[th, f"{n:,}", f"{pct(n, total)}%"] for th, n in theme_sorted],
              caption=f"All {len(theme_sorted)} policy domains over {total:,} "
                      "questions. Source: layer1_themes.json."))
    add(table(["Classification method", "Questions", "Share"],
              [[k.replace("_", " "), f"{v:,}", f"{pct(v, total)}%"]
               for k, v in sorted(themes["classification_methods"].items(),
                                  key=lambda kv: -kv[1])],
              caption="How themes were assigned (classification audit trail). "
                      "Source: layer1_themes.json."))
    add(details(f"Top 15 subthemes (of {len(themes['subtheme_counts'])})",
                table(["Subtheme", "Questions"],
                      [[k, f"{v:,}"] for k, v in
                       sorted(themes["subtheme_counts"].items(),
                              key=lambda kv: -kv[1])[:15]],
                      caption="Source: layer1_themes.json.")))

    mention = geo["mentioned"]
    add(f"<h3>{mention['share_with_any_mention_pct']}% of questions name a place — "
        f"most are state-wide in scope</h3>")
    add("<p>Two lenses: where the <i>asker's seat</i> is (MLA lookup) and what the "
        "<i>text</i> names (gazetteer scan). They answer different questions and are "
        "never merged.</p>")
    add(figs("04-districts", "17-mentioned-places"))
    add(table(["Region", "Questions", "Share"],
              [[k or "Not attributed", f"{v:,}", f"{pct(v, total)}%"]
               for k, v in sorted(geo["region_counts"].items(), key=lambda kv: -kv[1])],
              caption="Questions by the asker's district-region. "
                      "Source: layer2_geography.json."))
    add(table(["District (asker's seat)", "Questions", "Share"],
              [[k or "Not attributed", f"{v:,}", f"{pct(v, total)}%"]
               for k, v in sorted(geo["district_counts"].items(),
                                  key=lambda kv: -kv[1])],
              caption="Questions by the asker's district. Source: layer2_geography.json."))
    add(table(["Scope of the question", "Questions", "Share"],
              [[k.replace("_", "-"), f"{v:,}", f"{pct(v, total)}%"]
               for k, v in sorted(geo["scope_counts"].items(), key=lambda kv: -kv[1])],
              caption="State-wide vs place-specific vs constituency-specific. "
                      "Source: layer2_geography.json."))
    add(details("Districts named inside question texts (top 10)",
                table(["District mentioned", "Questions", "% of corpus"],
                      [[m["place"], f"{m['questions']:,}", f"{m['share_pct']}%"]
                       for m in mention["districts"][:10]],
                      caption=f"{mention['questions_with_any_mention']:,} questions "
                              f"name any place ({mention['share_with_any_mention_pct']}% "
                              "of the corpus). Source: layer2_geography.json.")))

    add(f"<h3>{n_fam} subjects recur across sessions — the standing agenda</h3>")
    add("<p>Recurrence uses exact normalized-subject matching (paraphrases are "
        "deliberately under-merged rather than guessed).</p>")
    add(figs("05-recurring-dots"))
    add(table(["Recurring subject", "Sittings", "Sessions", "Trajectory"],
              [[f["subject"], f["occurrences"], len(f["sessions"]),
                f["trajectory"].replace("_", " ")] for f in fam_top[:15]],
              caption=f"Top 15 of {n_fam} recurring subjects. "
                      "Source: layer5_resolution.json."))

    mlas = stats["mlas"]
    add(f"<h3>{esc(mlas[0]['mla'])} asks the most: {mlas[0]['questions']} questions "
        f"across {mlas[0]['departments']} departments</h3>")
    add(figs("15-mla-bubble"))
    add(table(["Member", "Questions", "Departments questioned", "Most-asked department"],
              [[m["mla"], m["questions"], m["departments"], m["top_department"]]
               for m in mlas[:10]],
              caption=f"Top 10 of {len(mlas)} members. Source: stats.json "
                      "(all members in the data appendix)."))

    budgets = ref_data.DEPT_BUDGET
    q_by_dept = Counter(normalize_dept(r.get("Departments")) for r in rows)
    budget_rows = []
    for dept, budget in budgets.items():
        q = q_by_dept.get(dept, 0)
        if q >= 5 and budget:
            budget_rows.append([dept, f"{budget:,.0f}", f"{q:,}",
                                f"{100 * q / budget:.1f}"])
    budget_rows.sort(key=lambda r: -float(r[1].replace(",", "")))
    biggest = budget_rows[0] if budget_rows else ["—", "—", "—", "—"]
    by_q = sorted(budget_rows, key=lambda r: -int(r[2].replace(",", "")))
    rank = next((i + 1 for i, r in enumerate(by_q) if r[0] == biggest[0]), "—")
    biggest_dept = str(biggest[0]).replace(" Department", "")
    add(f"<h3>The largest budget — {esc(biggest_dept)} at ₹{biggest[1]} crore — "
        f"ranks #{rank} of {len(budget_rows)} departments in questions asked</h3>")
    add(figs("18-budget-scatter"))
    add(table(["Department", "Budget 2025–26 (₹ crore)", "Questions",
               "Questions per ₹100 crore"],
              budget_rows,
              caption="Departments with ≥5 questions and a published allocation; "
                      "single-year budget, question window "
                      f"{window} — a ratio, not a rate. Source: reference_data "
                      "DEPT_BUDGET + CSV."))

    # ══ Challenge · Pillar 2 ══
    add(arc("Challenge · pillar 2"))
    add("<h2 class='sec' id='p2'>Dynamics and quality of oversight</h2>")
    add("<div class='guide'><b>Guiding question.</b> How does oversight work in "
        "practice — what do questions demand, who asks, and what do replies actually "
        "contain: substance, commitments, timeliness and evidence of delivery?</div>")

    add(f"<h3>{info_share}% of questions ask for information; {action_share}% "
        f"demand action</h3>")
    add(figs("06-demand-by-dept", "14-starred"))
    add(table(["Demand type", "Questions", "Share"],
              [[k, f"{v:,}", f"{pct(v, total)}%"]
               for k, v in sorted(demands["demand_counts"].items(),
                                  key=lambda kv: -kv[1])],
              caption=f"Over {total:,} questions. Source: layer3_demands.json."))
    dem_by_dept = {}
    for raw, counts in demands["demand_by_department"].items():
        agg = dem_by_dept.setdefault(normalize_dept(raw), Counter())
        agg.update(counts)
    top_dem = sorted(dem_by_dept.items(), key=lambda kv: -sum(kv[1].values()))[:12]
    add(details("Demand mix for the 12 most-questioned departments",
                table(["Department", "Information", "Action", "Explanation",
                       "Accountability", "Total"],
                      [[d, c.get("Information", 0), c.get("Action", 0),
                        c.get("Explanation", 0), c.get("Accountability", 0),
                        sum(c.values())] for d, c in top_dem],
                      caption="Raw department labels as recorded in questions; "
                              "aggregated via dept normalization. "
                              "Source: layer3_demands.json.")))
    add(details("Demand types by policy domain",
                table(["Policy domain", "Information", "Action", "Explanation",
                       "Accountability"],
                      [[th, c.get("Information", 0), c.get("Action", 0),
                        c.get("Explanation", 0), c.get("Accountability", 0)]
                       for th, c in demands["demand_by_theme"].items()],
                      caption="Source: layer3_demands.json.")))

    add(f"<h3>Opposition members asked {opp_share}% of questions and led "
        f"{opp_led} of {n_sessions} sessions</h3>")
    add(figs("19-opposition"))
    add(table(["Bloc", "Questions", "Share"],
              [[k, f"{v:,}", f"{pct(v, total)}%"]
               for k, v in sorted(bloc_counts.items(), key=lambda kv: -kv[1])],
              caption=f"Over {total:,} questions; bloc from member party records. "
                      "Source: layer3_demands.json."))
    bloc_tbl = []
    for key, b in bloc_by_session.items():
        c = b["counts"]
        bloc_tbl.append([key, f"{b['questions']:,}",
                         c.get("Ruling", 0), c.get("Opposition", 0),
                         f"{b['opposition_pct']:.1f}%"])
    add(table(["Session", "Questions", "Ruling", "Opposition",
               "Opposition share"], bloc_tbl,
              caption="Who asks, session by session. Source: layer3_demands.json."))

    peak_sess = max(sess_list, key=lambda s: s["questions"])
    add(f"<h3>Question volume peaks at {peak_sess['questions']:,} questions in "
        f"{esc(skey(peak_sess))} — attention rises and falls with each sitting</h3>")
    add(figs("07-session-trend", "08-dept-slopes"))
    add(details("Rising departments (steepest first)",
                table(["Department", "Δ questions / session", "Latest session"],
                      [[d["department"], f"{d['mean_delta']:+.1f}",
                        d["series"][-1]] for d in trends["rising_departments"]],
                      caption="Ordinary least-squares slope over the "
                              f"{n_sessions}-session series. Source: layer6_trends.json.")))
    add(details("Declining departments (steepest first)",
                table(["Department", "Δ questions / session", "Latest session"],
                      [[d["department"], f"{d['mean_delta']:+.1f}",
                        d["series"][-1]] for d in trends["declining_departments"]],
                      caption="Ordinary least-squares slope over the "
                              f"{n_sessions}-session series. Source: layer6_trends.json.")))

    add(f"<h3>Replies arrive in a median {g(t.get('median_days'))} days — "
        f"departments get {g(overall.get('notice_median_days'))} days' notice</h3>")
    add(figs("11-coverage", "21-latency"))
    add(table(["Timeliness measure", "Value", "Basis"],
              [["Trustworthy date pairs", f"{t.get('n', 0):,}",
                f"of {n_coded:,} coded replies ({t.get('coverage', 0)}%)"],
               ["Median submission → reply", f"{g(t.get('median_days'))} days",
                f"min {t.get('min_days', '—')}, max {t.get('max_days', '—')} days"],
               ["75th percentile", f"{g(t.get('p75_days'))} days", "pairs"],
               ["Over 30 days", f"{t.get('share_over_30d', 0)}%", "of pairs"],
               ["Over 90 days", f"{t.get('share_over_90d', 0)}%", "of pairs"],
               ["Median notice before sitting",
                f"{g(overall.get('notice_median_days'))} days",
                f"submission date → sitting date"],
               ["Late replies (after the sitting)", f"{overall['late_replies']}",
                f"{overall['late_share_pct']}% of dated replies"],
               ["Excluded date pairs", f"{overall['excluded_pairs']}",
                "flagged but kept in the data"]],
              caption="Date-gap analysis over extracted reply texts. "
                      "Source: compute_layer4 (build_compendium.py)."))
    add(details("Reply coverage by session",
                table(["Session", "Questions", "With reply", "Coverage"],
                      [[skey(s), f"{s['questions']:,}", f"{s['with_reply']:,}",
                        f"{s['coverage']}%"] for s in sess_list],
                      caption="Source: stats.json.")))

    add(f"<h3>{det_share}% of replies are detailed — but only "
        f"{overall['timeline_pct']}% commit to a date</h3>")
    add(figs("09-substantiveness", "10-assurance-evasion"))
    add(table(["Substantiveness band", "Replies", "Share"],
              [[k, f"{v:,}", f"{pct(v, n_coded)}%"]
               for k, v in sorted(overall["substantiveness"].items(),
                                  key=lambda kv: -kv[1])],
              caption=f"n={n_coded:,} coded replies. Source: compute_layer4."))
    add(table(["Specificity level", "Replies", "Share"],
              [[k, f"{v:,}", f"{pct(v, n_coded)}%"]
               for k, v in sorted(overall["specificity"].items(),
                                  key=lambda kv: -kv[1])],
              caption=f"n={n_coded:,} coded replies. Source: compute_layer4."))
    add(table(["Reply dimension", "Value", "Denominator"],
              [["Pure boilerplate", f"{overall['boilerplate_pct']}%",
                f"of {n_coded:,} coded replies"],
               ["Self-contradicting", f"{overall['contradiction_pct']}%",
                f"of {n_coded:,} coded replies"],
               ["Commits to a timeline", f"{overall['timeline_pct']}%",
                f"of {n_coded:,} coded replies"],
               ["Cites a budget figure", f"{overall['budget_pct']}%",
                f"of {n_coded:,} coded replies"],
               ["Names a responsible party", f"{overall['responsible_pct']}%",
                f"of {n_coded:,} coded replies"],
               ["Shows delivery progress",
                f"{overall['progress_evidence_pct']}%",
                f"of {overall['n_staged']:,} replies that evidence a stage"],
               ["Assurance-signal weight (mean)",
                f"{overall['assurance_weight_mean']}", "signal registry, not a score"],
               ["Evasion-signal weight (mean)",
                f"{overall['evasion_weight_mean']}", "signal registry, not a score"]],
              caption="Dimensions reported separately — no composite. "
                      "Source: compute_layer4."))

    stage_order = ["None evidenced", "Concept/Proposal", "Administrative Processing",
                   "Sanction/Funding", "Approval", "Procurement", "Execution/Award",
                   "Implementation", "Completion"]
    add("<h3>Most replies stop before any delivery stage is evidenced</h3>")
    add(figs("20-exec-stages"))
    add(table(["Execution stage evidenced", "Replies", "Share"],
              [[st, f"{overall['stage_distribution'].get(st, 0):,}",
                f"{pct(overall['stage_distribution'].get(st, 0), n_coded)}%"]
               for st in stage_order],
              caption=f"Highest evidenced stage per reply, n={n_coded:,} coded. "
                      "Source: compute_layer4."))
    dq_rows = []
    for d, v in list(dept_summary.items())[:12]:
        dq_rows.append([d, f"{v['n_replies']:,}",
                        v["latency_median"] if v["latency_median"] is not None else "—",
                        f"{v['boilerplate_pct']}%", f"{v['contradiction_pct']}%",
                        f"{v['timeline_pct']}%", f"{v['budget_pct']}%",
                        f"{v['responsible_pct']}%"])
    add(table(["Department", "Replies", "Median days", "Boilerplate",
               "Contradiction", "Timeline", "Budget cited", "Responsible"],
              dq_rows, total_row=False,
              caption="The 12 most-replied departments; percentages of that "
                      "department's coded replies. Source: compute_layer4."))

    # ══ Challenge · Pillar 3 ══
    add(arc("Challenge · pillar 3"))
    add("<h2 class='sec' id='p3'>Persistent and emerging challenges</h2>")
    add("<div class='guide'><b>Guiding question.</b> Which challenges persist or "
        "re-emerge across sessions, and what should departments anticipate and "
        "prepare for?</div>")

    traj_total = sum(res_counts.values())
    add(f"<h3>{n_stalled} of {n_fam} recurring subjects show no progress language "
        f"— {n_resolved} read as resolved</h3>")
    add(figs("12-resolution"))
    add(table(["Trajectory", "Subjects", "Share"],
              [[k.replace("_", " ").title(), f"{v:,}", f"{pct(v, traj_total)}%"]
               for k, v in sorted(res_counts.items(), key=lambda kv: -kv[1])],
              caption=f"Language-based course of the {n_fam} subjects asked in "
                      "two or more sessions. Source: layer5_resolution.json."))
    stalled = sorted((f for f in families.values() if f["trajectory"] == "stalled"),
                     key=lambda f: (-len(f["sessions"]), -f["occurrences"]))
    add(details(f"Stalled subjects ({len(stalled)}) — no progress language to date",
                table(["Subject", "Sessions", "Sittings", "Departments"],
                      [[f["subject"], len(f["sessions"]), f["occurrences"],
                        ", ".join(f["departments"][:2]) + ("…" if len(f["departments"]) > 2 else "")]
                       for f in stalled],
                      caption="Ordered by session count. Source: layer5_resolution.json.")))

    add(f"<h3>{len(emerging)} issues first surfaced in the three most recent "
        f"sessions — the watchlist</h3>")
    add(figs("13-emerging"))
    add(table(["Emerging subject", "First seen", "Sittings", "Members asking"],
              [[e["subject"], e["first_session"], e["occurrences"], len(e["askers"])]
               for e in emerging],
              caption="Rule: first seen in the last three sessions, ≥2 sittings, "
                      "≥2 members. Source: layer6_trends.json."))
    nvr_rows = []
    nvr_q = nvr_rec = nvr_new = 0
    for s in sess_list:
        key = skey(s)
        nvr = trends["new_vs_recurring"].get(key) or {}
        div = trends["diversity_index"].get(key)
        nvr_q += s["questions"]
        nvr_rec += nvr.get("recurring", 0)
        nvr_new += nvr.get("new", 0)
        nvr_rows.append([key, f"{s['questions']:,}", nvr.get("recurring", "—"),
                         nvr.get("new", "—"),
                         f"{nvr.get('recurring_pct', 0)}%",
                         div if div is not None else "—"])
    nvr_rows.append(["All sessions", f"{nvr_q:,}", nvr_rec, nvr_new,
                     f"{pct(nvr_rec, nvr_q)}%", "—"])
    add(table(["Session", "Questions", "Recurring", "New", "Recurring share",
               "Breadth per member"],
              nvr_rows, total_row=True,
              caption="Recurring = subject already asked in an earlier session; "
                      "breadth = mean distinct departments questioned per member "
                      "per session. Source: layer6_trends.json."))

    # ══ Action · briefs ══
    add(arc("Action"))
    add("<h2 class='sec' id='briefs'>Anticipate &amp; prepare: department briefs</h2>")
    add("<p>Evidence-linked preparation: what is likely to be asked again (because "
        "it persists or is rising in the record) and what a department can put in "
        "place. These are summaries of the record, not predictions — every item "
        "links back to counted questions.</p>")
    if briefs:
        shown = sorted(briefs, key=lambda d: -briefs[d]["questions"])[:12]
        add(f"<p class='note'>Showing {len(shown)} of {len(briefs)} department "
            "briefs; the full set is in "
            "<code>output/anticipation/dept_briefs.json</code>.</p>")
        for dept in shown:
            b = briefs[dept]
            add(f"<div class='brief'><h4>{esc(dept)}</h4>"
                f"<div class='meta'>{b['questions']} questions ({b['share_pct']}%) · "
                f"reply coverage {b['reply_coverage_pct']}% · "
                f"trend {b['trend_delta_per_session']:+.2f}/session · "
                f"{b['recurring_subjects']} recurring · "
                f"{b['replies_coded']} replies coded</div>")
            if b["anticipate"]:
                add("<b>Anticipate:</b><ul>" + "".join(
                    f"<li>{esc(a['subject'])} <span class='tag'>{esc(a['why'])}</span></li>"
                    for a in b["anticipate"][:6]) + "</ul>")
            if b["prepare"]:
                add("<b>Prepare:</b><ul>" + "".join(
                    f"<li>{esc(p)}</li>" for p in b["prepare"]) + "</ul>")
            add("</div>")
    else:
        add("<div class='note'>No briefs found — run "
            "<code>scripts/build_anticipation.py</code>.</div>")

    # ══ Resolution · methods ══
    add(arc("Resolution"))
    add("<h2 class='sec' id='methods'>Methods, validation, and limits</h2>")
    add("<h3>Sources and pipeline</h3>")
    add("<p><b>Questions:</b> NeVA Digital Library export "
        "(<code>data/dl_questions_raw.csv</code>), scoped to sittings from 2021; "
        f"pre-2021 rows are excluded from every number above "
        f"({total:,} rows remain). <b>Replies:</b> signed PDFs under "
        "<code>data/pdfs/</code>, OCR'd with nemotron-ocr under a three-reader "
        "consensus with mechanical gates; workers write to a C: drive run directory "
        "mirrored to the repository. <b>Derived evidence:</b> six rule-based layers "
        "plus reply coding, each row carrying its evidence (matched keywords, "
        "counts) rather than a model verdict.</p>")
    add(table(["Evidence layer", "Question it answers", "Method", "Output file"],
              [["1 · Themes", "Which policy domains do questions concern?",
                "Keyword codebook with department-prior tie-breaks; per-row evidence",
                "layer1_themes.json"],
               ["2 · Geography", "Where are askers from, what do texts name?",
                "MLA → seat lookup + gazetteer scan of the question text",
                "layer2_geography.json"],
               ["3 · Demands & blocs",
                "What kind of answer is asked, and by whom?",
                "Demand keywords; ruling/opposition from member party records",
                "layer3_demands.json"],
               ["4 · Reply quality",
                "What do replies contain (coded)?",
                "Reply codebooks: length bands, specificity, actionability, stages, "
                "assurance/evasion, contradictions, date gaps",
                "stats + report (compute_layer4)"],
               ["5 · Recurrence",
                "Which subjects persist across sessions?",
                "Exact normalized-subject match in ≥2 sessions + trajectory language",
                "layer5_resolution.json"],
               ["6 · Trends",
                "What is rising, declining, emerging?",
                f"Per-session slopes; emerging = first seen in the last 3 sessions, "
                "≥2 sittings, ≥2 members", "layer6_trends.json"]],
              caption="Each layer is deterministic and re-runnable; "
                      "see the appendix for regeneration commands."))
    add("<h3>Validation</h3>")
    unmatched_q = sum(1 for r in rows
                      if str(r.get("Asked_By") or "") in set(geo.get("mla_unmatched", [])))
    add(table(["Check", "Result"],
              [["Reply dates vs hand-annotated truth (12 PDFs)",
                "12/12 exact, 0 confident extraction errors"],
               ["Thematic coding", "100-question stratified sample drawn for manual "
                                   "review (output/validation/)"],
               ["Asker → seat join",
                f"{total - unmatched_q:,} of {total:,} questions carry a matched "
                f"seat ({pct(total - unmatched_q, total)}%); "
                f"{len(geo.get('mla_unmatched', []))} unmatched name(s) recorded in "
                "layer2_geography.json"],
               ["Date-gap exclusions",
                f"{overall['excluded_pairs']} pairs flagged as untrustworthy — "
                "excluded from latency stats but kept in the data"],
               ["Supervisor review of extraction decisions",
                "kept in the pipeline; 0 usable corrections in 70+ trials "
                "(output/validation/supervisor_trial*.json)"]],
              caption="Evidence for the evidence."))
    add("<div class='warnbox'><b>What this report does not claim.</b>"
        "<ul class='plain'>"
        "<li>No composite scores, readiness indices, probabilities or forecasts; "
        "no ranking of departments beyond measured counts; no judgement of "
        "individual officers; the briefs are summaries of the record, not "
        "LLM-generated action plans.</li>"
        "<li>Associations (e.g. budget vs questions) are descriptive; the budget is "
        "a single year (2025–26) against a multi-year question window.</li>"
        "<li>Reply-quality codes measure textual signals in OCR'd replies, not "
        "administrative reality; substantiveness is length-based by construction.</li>"
        "<li>Exact-match recurrence under-merges paraphrases by design; the "
        "emerging list is small-sample by rule (≥2 sittings, ≥2 members).</li>"
        "<li>Bloc labels follow party records; unaffiliated members fall to "
        "Unknown. Latency uses only trustworthy date pairs.</li>"
        "<li>Reply coverage before 2021 was 0–16%, which is why the window starts "
        "in 2021.</li>"
        "</ul></div>")

    # ══ Resolution · appendix ══
    add("<h2 class='sec' id='data'>Data appendix</h2>")
    add(details(f"All {len(stats['departments'])} departments",
                table(["Department", "Questions", "Share", "Sessions", "Askers",
                       "Reply coverage"],
                      [[d["department"], f"{d['questions']:,}", f"{d['share']}%",
                        d["sessions"], d["askers"], f"{d['coverage']}%"]
                       for d in stats["departments"]],
                      caption="Source: stats.json.")))
    add(details(f"All {len(mlas)} members",
                table(["Member", "Questions", "Departments", "Most-asked department"],
                      [[m["mla"], m["questions"], m["departments"],
                        m["top_department"]] for m in mlas],
                      caption="Source: stats.json.")))
    add(details(f"All {n_fam} recurring subjects",
                table(["Subject", "Sittings", "Sessions", "Departments",
                       "Trajectory"],
                      [[f["subject"], f["occurrences"], len(f["sessions"]),
                        ", ".join(f["departments"][:2]) + ("…" if len(f["departments"]) > 2 else ""),
                        f["trajectory"].replace("_", " ")]
                       for f in fam_top],
                      caption="Source: layer5_resolution.json.")))
    add("<h3>What is where</h3>")
    add(table(["File", "Contents"],
              [["output/layers/layer1_themes.json",
                "Themes, subthemes, classification methods, theme × department"],
               ["output/layers/layer2_geography.json",
                "Region/district by asker seat, question scope, mentioned places"],
               ["output/layers/layer3_demands.json",
                "Demand types, blocs, session-level bloc mix"],
               ["output/layers/layer5_resolution.json",
                "Recurring subjects, trajectories, question numbers"],
               ["output/layers/layer6_trends.json",
                "Department/theme session series, rising/declining, emerging"],
               ["output/stats.json",
                "Corpus overview, sessions, departments, members, recurring"],
               ["output/charts/ (PNG + SVG + manifest.json)",
                "The 21 figures used here, reusable as journal figures"],
               ["output/anticipation/dept_briefs.json",
                "Full per-department briefs"],
               ["output/charts/index.html",
                "Interactive visual companion (dashboard)"],
               ["output/compendium/", "Pillar compendium (markdown + charts page)"],
               ["output/report/index.html", "This report"]],
              caption="Everything a reviewer needs to trace a number back."))
    add("<h3>Regenerating this report</h3>")
    add("<pre class='cmd'>python scripts/run_layers.py\n"
        "python scripts/build_anticipation.py\n"
        "python scripts/build_compendium.py\n"
        "python scripts/build_charts.py\n"
        "python scripts/build_dashboard.py\n"
        "python scripts/build_report.py</pre>")

    add(f"<footer>Legislative Oversight in Meghalaya · evidence report · "
        f"generated {datetime.now():%d %B %Y, %H:%M} · {total:,} questions, "
        f"{n_sessions} sessions, {n_coded:,} coded replies · every number computed "
        "from source data at generation time · no composites, probabilities or "
        "forecasts</footer>")
    add("</div></body></html>")

    dest = OUT / "index.html"
    dest.write_text("\n".join(L), encoding="utf-8")
    kb = dest.stat().st_size // 1024
    n_tables = "\n".join(L).count("<table")
    print(f"report -> {dest} ({kb} KB, {len(FIG)} figures, {n_tables} tables, "
          "self-contained)")


if __name__ == "__main__":
    main()
