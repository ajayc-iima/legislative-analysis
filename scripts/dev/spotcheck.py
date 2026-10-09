"""Spot-check classifier output on a random sample."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "packages/analysis/src"))

from legislative_analysis import analysis as base
from legislative_analysis.codebook import classify_all
from legislative_analysis.geography import tag_all
from legislative_analysis.demand import classify_all as classify_demand_all

rows = base.load("data/dl_questions_raw.csv")
classify_all(rows, base.subject_of)
tag_all(rows, base.subject_of)

seen = {}
for r in rows:
    key = base.normalize_subject(base.subject_of(r))
    seen.setdefault(key, set()).add((r.get("Assembly"), r.get("Session")))
rec = {k for k, v in seen.items() if len(v) >= 2}
classify_demand_all(rows, base.subject_of, rec)

random.seed(7)
for r in random.sample(rows, 12):
    print(f"[{r['_theme']} / {r['_sub_theme']}] ({r['_demand_type']}) {r['_mla_constituency']}")
    print("   ", (base.subject_of(r) or "")[:110])
