# Heuristic Evaluation — Compendium Dashboard (`output/charts/index.html`)

Method: Nielsen's 10 heuristics, applied by inspection. Fixed during
the evaluation: finding-titles on key charts, % labels beside counts,
data tables next to every chart group, sticky section nav.

| # | Heuristic | Verdict | Evidence / fix |
|---|---|---|---|
| H1 | Visibility of system status | ✅ Pass | Generation timestamp, corpus counts, OCR-coverage KPI on every render |
| H2 | Match with the real world | ✅ Pass | Legislative vocabulary throughout; no "scores", "readiness", or probabilities anywhere |
| H3 | User control and freedom | ✅ Pass | Static page; sticky anchor nav; no state, no traps |
| H4 | Consistency and standards | ✅ Pass | One palette (World Bank), one caption pattern with data source on all 19 figures |
| H5 | Error prevention | ➖ N/A | No inputs exist; the one write path (mirror script) has a monotonic guard |
| H6 | Recognition rather than recall | ✅ Pass (fixed) | Was: counts without shares. Now: % labels on bars, data tables beside each chart group |
| H7 | Flexibility and efficiency | ✅ Pass | Responsive grid, print stylesheet, SVGs reusable as journal figures |
| H8 | Aesthetic and minimalist design | ⚠️ Accept | 19 figures is heavy; mitigated by pillar grouping + nav. Finding-titles added so skimmers get takeaways without reading every chart |
| H9 | Help users recover from errors | ➖ N/A | Nothing to break; limitations are documented instead |
| H10 | Help and documentation | ✅ Pass | Methods + limitations section, how-to-read briefs note, full regen command chain |

Open items (not fixed — conscious trade-offs):
- No choropleth map (no boundary shapefile in repo); district bars carry identical counts.
- No `<details>` per-figure data tables; group-level tables cover the same data with less markup.
- Red/green risk colors are not colorblind-safe; kept for legacy-palette continuity, never the sole encoding (labels/values always accompany color).
