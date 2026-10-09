"""Verify known-police/crime subjects still classify Law & Order."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "packages/analysis/src"))

from legislative_analysis import analysis as base
from legislative_analysis.codebook import classify

WANT_LAW = ["police outpost", "theft cases", "drug trafficking",
            "police out posts", "fire and emergency service"]
WANT_OTHER = ["fire and emergency services station at rajabala",
              "scheme for expansion and modernization of fire services"]

rows = base.load("data/dl_questions_raw.csv")
checked = 0
for r in rows:
    s = base.subject_of(r).lower()
    for probe in WANT_LAW + WANT_OTHER:
        if s.startswith(probe):
            t, st, _ev = classify(base.subject_of(r), r.get("Questions"),
                                  r.get("Departments"))
            flag = "OK " if (t == "Law & Order") == (probe in WANT_LAW) else "?? "
            print(f"{flag} [{t} / {st}] {base.subject_of(r)[:70]}")
            checked += 1
print(f"checked {checked}")
