import sys, csv
from pathlib import Path
repo = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo / 'scripts'))
sys.path.insert(0, str(repo / 'packages/analysis/src'))

from legislative_analysis import analysis as base
from legislative_analysis.codebook import normalize_dept
from legislative_analysis import semantic_subjects as sem
from build_compendium import load_extracted
from legislative_analysis.longitudinal import session_order_of

with open(repo / 'data/dl_questions_raw.csv', encoding='utf-8') as f:
    rows = base.scope_rows(list(csv.DictReader(f)))

extracted = load_extracted()
order = session_order_of(rows)

for target_dept in ['Health & Family Welfare', 'Public Works (Roads)']:
    dept_rows = [r for r in rows if normalize_dept(r.get('Departments')) == target_dept]
    res = sem.build_semantic_pipeline(dept_rows, extracted, order)
    print(f"=== {target_dept} ===")
    print(f"Total recurring families: {res['n_families']}")
    for k, fam in list(res['families'].items())[:8]:
        print(f"  - {fam['subject']} ({fam['occurrences']} questions, {len(fam['sessions'])} sessions)")
        print(f"    Trajectory: {fam['trajectory']}")
        print(f"    Variants: {fam['unique_subjects'][:4]}")
    print()
