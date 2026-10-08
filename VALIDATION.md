# Scraper validation

The `packages/scraper` (plain HTTP) was cross-checked against the legacy
Selenium-based scraper's master CSV
(`Legislative Preparedness/data/dl_questions.csv`, 1,900 rows, sessions
2021–2026) and against the live portal. Date: 2026-10-08.

## Method

For the 10 sessions both scrapes cover, rows were matched on
(session, sitting date, question number). Every disagreement was then
re-queried live from the portal's search endpoint.

## Result: 99.58% agreement

- old rows (shared sessions): 1,900 — new: 1,906 — matched: 1,892
- old-only: 8 · new-only: 14 · duplicates in either: 0

### The 14 new-only rows (old scraper missed them)

Budget Session, 2021, 08–09 Mar 2021, Q.No 1–14. The old Selenium run
recorded only Q.No 15+ (and Q.No 74, 75, …) for those dates; the portal
serves Q.No 1–14 as well. Confirmed live: 08/Mar/2021 has Q1–13,
09/Mar/2021 has Q14+. These are a scraper-completeness win for the new
version — the old run's dropdown/pagination handling skipped the first
page of those dates.

### The 8 old-only rows (verified against the live portal)

7 of 8 do not exist on the portal on any date of their session (checked
every sitting date):

| Session | Q.No | Old date | Live portal |
|---|---|---|---|
| Autumn 2022 | 119 | 16-Sep-22 | absent all dates |
| Autumn 2023 | 190 | 22-Sep-23 | absent all dates |
| Budget 2022 | 93 | 14-Mar-22 | absent all dates |
| Budget 2023 | 85 | 28-Mar-23 | absent all dates |
| Budget 2023 | 80 | 28-Mar-23 | absent all dates |
| Budget 2023 | 47 | 24-Mar-23 | absent all dates |
| Autumn 2022 | 74 | 16-Sep-22 | exists on 14-Sep-22 only, under a different subject |

Two Q.No 74s exist in the old file: the 14-Sep row (subject "Dalupara
Government L.P. School") matches the portal; the 16-Sep row (subject "New
Assembly Building") has no counterpart on the portal — the same number was
recorded twice with different subjects. Conclusion: the old Selenium
scrape contained a small number of phantom/mis-dated rows; the new scrape
matches the portal.

## Known source-data quirks (not scraper errors)

Both were verified live — the portal itself serves these:

1. **Budget 2018, 20 Mar:** Q.No 1–5 are served twice (Sr No 1–5 and
   6–10, identical subjects, asker spelled two ways). Historical data
   entry duplication in NeVA.
2. **Autumn 2020, 09 Nov:** two different Q.No 9 rows (different subjects,
   different askers, Sr No 19 and 20).
3. **One row** (Autumn 2020, 10 Nov) has no subject in the portal.

The analysis package flags all three as "data notes" in its report
rather than silently dropping them.

## Coverage boundaries of this validation

- Sessions covered by both scrapes: 10 (2021–2026). The new scrape's
  additional 6 sessions (2018–2020, and Autumn 2026) have no Selenium
  counterpart to compare against.
- The comparison key is (session, date, question number). Rows could in
  principle match on the key while differing in subject text; spot checks
  found identical text wherever compared.

## Completeness audit (portal vs scrape)

Every session the portal lists for assemblies 10 and 11 was checked
against the scrape (2026-10-08):

| Assembly | Sessions on portal | With scraped questions | Without |
|---|---|---|---|
| 11th | 9 | 8 | Special Session, 2023 |
| 10th | 12 | 7 | Re-Assembled Budget 2020, Autumn 2021, Budget 2020, Special 2018 |

The 5 sessions without questions return "No Records Founds." from the
portal itself on every sitting date — no questions are published there.
So the scrape captures 100% of what the portal serves for both
assemblies.

## Recurring-subject detection vs the old pipeline

The analysis package's exact-match recurring detection was compared
against the old pipeline's `recurring_families.json` (LLM-labelled
semantic + exact families), 2026-10-08:

- Every one of the old pipeline's exact-type families is found by the
  simple matcher (37/37 when normalized; 21 with identical session
  counts, 7 with more sessions, **0 with fewer**).
- The old pipeline missed 41 exact recurrences inside its own session
  scope (e.g. "tura medical college" across 3 sessions) and split some
  subjects across families — its semantic layer merged some subjects
  while normalisation gaps dropped others.
- Example: "Eklavya Model Residential Schools" — the simple matcher
  finds 8 questions across 7 sessions (2021–2026, 6 askers); the old
  output reported 2 sessions. Verified row-by-row in the scraped CSV.
- The old pipeline's 104 semantic-only families (subject text differs
  between occurrences) are not reproduced, by design: exact matching
  never merges different text, so it cannot over-merge. This under-merges
  paraphrases (e.g. "medical college" vs "tura medical college" count
  separately) — a documented trade-off for verifiability.


