# Execution Plan: From OCR Extraction to Journal Article

> **Superseded scope note (2026-10-12).** This plan was written for the
> pre-restriction corpus (2,634 questions, 16 sessions, 85.3% reply
> coverage). The delivered corpus is scoped to sittings from 2021:
> **2,217 questions, 11 sessions, 2,186/2,186 scoped reply PDFs
> (98.6% question coverage, 18 flagged-empty with recorded reasons)**.
> Phase/status numbers below describe the original plan; for current
> figures see `docs/ARTICLE_SCAFFOLD.md` §6 and `output/report/index.html`.

## Overview
This plan details the seven-phase execution to transform the validated Legislative Analysis dataset into a three-pillar Compendium and peer-reviewed journal article.

## Current State

### What We Have ✅
- **Dataset**: 2,634 questions, 16 sessions, 2,246 reply PDFs (85.3% coverage)
- **Pipeline**: OCR extraction with consensus fallback (NVIDIA OCR v1, 0.937 accuracy)
- **Analysis**: Basic descriptive stats, recurring subjects, reply coverage
- **Reference Data**: Geographic and taxonomic lookup tables from legacy pipeline

### What the Compendium Needs ❌
Six analytical layers to add to descriptive data:

1. **Thematic classification** - Policy domain coding of questions
2. **Geographic tagging** - Place name extraction and mapping
3. **Demand-type taxonomy** - Question classification by intent
4. **Response quality coding** - Rubric-based assessment of replies
5. **Longitudinal tracking** - Cross-session issue resolution
6. **Trend analysis** - Rising/declining patterns and projections

## Execution Timeline (4-5 Week Sprint)

### Week 1: Foundation Setup
**Phase 0 Parallel Tasks**:
- Task 0.1: OCR extraction run (15 hrs compute, resume-friendly)
- Task 0.2: Port reference data from legacy (1 day coding)

**Dependencies**: NVIDIA_API_KEY, reference_data.py output

### Week 2: Question-Side Analysis
**Phase 1 Tasks**:
- Task 1.1: Thematic classification (dictionary-based with fallback)
- Task 1.2: Geographic tagging (MLA-based + gazetteer)
- Task 1.3: Demand-type taxonomy (4-type classification)

**Validation**: Random sample verification, inter-coder reliability

### Week 3: Reply-Side Analysis  
**Phase 2 Tasks**:
- Task 2.1: Response pattern coding (substantiveness, specificity, assurance/evasion)
- Task 2.2: Evidence and contradiction detection (regex-based)
- Task 2.3: Reply timeliness analysis

**Dependencies**: Phase 0 (OCR extraction)

### Week 4: Longitudinal Analysis
**Phase 3 Tasks**:
- Task 3.1: Resolution tracking (cross-session outcome coding)
- Task 3.2: Trend analysis (departmental, thematic, temporal patterns)
- Task 3.3: Emerging issues identification (forecasting)

**Dependencies**: Phases 1 & 2

### Week 5: Compendium & Article Development
**Phase 4 Tasks**:
- Task 4.1: Compendium synthesis (three-pillar structure)
- Task 4.2: Visualization plan (chart catalog)

**Phase 5 Tasks**:
- Task 5.1: Analytical argument development
- Task 5.2: Literature review integration
- Task 5.3: Submission preparation (MBDA coordination)

## Execution Details

### Phase 0: Foundation

#### Task 0.1 - OCR Extraction Run
```python
# Configuration
table_name = "dl_questions_raw"
output_dir = "data/extracted"
pdf_root = "data/pdfs"
key = "NVIDIA_API_KEY"
limit = 0  # All PDFs

# Execution
for row in csv.DictReader(open(csv_path, encoding='utf-8-sig')):
    pdf_path = Path(pdf_root) / row.get('Document_Link', '')
    if not pdf_path.exists():
        continue
        
    # Extract with deterministic methods
    record = extract_pdf(str(pdf_path))
    
    # Try consensus for missing dates
    if not record.get('reply_date') or not record.get('submission_date'):
        readings = run_consensus(key, pdf_path, row)
        record.update(apply_consensus_results(readings))
        
    # Write to JSONL
    with open(output_dir / 'extracted.jsonl', 'a') as f:
        f.write(json.dumps(record) + '\n')
```

#### Task 0.2 - Port Reference Data
```python
# Geographic reference tables
MLA_DB = load_from_legacy('mgla_data.py', lines=500-700)
CONSTITUENCY_DISTRICT = load_from_legacy('mgla_data.py', lines=500-600)  
DISTRICT_REGION = load_from_legacy('mgla_data.py', lines=600-700)

# Taxonomic tables  
DEPT_ALIASES = load_from_legacy('mgla_data.py', lines=170-270)
DEPT_TAXONOMY = load_from_legacy('mgla_data.py', lines=280-310)

# Save new module
with open('packages/analysis/src/legislative_analysis/reference_data.py', 'w') as f:
    f.write(generate_module(MLA_DB, CONSTITUENCY_DISTRICT, DISTRICT_REGION, DEPT_ALIASES, DEPT_TAXONOMY))
```

### Phase 1: Question-Side Analysis

#### Task 1.1 - Thematic Classification
```python
# Theme hierarchy (from legacy)
TOP_LEVEL_THEMES = [
    "Health & Medical Services",
    "Education & Schools", 
    "Roads & Infrastructure",
    "Energy & Power",
    "Water & Sanitation",
    "Law & Order",
    "Rural & Community Development",
    "Urban Development",
    "Governance & Administration",
    "Environment & Natural Resources",
    "Social Welfare",
    "Economy & Commerce"
]

# Sub-themes mapping
SUB_THEMES = {
    "Health": ["PHC/CHC Facilities", "Medical Staffing", "Drug/Substance Abuse", "Scheme Implementation"],
    "Education": ["School Infrastructure", "Teacher Staffing", "Curriculum/Assessment", "Private Schools"],
    # ... more mappings
}

# Classification function
def classify_theme(subject_text, question_text):
    # Rule-based matching with keyword patterns
    combined = (subject_text or "") + " " + (question_text or "")
    
    # Check for exact matches
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword.lower() in combined.lower() for keyword in keywords):
            return theme, get_subtheme(theme, combined)
    
    # Fallback to manual classification
    return manual_classify(combined)
```

#### Task 1.2 - Geographic Tagging
```python
# MLA-based mapping
MLA_TO_CONSTITUENCY = {}
for mla_name, constituency in reference_data.MLA_DB.items():
    mla_name_normalized = normalize_text(mla_name)
    MLA_TO_CONSTITUENCY[mla_name_normalized] = {
        'constituency': constituency,
        'district': reference_data.CONSTITUENCY_DISTRICT[constituency],
        'region': reference_data.DISTRICT_REGION[reference_data.CONSTITUENCY_DISTRICT[constituency]]
    }

# Gazetteer extraction
GAZETTEER = load_place_names()  # district, towns, blocks

def extract_geography(subject_text, question_text):
    combined = (subject_text or "") + " " + (question_text or "")
    
    # District-level mentions
    districts = []
    for district in GAZETTEER['districts']:
        if district.lower() in combined.lower():
            districts.append(district)
    
    # MLA-based assignment
    mla_info = identify_mla(subject_text)  # from Asked_By field
    mla_location = MLA_TO_CONSTITUENCY.get(mla_info['normalized_name'])
    
    return {
        'mla_constituency': mla_info['constituency'],
        'mla_district': mla_info['district'],
        'mla_region': mla_info['region'],
        'mentioned_places': find_place_mentions(combined, GAZETTEER),
        'mentioned_districts': districts
    }
```

#### Task 1.3 - Demand-Type Taxonomy
```python
# Demand type patterns
DEMAND_PATTERNS = {
    'Information': [
        r'how many',
        r'total number',
        r'count of',
        r'number of',
        r'amount of',
        r'what is the status'
    ],
    'Explanation': [
        r'why',
        r'reasons for',
        r'cause of',
        r'factors contributing'
    ],
    'Action': [
        r'whether.*will',
        r'steps taken',
        r'action.*taken',
        r'decision.*made',
        r'plan to'
    ],
    'Accountability': [
        r're-opened',
        r'previous.*commitment',
        r'prior.*pledge',
        r're-view'
    ]
}

def classify_demand(question_text):
    for demand_type, patterns in DEMAND_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, question_text, re.IGNORECASE):
                return demand_type
    
    # Fallback heuristics
    if 'answer' in question_text.lower():
        return 'Information'
    return 'Unclassified'
```

### Phase 2: Reply-Side Analysis

#### Task 2.1 - Response Pattern Coding
```python
# Response quality dimensions
QUALITY_DIMENSIONS = {
    'substantiveness': {'brief': 200, 'standard': [200, 500], 'detailed': [500, 1500], 'very_detailed': 1500},
    'specificity': {
        'high': ['\d+', '\$\d+', 'scheme', 'programme', 'date', 'deadline'],
        'medium': ['some', 'several', 'many'],
        'low': []
    },
    'assurance_signals': load_regex_patterns('signals'),
    'evasion_signals': load_regex_patterns('evasion'),
    'action_indicators': ['timeline', 'responsible_party', 'budget_allocation', 'sanctioned']
}

def code_response_quality(reply_text, department_context=None):
    dimensions = {}
    
    # Substantiveness
    text_length = len(reply_text)
    dimensions['substantiveness'] = categorize_length(text_length, QUALITY_DIMENSIONS['substantiveness'])
    
    # Specificity  
    specificity_score = count_data_points(reply_text)
    dimensions['specificity'] = categorize_specificity(specificity_score)
    
    # Assurance vs Evasion
    assurance_count = count_pattern_matches(reply_text, QUALITY_DIMENSIONS['assurance_signals'])
    evasion_count = count_pattern_matches(reply_text, QUALITY_DIMENSIONS['evasion_signals'])
    dimensions['assurance_count'] = assurance_count
    dimensions['evasion_count'] = evasion_count
    
    # Actionability
    action_indicators = detect_action_items(reply_text)
    dimensions['actionability'] = {
        'has_timeline': 'timeline' in action_indicators,
        'has_responsible': 'responsible_party' in action_indicators,
        'has_budget': 'budget_allocation' in action_indicators,
        'has_sanction': 'sanctioned' in action_indicators
    }
    
    return dimensions
```

#### Task 2.2 - Evidence and Contradiction Detection
```python
# Contradiction patterns
CONTRADICTION_PATTERNS = {
    'positive_claims': load_regex_patterns('positive'),
    'negative_qualifiers': load_regex_patterns('negative'),
    'subject_reference': load_subject_patterns()
}

def detect_contradictions(reply_text, subject):
    # Split into paragraphs
    paragraphs = reply_text.split('\n\n')
    contradictions = []
    
    for para in paragraphs:
        has_positive = any(pattern in para.lower() for pattern in CONTRADICTION_PATTERNS['positive_claims'])
        has_negative = any(pattern in para.lower() for pattern in CONTRADICTION_PATTERNS['negative_qualifiers'])
        
        if has_positive and has_negative:
            # Check if they reference the same subject
            if subject_in_text(para, subject):
                contradictions.append({
                    'paragraph': para,
                    'positive_indicators': identify_positive(para),
                    'negative_indicators': identify_negative(para)
                })
    
    return contradictions
```

#### Task 2.3 - Reply Timeliness
```python
def analyze_timeliness(extracted_data):
    """Analyze response latency from date extraction"""
    
    timely_responses = []
    late_responses = []
    incomplete_responses = []
    
    for record in extracted_data:
        if not record.get('reply_date') or not record.get('submission_date'):
            incomplete_responses.append(record)
            continue
            
        reply_date = parse_date(record['reply_date'])
        submission_date = parse_date(record['submission_date'])
        
        if reply_date and submission_date:
            latency_days = (reply_date - submission_date).days
            
            if latency_days <= 30:
                timely_responses.append({
                    **record,
                    'latency_days': latency_days,
                    'category': 'timely'
                })
            elif latency_days <= 90:
                late_responses.append({
                    **record,
                    'latency_days': latency_days,
                    'category': 'moderately_late'
                })
            else:
                late_responses.append({
                    **record,
                    'latency_days': latency_days,
                    'category': 'very_late'
                })
    
    return {
        'timely': timely_responses,
        'late': late_responses,
        'incomplete': incomplete_responses,
        'coverage': {
            'complete': len(timely_responses) + len(late_responses),
            'coverage_rate': (len(timely_responses) + len(late_responses)) / len(extracted_data) * 100
        }
    }
```

### Phase 3: Longitudinal Analysis

#### Task 3.1 - Resolution Tracking
```python
# Resolution criteria
RESOLUTION_INDICATORS = {
    'resolved': ['completed', 'operational', 'functional', 'sanctioned', 'approved', 'implemented'],
    'progressing': ['50%', 'half', 'quarter', 'funds released', 'allocated', 'sanction granted'],
    'stalled': ['same', 'similar', 'boilerplate', 'no change', 'still pending'],
    'regressed': ['problems', 'issues with claimed progress', 'backtracking', 'withdraw']
}

def track_resolution(family_id, session_records):
    """Track resolution status across sessions for a recurring family"""
    
    trajectories = []
    for session_num, record in enumerate(session_records):
        reply_text = record.get('reply', '')
        session_trajectory = assess_session_resolution(reply_text, session_num, RESOLUTION_INDICATORS)
        trajectories.append(session_trajectory)
    
    # Determine final resolution status
    final_status = determine_final_resolution(trajectories)
    
    return {
        'family_id': family_id,
        'sessions': session_records,
        'trajectories': trajectories,
        'final_resolution': final_status,
        'resolution_time': calculate_resolution_time(trajectories)
    }

def assess_session_resolution(reply_text, session_num, indicators):
    """Assess resolution for a single session"""
    
    # Clean and normalize text
    clean_text = clean_reply_text(reply_text)
    
    # Check for resolution keywords
    status = 'unknown'
    for status_type, keywords in indicators.items():
        for keyword in keywords:
            if keyword in clean_text.lower():
                status = status_type
                break
        if status != 'unknown':
            break
    
    return {
        'session': session_num,
        'status': status,
        'indicators_found': find_indicators(clean_text, indicators),
        'confidence': calculate_confidence(clean_text, indicators)
    }
```

#### Task 3.2 - Trend Analysis
```python
# Trend detection functions
def calculate_departments_trends(question_data, sessions):
    """Calculate department attention trends over time"""
    
    trends = {}
    for session in sessions:
        session_departments = {}
        for question in question_data:
            if question['session'] == session:
                dept = question['department']
                if dept not in session_departments:
                    session_departments[dept] = 0
                session_departments[dept] += 1
        
        # Calculate slopes
        dept_slopes = {}
        for dept, count in session_departments.items():
            trend_slope = calculate_slope(count, previous_session_count(dept, session))
            dept_slopes[dept] = trend_slope
        
        trends[session] = dept_slopes
    
    return trends

def identify_emerging_issues(question_data, subjects, threshold=2):
    """Identify subjects appearing for first time and showing growth"""
    
    # Track appearance patterns
    subject_sessions = {}
    for question in question_data:
        subject = question['subject']
        if subject not in subject_sessions:
            subject_sessions[subject] = []
        subject_sessions[subject].append(question['session'])
    
    # Identify emerging issues
    emerging = []
    for subject, sessions in subject_sessions.items():
        first_session = min(sessions)
        session_count = len(sessions)
        
        # Check if appearing in multiple MLAs
        mlas_for_subject = set(q['mla'] for q in question_data if q['subject'] == subject)
        mla_diversity = len(mlas_for_subject) > 1
        
        if session_count >= threshold and mla_diversity:
            emerging.append({
                'subject': subject,
                'first_session': first_session,
                'sessions': sessions,
                'occurrences': session_count,
                'mla_diversity': mla_diversity,
                'growth_rate': calculate_growth_rate(sessions)
            })
    
    return sorted(emerging, key=lambda x: x['first_session'])
```

### Phase 4: Compendium Synthesis

#### Task 4.1 - Compendium Structure
```markdown
# COMPENDIUM: Legislative Oversight in Meghalaya
# ═══════════════════════════════════════════════

## Executive Summary
- Key findings overview
- Data overview and methodology

## Part I: Patterns of Legislative Attention
### Chapter 1: Departmental Attention Landscape
- Question volume rankings
- Session span analysis
- MLA breadth metrics

### Chapter 2: Thematic Attention
- Policy domain distribution
- Theme × department cross-tabulation
- Starred vs unstarred analysis

### Chapter 3: Geographic Attention
- District/region-level maps
- Constituency-level analysis
- State-wide vs local questions

### Chapter 4: Sustained Attention
- Recurring subjects catalog
- Cross-session persistence
- Resolution tracking

## Part II: Dynamics and Quality of Legislative Oversight
### Chapter 5: Demand Types
- Information/Explanation/Action/Accountability distribution
- Cross-tab with departments and sessions

### Chapter 6: Trends Over Time
- Session-level volume trends
- Departmental attention shifts
- Starred vs unstarred evolution

### Chapter 7: Response Quality
- Substantiveness distributions
- Specificity analysis
- Assurance vs evasion patterns
- Boilerplate detection results
- Timeliness analysis (where data available)

### Chapter 8: Gaps and Contradictions
- Contradiction detection results
- Evidence gaps analysis
- Actionability assessment

## Part III: Persistent and Emerging Governance Challenges
### Chapter 9: Unresolved Issues
- Resolution tracking findings
- "Stalled issues" catalog
- Departmental performance comparison

### Chapter 10: Recurring Challenges
- Cross-session persistent subjects
- Departmental response difficulties

### Chapter 11: Emerging Issues and Anticipation
- Emerging issues watchlist
- Anticipatory analysis by department
- Preparedness recommendations

## Methodology Appendix
- Data sources and pipeline description
- Classification codebooks
- Validation results
- Limitations and caveats

## Data Appendix
- Full department rankings table
- Full MLA activity table
- Full recurring subjects catalog
- Session-level statistics
```

#### Task 4.2 - Visualization Plan
```python
# Chart generation specifications
CHART_SPECIFICATIONS = [
    {
        'id': 1,
        'title': 'Department Attention Landscape (Top 20)',
        'pillar': 'Pillar 1',
        'data_source': 'stats.json',
        'chart_type': 'bar_horizontal',
        'parameters': {
            'limit': 20,
            'include_share': True,
            'color_scheme': 'wb_palette'
        }
    },
    {
        'id': 2,
        'title': 'Department × Session Attention Heatmap',
        'pillar': 'P1/P2',
        'chart_type': 'heatmap',
        'parameters': {
            'x_axis': 'departments',
            'y_axis': 'sessions',
            'color_by': 'question_volume'
        }
    },
    # ... more charts
]

# Chart generation function
def generate_charts(chart_specs, data_sources):
    """Generate all compendium visualizations"""
    
    charts = {}
    for spec in chart_specs:
        chart_data = extract_chart_data(spec, data_sources)
        chart = create_chart(spec['chart_type'], chart_data, spec['parameters'])
        charts[spec['id']] = {
            'spec': spec,
            'data': chart_data,
            'chart': chart,
            'metadata': generate_chart_metadata(spec, chart_data)
        }
    
    return charts
```

### Phase 5: Journal Article

#### Task 5.1 - Analytical Argument Development
```python
# Analytical framework for journal article
ARTICLE_STRUCTURE = {
    'introduction': {
        'problem': 'Legislative questioning in subnational democracies: information extraction vs executive response',
        'puzzle': 'Does increased legislative attention improve governance outcomes?',
        'megahalaya_case': 'Meghalaya Assembly (2018-2026) provides rich dataset for testing theoretical expectations'
    },
    'literature_review': {
        'question_time': 'Information asymmetry literature',
        'subnational_governance': 'Decentralized accountability research',
        'legislative_capacity': 'Comparative parliamentary studies',
        'preparedness_gap': 'Novel contribution - measurable institutional readiness concept'
    },
    'methodology': {
        'data': '2,634 legislative questions, 2,246 reply PDFs, 85.3% coverage',
        'classification': 'Dictionary-based thematic and demand-type coding',
        'quality_assessment': 'Response quality rubric with regex-based detection',
        'validation': 'Random sampling verification, inter-coder reliability'
    },
    'findings': {
        'pillar1_analysis': 'Patterns of legislative attention distribution',
        'pillar2_analysis': 'Dynamics and quality of executive responses',  
        'pillar3_analysis': 'Persistent and emerging governance challenges'
    },
    'discussion': {
        'analytical_frame': 'Chosen framework (A-D from PLAN.md)',
        'implications': 'For legislative reform, executive practice, theory development',
        'limitations': 'Data coverage, classification challenges'
    }
}
```

## Technical Implementation Requirements

### Development Environment
```python
# Required Python packages
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import re
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Custom packages (to be created)
from packages.analysis.src.legislative_analysis import (
    reference_data,
    classifiers,
    quality_rubrics,
    longitudinal_tracker
)
```

### File Structure
```
/legislative-analysis
├── packages/
│   └── extract/
│       └── src/legislative_extract/  # Existing OCR pipeline
│   └── analysis/
│       └── src/legislative_analysis/  # New analysis code
├── data/
│   ├── extracted/                  # OCR extraction output
│   ├── reference/                  # Lookup tables
│   └── analysis/                   # Analysis results
├── output/
│   ├── charts/                     # Visualizations
│   └── compendium/                 # Final Compendium document
└── scripts/                        # Execution scripts
    ├── phase0_foundation.py
    ├── phase1_analysis.py
    ├── phase2_analysis.py
    ├── phase3_longitudinal.py
    ├── phase4_compendium.py
    └── phase5_article.py
```

### Reproducibility Requirements
```python
# Script header template
#!/usr/bin/env python3
"""
Execution script: Phase X - Task Y

Purpose: [Brief description of script purpose]
Dependencies: [List of required packages, data files]
Author: [Name]
Date: [Date]

Usage: python3 [script_name].py [parameters]

Key functions:
- [Function1]: [Purpose]
- [Function2]: [Purpose]

Validation:
- Input data validation: [method]
- Output quality checks: [method]
- Performance metrics: [metrics]
"""

# Main execution
if __name__ == '__main__':
    start_time = datetime.now()
    
    # Load configuration
    config = load_config('config.yaml')
    
    # Execute main pipeline
    results = execute_pipeline(config)
    
    # Save results
    save_results(results, config['output_dir'])
    
    # Log execution
    end_time = datetime.now()
    log_execution(start_time, end_time, results)
```

## Risk Management

### High-Risk Items
1. **OCR extraction accuracy** - Dependent on NVIDIA API
2. **Manual classification burden** - Fallback for automated methods
3. **Timeline adherence** - Parallel execution critical for deadline

### Mitigation Strategies
1. **OCR redundancy** - Multiple reader consensus, supervisor override
2. **Progressive validation** - Quality checks at each phase
3. **Parallel execution** - Phase 0 dependencies separated from main analysis
4. **Backup timelines** - Extra time allocated for manual tasks

### Quality Assurance
1. **Reproducibility verification** - Every number validated against source data
2. **Inter-coder reliability** - Random sample coding checks
3. **Code documentation** - Clear comments and documentation
4. **Testing** - Unit tests for all classification functions

## Conclusion

This execution plan provides a clear roadmap for transforming the validated Legislative Analysis dataset into a three-pillar Compendium and peer-reviewed journal article. The plan balances methodological rigor with practical execution, ensuring academic quality while meeting the tight timeline requirements.

The key to success is:
1. **Parallel execution** where possible (Phase 0 independent)
2. **Robust validation** at each step
3. **Clear documentation** of trade-offs
4. **Flexible adaptation** to unexpected challenges

The resulting Compendium and journal article will make a significant contribution to the literature on legislative oversight, executive accountability, and institutional preparedness in Indian subnational democracy.