"""Time the full consensus path on a PDF needing it."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "packages/extract/src"))

from legislative_extract import extract as E
from legislative_extract import nvidia

key = nvidia.load_key()

# a PDF whose deterministic pass misses at least one date
CANDIDATES = [
    "data/pdfs/assembly-11/autumn-session-2026/11_9_S_3960_V1_signed.pdf",
    "data/pdfs/assembly-11/autumn-session-2026/11_9_S_4142_V1_signed.pdf",
]

for pdf in CANDIDATES:
    if not Path(pdf).exists():
        print(f"missing: {pdf}")
        continue
    t0 = time.time()
    rec = E.extract_pdf(pdf, key, session_date="28/Aug/2026")
    dt_det = time.time() - t0
    print(f"{Path(pdf).name}: deterministic {dt_det:.1f}s "
          f"rdate={rec['reply_date'] or '?'} sdate={rec['submission_date'] or '?'} "
          f"review={rec['needs_review']}")
    if rec["reply_date"] and rec["submission_date"]:
        continue
    row = {"Session": "Autumn Session, 2026", "Session_Date": "28/Aug/2026",
           "Departments": "Education", "Asked_By": "Test", "Subject": "Test"}
    t0 = time.time()
    E.consensus_fill(pdf, key, rec, row)
    print(f"  consensus_fill {time.time() - t0:.1f}s "
          f"rdate={rec['reply_date'] or '?'} sdate={rec['submission_date'] or '?'} "
          f"conf={rec.get('confidence')} prov={rec.get('provenance')}")
