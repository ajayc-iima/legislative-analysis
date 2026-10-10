"""Spot-check bloc attribution on top askers + list unknowns."""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages/analysis/src"))

from legislative_analysis import analysis as base
from legislative_analysis.geography import bloc_of, party_of

rows = base.load("data/dl_questions_raw.csv")
askers = Counter((r.get("Asked_By") or "").strip() for r in rows)
for name, n in askers.most_common(8):
    print(f"{n:4d} {bloc_of(name, 'Eleventh Assembly'):10} "
          f"({party_of(name, 'Eleventh Assembly')}) {name[:40]}")
print("--- unknown askers (n>1) ---")
for name, n in askers.most_common():
    if n > 1 and bloc_of(name, "Eleventh Assembly") == "Unknown":
        print(f"{n:4d} {name[:50]}")
