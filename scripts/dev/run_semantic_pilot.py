import csv
import json
import time
import sys
from pathlib import Path

repo = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo / "scripts"))
sys.path.insert(0, str(repo / "packages/analysis/src"))

from legislative_analysis import analysis as base
from legislative_analysis.codebook import normalize_dept
from legislative_analysis import semantic_subjects as sem
from build_compendium import load_extracted
from legislative_analysis.longitudinal import session_order_of

repo = Path(__file__).resolve().parent.parent.parent

with open(repo / "data/dl_questions_raw.csv", encoding="utf-8") as f:
    rows = base.scope_rows(list(csv.DictReader(f)))

extracted = load_extracted()
order = session_order_of(rows)

print(f"Loaded {len(rows)} scoped rows.")

# Test on top 3 departments
top_3 = ["Education", "Health & Family Welfare", "Public Works (Roads)"]
sub_rows = [r for r in rows if normalize_dept(r.get("Departments")) in top_3]

print(f"Top 3 departments contain {len(sub_rows)} questions.")
t0 = time.time()
res = sem.build_semantic_pipeline(sub_rows, extracted, order)
t1 = time.time()

print(f"Done in {t1 - t0:.2f} seconds.")
print(f"Total clusters: {res['n_clusters']}")
print(f"Recurring families (>= 2 sessions): {res['n_families']}")
print(f"Resolution trajectory counts: {res['resolution_counts']}")

print("\n--- SAMPLE RECURRING FAMILIES FOUND ---")
for k, fam in list(res["families"].items())[:15]:
    print(f"[{fam['departments'][0]}] {fam['subject']}")
    print(f"   Occurrences: {fam['occurrences']}, Sessions: {fam['sessions']}")
    print(f"   Trajectory: {fam['trajectory']}, Variants: {fam['unique_subjects']}")
    if fam.get("verified_edges"):
        for edge in fam["verified_edges"][:2]:
            print(f"      Verified edge ({edge['sim']}): '{edge['s1']}' <=> '{edge['s2']}' ({edge['reason']})")
    print()
