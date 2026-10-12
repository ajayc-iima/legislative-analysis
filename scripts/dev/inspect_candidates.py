import csv
import json
from pathlib import Path
import numpy as np

repo = Path(__file__).resolve().parent.parent.parent

import sys
sys.path.insert(0, str(repo / "packages/analysis/src"))

from legislative_analysis import analysis as base
from legislative_analysis.codebook import normalize_dept
from legislative_analysis.semantic_subjects import (
    load_embed_cache, check_deterministic_match, cosine_sim
)

cache = load_embed_cache()
with open(repo / 'data/dl_questions_raw.csv', encoding='utf-8') as f:
    rows = base.scope_rows(list(csv.DictReader(f)))

for dept in ['Education', 'Health & Family Welfare', 'Public Works (Roads)']:
    dept_rows = [r for r in rows if normalize_dept(r.get('Departments')) == dept]
    subs = sorted(list(set(base.subject_of(r) for r in dept_rows if base.subject_of(r))))
    pairs = []
    for i in range(len(subs)):
        v1 = np.array(cache.get(subs[i], []))
        if len(v1) == 0: continue
        for j in range(i+1, len(subs)):
            v2 = np.array(cache.get(subs[j], []))
            if len(v2) == 0: continue
            sim = cosine_sim(v1, v2)
            if sim >= 0.84:
                det = check_deterministic_match(subs[i], subs[j])
                pairs.append((sim, subs[i], subs[j], det))
    pairs.sort(reverse=True)
    print(f'=== {dept} (Pairs >= 0.84: {len(pairs)}) ===')
    for sim, s1, s2, det in pairs[:10]:
        print(f'  [{sim:.3f}] "{s1}" <=> "{s2}" (Det: {det[0] if det else None})')
    print()
