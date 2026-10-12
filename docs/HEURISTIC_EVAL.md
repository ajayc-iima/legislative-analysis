# Heuristic Evaluation — Visualization Suite (dashboard, report, 21 charts)

Method: Nielsen's 10 heuristics plus the shared dataviz deck's
**master checklist** (8 dimensions) and its **narrative-edit prompts**,
applied by inspection on 2026-10-12 to the current build
(21 charts, single-file report, dashboard). Everything below is either
✅ pass, ⚠️ accepted trade-off, ➖ N/A, or ❌→fixed with the fix named.

## A. Master checklist (deck, final slides) — per dimension

| Dimension | Verdict | Evidence / fix |
|---|---|---|
| **Message** (one dominant comparison) | ❌→fixed | Chart 02's title asserted "leads N of 11 sessions" with no visual way to verify it → gold rings now mark each session's leading cell. Report cards previously printed the message twice (HTML headline + in-image title) → `_strip_internal_title()` removes the in-SVG `<text>` title; the HTML headline is the single title. |
| **Mapping** (channel matches variable type) | ❌→fixed | Chart 20 (delivery stage) and chart 12 (trajectory) encoded an **ordered** variable with rainbow hues → ordered single-hue ramps; chart 09 (reply length) red→amber→teal→navy → ordered cool ramp; alarm hues (amber/red) reserved for stalled/regressed. |
| **Scale** (domain, units, transforms explicit) | ✅ pass | Axis labels carry units (% of coded replies, questions/session, ₹ crore); every share states its denominator; no log or truncated scales. |
| **Integrity** (visible extent matches values) | ✅ pass | All bars start at zero; heatmaps (02, 16) label every cell and carry a colorbar; diverging chart (08) is symmetric around zero. Label ink is picked by measured WCAG contrast against the real fill (heatmap cell colour sampled from the colormap, segment colour from the palette) instead of a "is this dark?" guess — mid-grey bands get dark ink, not grey. |
| **Color** (purposeful and accessible) | ❌→fixed | Chart 08 used red/green (CVD-unsafe) → navy/gold from the deck palette; sign is still encoded by position. Chart 11 keeps band colors but now prints the % on every bar and carries a band legend. |
| **Density** (overlap cannot hide evidence) | ❌→fixed | Charts 09 and 20 drew legends **over** the bars → moved below the plot (outside); chart 20 stacked 9 stages where 4 carry the mass → top-3 stages + "None evidenced" + one honest "Other stages (n)" band, thin members named in the legend. Label collisions were the last form of hidden evidence: scatter labels were placed by a guessed data-space radius and printed on top of each other (figures 8, 10, 18) → `label_points()` measures the rendered text box and keeps a label only when it clears every label already placed. |
| **Context** (viewer decodes quickly) | ❌→fixed | Charts 03, 08, 11, 12, 14 carried no value labels → added (count + share, signed Δ, % , trajectory n (%), session totals). Every figure has a "Source & Method" caption. Labelling is now **one rule across all 21 figures**, not a per-chart decision — see §F. |
| **Story** (raw → derived → consequence) | ✅ pass | Report Parts 3–5 = raw record, derived coding, consequences; briefs close with preparation actions. |

## B. Narrative-edit prompts (deck slide 163)

| Prompt | Verdict | Evidence / fix |
|---|---|---|
| Write the one-sentence takeaway | ✅ pass | All 21 chart titles and all section headings are computed sentences carrying their own numbers. |
| Mute non-essential series | ❌→fixed | Chart 20 now aggregates 5 thin stages into one labelled "Other" band. |
| Annotate the event that explains the change | ✅ pass | Chart 07 shades the 10th→11th Assembly transition; chart 11 marks the coverage bands; chart 21 marks median and 30-day reference lines. |
| Replace generic title with a message title | ✅ pass | Titles such as "40% of coded replies are detailed or very detailed (n=2,168)" replace chart names. |

## C. Nielsen's heuristics — current build

| # | Heuristic | Verdict | Evidence / fix |
|---|---|---|---|
| H1 | Visibility of system status | ✅ pass | Generation timestamp, corpus counts, extraction-complete badge, scope coverage on the cover. |
| H2 | Match with the real world | ✅ pass | Legislative vocabulary; no scores, indices, probabilities or forecasts anywhere. |
| H3 | User control and freedom | ✅ pass | Static pages, sticky nav, `<details>` disclosure, no traps. |
| H4 | Consistency and standards | ❌→fixed | Single caption pattern; **new**: SVGs switched to real `<text>` (fonttype `none`) — selectable, screen-reader readable, and ~50% smaller (report 1,532 → 771 KB). |
| H5 | Error prevention | ➖ N/A | No user inputs; the one write path (mirror script) has a monotonic guard. |
| H6 | Recognition rather than recall | ❌→fixed | Value labels added to five chart families; the reading-guide table states the standard figure-by-figure; §F fixes the labelling rule so the reader knows, before reading any figure, when a mark carries its number and when it deliberately does not. |
| H7 | Flexibility and efficiency | ✅ pass | Responsive layout, print stylesheet, standalone PNG/SVG for journal use, CSV export for spreadsheets. |
| H8 | Aesthetic and minimalist design | ❌→fixed | Duplicate titles removed; legends moved off the data; density reduced; overlapping labels resolved (figure 8 originally named 8 of 20 bubbles by an arbitrary rank rule, figures 10 and 18 collided, the histogram and the trend line carried no labels at all). 21 figures remain heavy — mitigated by pillar grouping and the sticky nav. |
| H9 | Help users recover from errors | ➖ N/A | Nothing to break; limitations documented instead. |
| H10 | Help and documentation | ❌→fixed | **Number rot**: eight executive callouts and one KPI hardcoded values (222/219/185, 28.2%, 40.5%, 124, 2,168, 69.9%, 62.1%) that would silently contradict the report's own "every number computed at generation" claim. All are now computed from live data (audit: 0 hardcoded data literals remain in the report generator). |

## D. Open trade-offs (accepted, documented)
- No choropleth map (no boundary shapefile in repo); district bars carry identical counts.
- Red/amber/green remains in the coverage chart as an alarm scale — CVD-safe by construction (every bar prints its % and a band legend states the bands), never the sole cue.
- No per-figure `<details>`; group-level tables carry the same numbers with less markup.

---

## Historical note (earlier builds)

The first dashboard pass fixed finding-titles, % labels, group data
tables and the sticky nav; the open items above (choropleth, details
per figure, red/green) were carried forward from it and re-verified
in this round.

---

## E. How the deck's principles reach the reader

The report now carries the standard explicitly: §"How to Read the
Evidence" (immediately after the executive findings) prints the
8-dimension checklist with the column "How this report meets it", so a
reviewer can check the contract figure by figure instead of trusting
it. Story arc runs Findings → Reading Guide → Theory → Method →
Findings I/II/III → Briefs → Policy → Appendix, each marked by a
section arc label.

Automated checks run against the current build (see the report
validator):
- self-contained: zero external loads, XML prolog/DOCTYPE stripped
- exactly one title per figure (HTML headline; in-SVG title removed)
- all nav anchors resolve; 21 sequentially numbered figures, each with
  eyebrow + "Source & Method" caption
- no hardcoded data literals remain in the report generator: every
  number in prose and tables is computed from source data at build time
- no overlapping labels in any chart (`scripts/dev/audit_labels.py`:
  21/21 charts pass; rotated labels compared as oriented rectangles)

Carried-forward trade-offs: no choropleth (documented); coverage-band
alarm colors kept with % on every bar plus a band legend; extraction
badge reads "reply texts complete" only when every scoped PDF on disk
has a reply text (18 records are flagged-empty with recorded reasons —
see `data/review/FLAGGED_EMPTY.md`).

---

## F. Labelling policy (one rule for all 21 figures)

Labelling is not decoration: a value label is the reader's only way to
take an exact number off a chart. Partially labelled figures therefore
communicate a rule the reader cannot see — which is how figure 8 came to
name 8 of 20 members by rank order while 12 bubbles sat unlabelled.

**The policy, applied identically to every figure:**

| Mark type | Rule | Figures |
|---|---|---|
| Single bar / dot-plot row | Label **every** mark | 01, 03, 04, 05, 08, 11, 12, 17 |
| Line point | Label **every** point, haloed so the line cannot cross the number | 07 |
| Heatmap cell | Label **every** non-zero cell; zero cells stay empty | 02, 16 |
| Stacked column segment | Label every segment **>= 8%** of its column; the rest are left to the axis | 06, 09, 14, 19, 20 |
| Histogram bin | Label every bin **>= 10%** of the tallest bin; the thin tail is read off the axis | 21 |
| Scatter / bubble | Leaders on each axis first, then **every** remaining point whose measured label box clears all others; how many were placed is printed in the caption | 10, 15, 18 |

Two supporting rules keep labels legible: label ink is chosen by measured
WCAG contrast against the real fill (never an "is this dark?" guess), and
axes reserve headroom so a value label can never run into the title or a
reference line — both happened, the tallest column's share label on
figure 19 sat on the title.

**This is checked, not trusted.** `scripts/dev/audit_labels.py` parses
each built SVG, measures every text label in figure coordinates
(handling anchor, rotation and ancestor translation), and reports any
overlapping pair. Rotated labels are compared as oriented rectangles via
the separating axis theorem, because axis-aligned boxes would report
every 45-degree tick label as a collision with its own neighbour.
Current build: **21 charts, 0 overlapping pairs**.
