# Legislative Analysis

Monorepo for Meghalaya Legislative Assembly (NeVA) data work. Two small,
stdlib-first packages under `packages/`. Facts only — no composite scores,
no invented probabilities.

## Scraper

Downloads Digital Library questions (assemblies 10 and 11, all sessions)
into one CSV.

```bash
pip install -e packages/scraper
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
pip install -e packages/analysis
python -m legislative_analysis --csv data/dl_questions_raw.csv --out-dir output
```

Options: `--csv`, `--out-dir`, `--top` (rows per table, default 20).

### Why so small

The previous 24k-line pipeline produced composite indices
("readiness 92/100", "delivery probability") from hand-picked weights and
unvalidated LLM clusters. Those numbers appeared in reports but were never
back-tested and are not reproducible from the source data. This package
computes only what the data supports directly:

- counts, shares, distributions
- reply coverage (does a signed reply document exist)
- recurring subjects (same normalized subject across 2+ sessions)

Traps to avoid if extending: don't name weighted sums "probability" or
"score", don't rank departments by anything other than measured counts
without stating the weights, and keep every number reproducible from the
input CSV.

## Tests

```bash
python -m pytest
```

## Validation

`VALIDATION.md` records the scraper audit: 99.58% row agreement against
the legacy Selenium scrape on shared sessions, live-portal verification
of every disagreement, and a completeness check against all sessions the
portal lists for assemblies 10 and 11.

