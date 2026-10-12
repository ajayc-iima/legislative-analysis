# Heuristic Evaluation — Compendium Dashboard (`output/charts/index.html`)

Method: Nielsen's 10 heuristics, applied by inspection. Fixed during
the evaluation: finding-titles on key charts, % labels beside counts,
data tables next to every chart group, sticky section nav.

| # | Heuristic | Verdict | Evidence / fix |
|---|---|---|---|
| H1 | Visibility of system status | ✅ Pass | Generation timestamp, corpus counts, OCR-coverage KPI on every render |
| H2 | Match with the real world | ✅ Pass | Legislative vocabulary throughout; no "scores", "readiness", or probabilities anywhere |
| H3 | User control and freedom | ✅ Pass | Static page; sticky anchor nav; no state, no traps |
| H4 | Consistency and standards | ✅ Pass | One palette (World Bank), one caption pattern with data source on all 21 figures |
| H5 | Error prevention | ➖ N/A | No inputs exist; the one write path (mirror script) has a monotonic guard |
| H6 | Recognition rather than recall | ✅ Pass (fixed) | Was: counts without shares. Now: % labels on bars, data tables beside each chart group |
| H7 | Flexibility and efficiency | ✅ Pass | Responsive grid, print stylesheet, SVGs reusable as journal figures |
| H8 | Aesthetic and minimalist design | ⚠️ Accept | 21 figures is heavy; mitigated by pillar grouping + nav. Finding-titles added so skimmers get takeaways without reading every chart |
| H9 | Help users recover from errors | ➖ N/A | Nothing to break; limitations are documented instead |
| H10 | Help and documentation | ✅ Pass | Methods + limitations section, how-to-read briefs note, full regen command chain |

Open items (not fixed — conscious trade-offs):
- No choropleth map (no boundary shapefile in repo); district bars carry identical counts.
- No `<details>` per-figure data tables; group-level tables cover the same data with less markup.
- Red/green risk colors are not colorblind-safe; kept for legacy-palette continuity, never the sole encoding (labels/values always accompany color).

---

## Addendum — Final report redesign (`output/report/index.html`)

The shareable single-file report was redesigned against
`C:\Users\chou_\Desktop\Data_Visualization.pptx` (166-slide dataviz deck,
after Wilke) plus this evaluation. Regenerated after each extraction pass;
the figure count in this document refers to the current 21-chart manifest.

| Deck principle | How the report applies it |
|---|---|
| Titles state the message, not the chart name | All 21 chart titles computed from live data (e.g. “Education, Health & Family Welfare, Public Work(Road) draw 28.2% of all questions”); section headings are computed findings (h3s read as sentences with numbers); the figure eyebrow carries only number · label · pillar |
| One figure, one dominant point | Each chart group is preceded by a finding heading that states the point |
| Tables as figures | 36 borderless tables: no vertical rules, right-aligned tabular numbers, hairline row separators, caption = “what + source file” |
| Percentages carry denominators | e.g. “43.5% of 1,950 coded replies”; corpus shares out of 2,217 |
| Story arc (Opening → Challenge → Action → Resolution) | Arc labels above each h2: findings → how-to-read → corpus → three pillars → briefs → methods → appendix |
| Every color has a job; never the sole cue | Coverage-band legend added to Figure 11 (≥99 / 80–99 / <80%); values accompany every color |
| Raw evidence before derived | Six evidence layers surfaced as data tables with source files; quality dimensions listed separately (no composite) |
| Audience prior knowledge | “How to read this report”: conventions list + 10-term glossary (starred, coded reply, trajectory, emerging, bloc, notice…) |

| Nielsen (report) | Verdict |
|---|---|
| H1 | Sticky contents (scroll-margin anchors) + generation stamp + extraction badge (complete / still extracting, computed from scoped PDFs on disk) |
| H6 | Every chart group followed by its data table — 25 open, 11 folded under “Show data” |
| H8 | Finding-first h3s; progressive disclosure keeps the page scannable despite 21 figures |
| H10 | Layer-by-layer methods table, validation table, “what this report does not claim” box, regen commands, file inventory |

Validator results for the current build: self-contained (zero external loads,
XML prolog/DOCTYPE stripped from inlined SVGs), all 9 nav anchors resolve,
21 sequentially numbered figures each with eyebrow + source caption,
36 tables, 12 briefs, 9 computed executive findings, no raw-data leakage.

Carried-forward trade-offs: no choropleth (documented); red/amber/green kept
with explicit band legends; extraction badge reads “still extracting” until
every scoped PDF on disk has a reply text.
