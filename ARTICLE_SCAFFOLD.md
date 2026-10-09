# Journal Article Scaffold — Legislative Oversight in Meghalaya

> **Status**: scaffold for collective decision. Authorship, order,
> frame selection, and journal target are to be agreed among the
> research team; MBDA takes responsibility for submission and fees.
> This document develops the analytical argument, method, and
> structure so the Compendium findings can be carried into a
> peer-reviewed venue.

---

## 1. The contribution in one paragraph

Using the complete question record of the Meghalaya Legislative
Assembly across two assemblies (2,634 questions, 16 sessions,
2018–2026) and OCR-extracted replies to 2,246 of them, we show
that legislative questioning is a measurable instrument of
executive accountability at the subnational level, but that the
*quality* of the information executives return varies
systematically by department and over time. We introduce a
transparent, reproducible coding framework — thematic,
geographic, demand-type, response-quality, and longitudinal —
in which every dimension is reported separately and no composite
"readiness score" is constructed. We then use the framework to
define and measure the **preparedness gap**: the distance
between what legislators ask and what executives are ready to
answer, evidenced in boilerplate replies, internal
contradictions, evasion signals, and unresolved recurring
subjects.

---

## 2. Frame options (to be decided collectively)

| Frame | Core argument | Primary evidence | Novelty |
|---|---|---|---|
| **A. Information asymmetry** | Departments control the information environment through vague, boilerplate, or evasive replies, undermining the legislature's oversight function | Pillar 2: evasion/assurance patterns, boilerplate rates, specificity gaps | Moderate |
| **B. Institutional learning** | Repeated questioning can improve responses — but only when departments engage substantively; measure whether the same issue yields better answers over time | Pillar 3: resolution tracking, response evolution | Moderate |
| **C. Attention allocation** | The distribution of questions reveals systematic attention biases; some departments face disproportionate scrutiny while others operate with minimal oversight | Pillar 1: attention concentration, demand types, MLA behaviour | Moderate |
| **D. The preparedness gap** *(developed below)* | Develop a *measurable* concept of departmental preparedness without collapsing it into a single score; show how the gap varies across departments and over time | All three pillars | **High** |

**Recommendation**: Frame D, with A as the supporting mechanism.
D is the most novel because "preparedness" is asserted in
policy discourse but rarely measured; our corpus supplies the
first reproducible operationalisation from legislative questioning
data. A supplies the mechanism (information asymmetry) that
explains *why* the gap persists.

---

## 3. The preparedness gap (Frame D, developed)

### 3.1 Definition

The **preparedness gap** for a department–session is the
observable distance between a legislative demand and the
executive's capacity to answer it concretely. It is *not* a
score. It is a vector of separately reported dimensions:

| Dimension | Measured by | Direction |
|---|---|---|
| **Unanswered demand** | share of questions with no signed reply (coverage) | wider gap = lower coverage |
| **Vagueness** | boilerplate-reply rate; evasion-signal weight | wider gap = more boilerplate/evasion |
| **Unsubstantiated claims** | assurance-signal weight *without* budget/timeline/responsible-party commitment | wider gap = more bare assurances |
| **Internal inconsistency** | contradiction rate (completion claim + negative qualifier in one paragraph) | wider gap = more contradictions |
| **Thin evidence** | low-specificity rate (no numbers, dates, schemes, amounts) | wider gap = thinner evidence |
| **Slow response** | reply latency (submission → reply days) | wider gap = longer latency |
| **Persistent non-resolution** | share of recurring subjects whose latest reply shows no progress language | wider gap = more stalled families |

Each dimension is reported per department and per session. A
department is "less prepared" not because it scores low on a
weighted sum, but because it is *simultaneously* wide on several
dimensions — a pattern the reader can verify row by row.

### 3.2 Why this is defensible

The legacy pipeline's error was collapsing these dimensions into
weighted composites ("readiness scores", "delivery probability")
with arbitrary, unvalidated weights. Our framework refuses that.
The gap is a *profile*, not a number. This is also what makes it
publishable: the method is fully reproducible from the source
data, and the unit of analysis (department × session) is stable
across the two assemblies.

### 3.3 Hypotheses the data can test

- **H1 (attention concentrates on social sectors)**: Health,
  Education, and Roads receive disproportionate question volume
  relative to their budget share.
- **H2 (vagueness is departmental, not random)**: boilerplate
  and evasion rates cluster by department and persist across
  sessions.
- **H3 (repeated questioning yields improvement)**: recurring
  subjects whose replies are substantive in early sessions are
  more likely to show progress language later.
- **H4 (the gap widened/narrowed over time)**: dimension-level
  trends differ across the two assemblies and across the
  assembly transition.

---

## 4. Literature review skeleton

### 4.1 Question time as information extraction
- Parliamentary question time as a mechanism for extracting
  information from executives (classic legislative studies).
- The distinction between *asking* and *answering*; the
  executive's discretion over reply content.

### 4.2 Subnational legislative capacity in India
- State assemblies as under-studied oversight institutions;
  the NeVA digital library as a new data source.
- Meghalaya as a small, tribal, hill state — a case where
  executive accountability is institutionally consequential.

### 4.3 Response quality and institutional learning
- Do executives improve their answers when the same issue
  recurs? Evidence from legislative studies and public
  administration.
- Boilerplate and evasion as forms of non-answer.

### 4.4 The preparedness concept
- "Preparedness" in policy discourse (disaster, health,
  fiscal) vs. our legislative-information operationalisation.
- Gap: no prior work measures departmental preparedness from
  question–reply data.

---

## 5. Data and methods

### 5.1 Data
- Questions: NeVA Digital Library, 2,634 rows, 15 fields,
  Assemblies 10–11 (2018–2026), 16 sessions, 84 sitting dates.
- Replies: 2,246 signed PDFs (85.3% coverage), scanned images.
- OCR: NVIDIA nemotron-ocr-v1 with a three-reader consensus
  (ocr-v1 + parse + vision-11b); mechanical gates (parseable, ordered,
  within ±120 days of the sitting date) apply to every winner, and
  fields without agreement stay blank for the review queue (a reasoning
  supervisor was trialled and removed: 0 usable decisions in over 70 tries).
  Validated: 12/12 reply dates correct against hand-annotated
  truth; 0 confident errors.

### 5.2 Coding framework (six layers)
1. **Thematic** — 17 policy domains, keyword rules with
   department-sector tie-break; evidence recorded per row.
2. **Geographic** — MLA→constituency→district→region (60 seats,
   typo-tolerant) plus a gazetteer scan; scope flags
   (constituency-specific / place-specific / state-wide).
3. **Demand type** — Information / Explanation / Action /
   Accountability (the last structural: subject recurs).
4. **Response quality** — substantiveness, specificity,
   assurance/evasion signals, boilerplate, contradiction,
   actionability (timeline/budget/responsible party).
5. **Longitudinal** — recurring families (exact normalized
   match ≥2 sessions) with resolution trajectories
   (resolved / progressing / stalled / regressed).
6. **Trends** — departmental and thematic session-over-session
   deltas, new-vs-recurring ratio, MLA diversity index,
   emerging-issues watchlist.

### 5.3 Reproducibility
- Every figure is generated from `data/dl_questions_raw.csv`
  and `data/extracted/extracted.jsonl` by the open pipeline
  (`packages/analysis`, `packages/extract`). No composite
  scores; no LLM-generated probabilities. Codebooks and
  validation results are in the Methodology Appendix.

### 5.4 Limitations
- OCR accuracy is bounded (~0.94 per field); low-confidence
  extractions carry provenance flags.
- Exact-match recurrence under-merges paraphrases (documented
  trade-off; never over-merges).
- MLA-based geography assumes questions concern the asker's own
  seat; the gazetteer scan runs alongside it.
- Reply coverage is 85.3%; non-replies are themselves a
  preparedness signal (unanswered demand).

---

## 6. Findings (to be populated from the Compendium)

```
6.1 Patterns of attention (Pillar 1)
    - departmental concentration; thematic distribution;
      geographic distribution; sustained attention
6.2 Response quality (Pillar 2)
    - substantiveness, specificity, assurance vs evasion,
      boilerplate, contradictions, timeliness — by department
6.3 Resolution and learning (Pillar 3)
    - resolution trajectories; stalled issues; emerging watchlist
6.4 The preparedness gap (synthesis)
    - department-level gap profiles; session-level trends;
      which departments are wide on multiple dimensions
```

---

## 7. Discussion
- What the gap profiles reveal about executive–legislative
  information asymmetry in a small state.
- Implications for legislative reform (transparency of replies,
  follow-up mechanisms).
- Implications for departmental practice (concrete commitments,
  data-backed replies).
- Generalisability to other Indian states and small legislatures.

---

## 8. Conclusion

---

## 9. Candidate journals (per PLAN.md)

| Journal | Fit | Notes |
|---|---|---|
| *The Journal of Legislative Studies* | ★★★★★ | Directly on point |
| *Parliamentary Affairs* | ★★★★★ | Questions, oversight |
| *Governance* | ★★★★ | Institutional design, accountability |
| *Public Administration* | ★★★★ | Executive–legislative dynamics |
| *Commonwealth & Comparative Politics* | ★★★★ | Subnational, developing democracies |
| *Indian Journal of Public Administration* | ★★★★ | Indian context |
| *The Journal of Development Studies* | ★★★ | If framed around governance & development |

---

## 10. Open decisions for the team

1. **Frame**: D (preparedness gap) recommended; A as mechanism.
2. **Authorship & order**: to be agreed collectively.
3. **Journal target**: shortlist above; MBDA to submit.
4. **Semantic recurrence**: keep exact-match (documented
   under-merge) or add fuzzy matching (risks over-merge)?
5. **Thematic codebook**: start from the 17 legacy-derived
   domains or develop a fresh taxonomy?
6. **Demand taxonomy granularity**: four types, or refine?

---

*This scaffold is generated alongside the Compendium. Findings
sections populate automatically once the OCR extraction run
completes and `build_compendium.py` is re-run.*
