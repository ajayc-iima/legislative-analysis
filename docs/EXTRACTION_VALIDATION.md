# Extraction validation — reply texts (2021+ scope)

Companion to `VALIDATION.md` (scraper). This records how the
2,186 scoped reply PDFs were turned into reply texts and reply dates,
what was measured, what failed, and what remains flagged. All figures
are from the final run (2026-10-12); regenerable artefacts are cited.

## 1. Scope and completion

| Quantity | Value |
|---|---|
| Questions in scope (sittings from 2021) | 2,217 |
| Scoped reply PDFs (distinct `Document_Link` basenames) | 2,186 |
| Reply texts extracted | 2,186 / 2,186 (100.0%, 0 failed, 0 skipped) |
| Reply texts with content | 2,168 (99.2%) |
| Flagged-empty (text withheld or unreadable, reasons recorded) | 18 (0.8%) |
| Records carrying recovered dates but no text | 11 of the 18 (9 with both dates) |
| Package tests (`pytest packages`) | 148 passing |

All 417 pre-2021 rows of the CSV are excluded by scope (60 of them
carry reply PDFs); the extractor skips them before OCR
(`--from-year 2021`). Unparseable session dates are never dropped —
kept and counted.

## 2. Method

1. **Deterministic pass** — PyMuPDF text layer where trustworthy;
   OCR (NVIDIA nemotron-ocr-v1) where the layer is missing, too short,
   or detected as mojibake (symbol-soup ratio > 0.06).
2. **Layout split** — the portal's two-column layout (question left,
   reply right of 45% page width), with guarded fallbacks for
   single-column and short-reply pages (§4).
3. **Footer cut** — memo/signature block excluded at the first
   `Memo No.` / `Dated` / `Copy to` line below 35% page height.
4. **Three-reader consensus for dates** — ocr-v1 + parse + vision-11b,
   then a reasoning supervisor when no 2-of-N agreement; every winner
   passes mechanical gates (parseable, ordered, within ±120 days of
   the sitting date). Records carry `confidence` / `provenance`.
5. **Quarantine** — pages that mix bulletin/question material with
   answers are withheld to flagged-empty rather than stored
   (`scripts/quarantine_mixed.py`, `data/review/quarantine_list.csv`).
6. **Review sheet** — every flagged record is listed with its reason
   and PDF path in `data/review/FLAGGED_EMPTY.md` (built by
   `scripts/build_review_sheet.py`).

## 3. Date accuracy

- Hand-annotated truth set of 12 reply PDFs: **12/12 exact, 0
  confident errors** (`output/validation/`).
- 1,409 of 2,168 coded replies yield a trustworthy date pair (median
  7 days, P75 9). 76 pairs are flagged as untrustworthy and excluded
  from latency statistics but kept in the data.
- The reasoning supervisor was retained per team decision after 70+
  trials yielded 0 usable corrections (`output/validation/supervisor_trial*.json`);
  its verdicts remain recorded as provenance.

## 4. Layout recoveries (the "empty reply" work)

The first complete pass left 80 reply texts empty. Root cause was
layout, not connectivity (zero transport errors across ~260
OCR-backed files; blanks reproduced deterministically with the API
answering normally):

| Cause | Records | Fix |
|---|---|---|
| Single-column pages (every line straddles the gutter) | ~60 | gutter-guarded fallback: take full lines only when a majority straddle the split with enough characters |
| Short "Sir, …" replies left of the split | 9 | reply-marker fallback: ≥50% of lines carry "Sir" (question text essentially never does) |
| Single unpunctuated sentence line | 3 | sentence-shape rule (lowercase + terminal punctuation) |
| Mojibake text layers (broken font encoding) | 1 + 4 detected by corpus audit | gibberish detector in `page_data` → re-OCR |
| Genuinely dateless/empty scans | 8 | left flagged-empty — no rule can separate them from garbled question text |
| Mixed bulletin/answer pages | 5 + 5 quarantined | header skip + whole-page refusal |
| Dates found before the reply page was read | 1 | read on while reply text is still empty |

Net: 72 replies recovered from blank; 18 remain flagged-empty with
recorded reasons; zero question-substance contamination in any stored
reply (normalized audit of all 2,186 records plus full-text review
of every recovered take).

## 5. Incidents and hardening

- **D: volume dropout (Seagate external USB, twice).** First dropout
  silently skipped 178 PDFs (`if not matches: continue`, no counter).
  Hardened: misses now log to `extract_errors.jsonl`, print `[MISS]`
  and count in the run summary. All 178 re-processed.
- **Process death on volume loss** (interpreter lives on D:) now
  detectable via lock file + mtime; runs resume by basename.
- **Deduplication** — the JSONL is keyed one-record-per-PDF; verified
  2,186 unique keys, zero duplicates across every resume.
- **Deterministic order** — records sorted by PDF basename so the
  file is byte-stable; verified multiset-identical after sorting.

## 6. Backup trail

All extraction state is mirrored from C: (run directory) and the
repository history is bundled to C: after every session of work
(`extract_backup/`): full JSONL snapshots, the stripped-record lists
per pass, a git bundle, and the API key file. The source PDFs live on
D: only.

## 7. What remains open

- 18 flagged-empty records await human review (5 quarantine, 13
  refused as unreadable/inseparable). The review sheet lists each with
  its question, MLA, recovered dates and PDF path.
- Reply texts retain reply-document headers (answering-minister
  assignment, memo references) in 798 records; they identify the
  source and are documented, not stripped.
- Exact-match recurrence under-merges paraphrases by design
  (see `VALIDATION.md` §"Recurring-subject detection").