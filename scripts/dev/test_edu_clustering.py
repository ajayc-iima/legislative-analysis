import csv
import json
import time
import requests
import numpy as np
from pathlib import Path
from legislative_analysis import analysis as base
from legislative_analysis.codebook import normalize_dept

repo = Path(__file__).resolve().parent.parent.parent

with open(repo / '.env') as f:
    for line in f:
        if line.startswith('NVIDIA_API_KEY='):
            key = line.strip().split('=', 1)[1]

with open(repo / 'data/dl_questions_raw.csv', encoding='utf-8') as f:
    rows = [r for r in base.scope_rows(list(csv.DictReader(f))) if normalize_dept(r.get('Departments')) == 'Education']

subjects = [base.subject_of(r) for r in rows]
unique_subs = sorted(list(set(subjects)))
print('Total Education questions:', len(rows))
print('Unique Education subjects:', len(unique_subs))

headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

embeddings = []
for i in range(0, len(unique_subs), 50):
    batch = unique_subs[i:i+50]
    payload = {'input': batch, 'model': 'nvidia/nemotron-3-embed-1b', 'input_type': 'passage'}
    r = requests.post('https://integrate.api.nvidia.com/v1/embeddings', json=payload, headers=headers)
    for item in r.json().get('data', []):
        embeddings.append(np.array(item['embedding']))

print('Total embeddings generated:', len(embeddings))

sims = []
for i in range(len(unique_subs)):
    for j in range(i + 1, len(unique_subs)):
        v1, v2 = embeddings[i], embeddings[j]
        cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
        if cos >= 0.70:
            sims.append((cos, unique_subs[i], unique_subs[j]))

sims.sort(reverse=True)
print(f'Pairs with similarity >= 0.70: {len(sims)}')
print('\nTop 25 most similar subject pairs in Education:')
for cos, s1, s2 in sims[:25]:
    print(f'[{cos:.3f}] "{s1}" <==> "{s2}"')
