import requests
import json
from pathlib import Path

repo = Path(__file__).resolve().parent.parent.parent

with open(repo / '.env') as f:
    for line in f:
        if line.startswith('NVIDIA_API_KEY='):
            key = line.strip().split('=', 1)[1]

headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

test_cases = [
    ("CUET Examinations", "CUET Exams", "Education"),
    ("Teachers of Government Lower Primary and Upper Primary Schools, East Jaintia Hills District",
     "Teachers of Government Lower Primary and Upper Primary Schools, West Jaintia Hills District", "Education"),
    ("College of Architecture & Urban Planning, Tura", 
     "College of Architecture and Urban Planning, Tura", "Education"),
    ("Tura Government Medical College", "Shillong Medical College", "Health & Family Welfare"),
    ("Condition of the PMGSY Road", "Status of Implementation of the PMGSY-P-III", "Public Works (Roads)")
]

for s1, s2, dept in test_cases:
    prompt = f"""You are an expert legislative auditor for the Meghalaya Assembly.
Determine if Subject A and Subject B refer to the EXACT SAME specific government project or issue, or different ones.

Department: {dept}
Subject A: {s1}
Subject B: {s2}

If they differ by district, town, or project (e.g. East Jaintia vs West Jaintia, or Tura vs Shillong), they are NOT the same issue.
If they are spelling variations, abbreviations, or updates on the same scheme/facility, they ARE the same issue.

Reply JSON: {{"same_issue": true/false, "canonical_title": "...", "reason": "..."}}"""

    p = {
        'model': 'nvidia/nemotron-3.5-lightning-30b-a3b',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens': 120
    }
    resp = requests.post('https://integrate.api.nvidia.com/v1/chat/completions', json=p, headers=headers, timeout=10)
    print(f"=== {s1} vs {s2} ===")
    print(resp.json()['choices'][0]['message']['content'])
    print()
