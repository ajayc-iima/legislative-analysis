# Legislative Analysis

Monorepo for Meghalaya Legislative Assembly (NeVA) data work. Three small
packages under `packages/`. Facts only — no composite scores, no invented
probabilities.

## Layout

```
README.md            this file
docs/                PLAN, mental model, execution plan, article scaffold, validation notes
packages/            scraper · analysis · pdfs · extract (installable, tested)
scripts/             pipeline runners: run_layers, build_compendium,
                     build_charts, build_dashboard, port_reference,
                     validate_layers, supervisor trials
scripts/dev/         one-off diagnostic probes (see its README)
data/                scraped CSV + reply PDFs (gitignored, regenerable)
output/              layers/ · compendium/ · charts/ · validation/ (gitignored)
```

## Setup

Requires Python 3.10+. The analysis package is stdlib-only; the scraper
and PDF store use `requests`.

```bash
pip install -e packages/scraper -e packages/analysis -e packages/pdfs -e packages/extract
pip install matplotlib  # charts only (in the venv: .venv\Scripts\pip.exe install matplotlib)
```

## Scraper

Downloads Digital Library questions (assemblies 10 and 11, all sessions)
into one CSV.
```bash
python -m legislative_scraper [--out PATH]
```

Default `--out` is `data/dl_questions_raw.csv` at the repo root
(created on first run).

## Analysis

Reads a questions CSV (the scraper's output, or the legacy
`dl_questions_normalized.csv`) and writes `analysis_report.md` +
`stats.json`: question volume per department / MLA / session, reply
coverage, and subjects recurring across sessions.

```bash
python -m legislative_analysis --csv data/dl_questions_raw.csv --out-dir output
```

Options: `--csv`, `--out-dir`, `--top` (rows per table, default 20).

## Reply PDFs

Stores signed reply PDFs under `data/pdfs/`, one folder per
assembly/session:

```
data/pdfs/assembly-11/autumn-session-2026/11_9_S_4037_V1_signed.pdf
```

Filenames are the portal's own (they already carry assembly/session/
question/version codes). The layout is a presentation choice — filenames
alone are unique across the corpus (verified: 0 collisions across
all 2,186 scoped rows, one record per filename).

```bash
# download everything missing (resume-friendly: existing files skipped)
python -m legislative_pdfs --csv data/dl_questions_raw.csv --out data/pdfs

# pilot: first N per session
python -m legislative_pdfs --limit 3

# backfill from an existing folder instead of re-downloading (flat or nested)
python -m legislative_pdfs --copy-from "D:\path\to\old\pdfs"
```

Notes:

- `--copy-from` matches by basename and is the fast path after migrating
  from an older store; anything unmatched is reported and can be fetched
  live afterwards.
- A file's presence means "stored"; the tool never overwrites. Zero-byte
  partials are not produced (a download that fails raises before writing).
- The portal serves anonymous requests; no auth. Downloads pause 0.4 s
  between files.
- Don't dedupe by question number: the portal publishes multiple signed
  versions per question (`_V1`, `_V2`, ...), all distinct documents.

## Extraction (OCR trial)

Reply PDFs are mostly scans, so text comes from NVIDIA OCR. The trial
(`packages/extract/TRIAL.md`) compared ocr-v1, ocr-v2, PaddleOCR and
nemotron-parse on 12 hand-checked pages: **ocr-v1 wins (0.937)**.
Run it with:

```bash
python -m legislative_extract --pdf-root data/pdfs \
  --truth packages/extract/trial_ground_truth.json --out scorecard.json
```

Needs `NVIDIA_API_KEY` in the environment or `.env` (gitignored, never
committed). Dropped endpoints: `nemoretriever-ocr-v1` (EOL),
`nemotron-parse-2.0` (not callable), `rerank-vl` (no endpoint).

### Why so small

The previous 24k-line pipeline produced composite indices
("readiness 92/100", "delivery probability") from hand-picked weights and
unvalidated LLM clusters. Those numbers appeared in reports but were never
back-tested and are not reproducible from the source data. This package
computes only what the data supports directly, in six auditable layers:

- **Layer 1** — thematic classification: 17 policy domains, keyword rules
  with department-sector tie-break, evidence recorded per row (`codebook.py`)
- **Layer 2** — geographic tagging: MLA→constituency→district→region plus a
  gazetteer scan, with scope flags (`geography.py`)
- **Layer 3** — demand-type taxonomy: Information / Explanation / Action /
  Accountability, the last structural (`demand.py`)
- **Layer 4** — response quality: substantiveness, specificity,
  assurance/evasion signals, boilerplate, contradiction, actionability,
  plus reply latency (`response.py`; needs the OCR run below)
- **Layer 5** — resolution tracking: recurring families with trajectories
  (`longitudinal.py`)
- **Layer 6** — trends and emerging issues: departmental/theme deltas,
  new-vs-recurring ratio, diversity index, watchlist (`longitudinal.py`)

```bash
# question-side layers (1-3, 5-6) + layers report
python scripts/run_layers.py          # -> output/layers/

# full Compendium (adds Layer 4 from extracted replies; regenerate as OCR accrues)
python scripts/build_compendium.py    # -> output/compendium/COMPENDIUM.md

# 15 publication charts (PNG + SVG, World Bank palette) + HTML dashboard
python scripts/build_charts.py     # -> output/charts/ (manifest.json)
python scripts/build_dashboard.py  # -> output/charts/index.html

# final shareable report (single self-contained HTML file)
python scripts/build_report.py     # -> output/report/index.html
```

Open `output/charts/index.html` in any browser (no server, no
network needed): KPI cards, all 15 charts with data-source
captions, domain/demand/emerging tables, and methods. The SVGs
double as journal-submission figures; everything regenerates
from source data as the OCR run accrues.

Reference tables ported from the legacy pipeline (never copied by hand)
live in `reference_data.py`, generated by `scripts/port_reference.py`:
60-seat MLA database, constituency→district→region, 200-entry department
alias table, department→sector hierarchy, and the signal/evasion regex
registries. Journal-article scaffold: `ARTICLE_SCAFFOLD.md`.

Traps to avoid if extending: don't name weighted sums "probability" or
"score", don't rank departments by anything other than measured counts
without stating the weights, and keep every number reproducible from the
input CSV.

## Tests

```bash
pip install pytest
python -m pytest
```

## Validation

`VALIDATION.md` records the scraper audit: 99.58% row agreement against
the legacy Selenium scrape on shared sessions, live-portal verification
of every disagreement, and a completeness check against all sessions the
portal lists for assemblies 10 and 11.

