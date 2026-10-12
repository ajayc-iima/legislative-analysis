import json
from pathlib import Path

repo = Path(__file__).resolve().parent.parent.parent

with open(repo / 'output/layers/semantic_clusters.json', encoding='utf-8') as f:
    d = json.load(f)

print('Generated at:', d.get('generated_at'))
print('Model embedding:', d.get('model_embedding'))
print('Model verification gate:', d.get('model_verification_gate'))
print('Total clusters:', d.get('n_clusters'))
print('Total recurring families:', d.get('n_families'))
print('Resolution trajectory breakdown:', d.get('resolution_counts'))

print('\nTop 15 Cross-Session Recurring Families:')
rec = [c for c in d['clusters'] if c['n_sessions'] >= 2]
rec.sort(key=lambda c: (-c['occurrences'], -c['n_sessions']))
for c in rec[:15]:
    print(f"[{c['department']}] {c['canonical_subject']} ({c['occurrences']} questions across {c['n_sessions']} sessions)")
    if len(c['unique_subjects']) > 1:
        print(f"   Variants ({len(c['unique_subjects'])}): {c['unique_subjects'][:4]}")
    if c.get('verified_edges'):
        e = c['verified_edges'][0]
        print(f"   Proof edge ({e['sim']}): '{e['s1']}' <=> '{e['s2']}' [{e['reason']}]")
    print()
