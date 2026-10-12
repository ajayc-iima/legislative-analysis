import json
import requests
from pathlib import Path

repo = Path(__file__).resolve().parent.parent.parent

with open(repo / '.env') as f:
    for line in f:
        if line.startswith('NVIDIA_API_KEY='):
            key = line.strip().split('=', 1)[1]

headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

pairs = [
    ("CUET Examinations", "CUET Exams", "Education"),
    ("Science and Commerce Collage at Mawphlang", "Science and Commerce College at Mawphlang", "Education"),
    ("Teachers of Government Lower Primary and Upper Primary Schools, East Jaintia Hills District", 
     "Teachers of Government Lower Primary and Upper Primary Schools, West Jaintia Hills District", "Education"),
    ("College of Architecture & Urban Planning, Tura", "College of Architecture and Urban Planning, Tura", "Education"),
    ("Tura Government Medical College", "Shillong Medical College", "Health & Family Welfare"),
    ("Condition of the PMGSY Road", "Status of Implementation of the PMGSY-P-III", "Public Works (Roads)"),
    ("Improvement and Renovation Roads Under PMGSY", "Flooding at NH-6, Jorabat", "Public Works (Roads)")
]

for s1, s2, dept in pairs:
    prompt = f"""You are an expert legislative auditor for the Meghalaya State Government.
You are evaluating whether two parliamentary question subjects refer to the EXACT SAME specific government project, institution, policy, or matter (i.e. a continuing longitudinal issue across assembly sessions), OR if they refer to different instances, different geographic locations, different districts, or different projects.

Department: {dept}
Subject A: "{s1}"
Subject B: "{s2}"

Rules:
1. If they differ in geographic location, district, or constituency (e.g. East Jaintia vs West Jaintia, Tura vs Shillong), they are NOT the same issue (same_issue: false).
2. If they differ only in spelling, acronyms, minor wording, or are progressive status updates on the same specific project/policy, they ARE the same issue (same_issue: true).

Respond with valid JSON:
{{"same_issue": true/false, "canonical_title": "...", "reason": "..."}}
"""
    payload = {
        'model': 'meta/llama-3.2-11b-vision-instruct',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens': 150
    }
    r = requests.post('https://integrate.api.nvidia.com/v1/chat/completions', json=payload, headers=headers)
    resp = r.json()
    content = resp['choices'][0]['message']['content'].strip()
    print(f"=== Pair: '{s1}' vs '{s2}' ===")
    print(content)
    print()
