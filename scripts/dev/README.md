# Development probes (one-off diagnostics, not the pipeline)

Run from the repo root. Each file is a single answered question:

| File | Question it answered |
|---|---|
| `spotcheck.py` | Do the Layer 1–3 classifiers behave on a random sample? |
| `check_law.py` | Did the token-matching fix keep real police/crime questions in Law & Order? |
| `check_dashboard.py` | Do all dashboard image references resolve? |
| `time_calls.py` | Per-call latency of ocr-v1 / parse / vision-11b (vision ≈ 20s is the bottleneck) |
| `time_consensus.py` | End-to-end cost of the consensus path on date-missing PDFs (~20–30s) |

Findings worth keeping are summarized in commit messages; the
probes themselves are retained so any measurement can be re-run.
