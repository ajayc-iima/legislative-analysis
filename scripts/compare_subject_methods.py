"""Exact-match vs semantic subject grouping, side by side.

Answers the question a Secretary will ask first: *what changes if you stop
comparing strings?* Written to be read by someone who disagrees with the
answer, so every claim is backed by the underlying records.

Writes:
    output/layers/subject_method_comparison.json   machine-readable
    data/review/subject_method_comparison.md       for human readers

Usage: python scripts/compare_subject_methods.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))
sys.path.insert(0, str(REPO / "scripts"))

from legislative_analysis.codebook import normalize_dept      # noqa: E402
from legislative_analysis import analysis as base              # noqa: E402

LAYERS = REPO / "output/layers"
OUT_MD = REPO / "data/review/subject_method_comparison.md"


def load(name: str) -> dict:
    path = LAYERS / name
    if not path.exists():
        raise SystemExit(f"missing {path} - run run_layers.py "
                         f"and build_semantic_clusters.py first")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    exact = load("layer5_resolution.json")
    semantic = load("layer5_semantic.json")

    ex_fams = exact["families"]
    se_fams = semantic["families"]

    # which exact families' questions fall inside each semantic family
    se_index: dict[str, set[str]] = defaultdict(set)
    for key, fam in se_fams.items():
        for number in fam.get("question_numbers", []):
            se_index[number.strip()].add(key)

    merged_into: dict[str, list[str]] = defaultdict(list)
    for qnum, keys in se_index.items():
        for k in keys:
            merged_into[k].append(qnum)

    # per-department counts
    rows_by_number = {}
    with open(REPO / "data/dl_questions_raw.csv", encoding="utf-8") as fh:
        import csv
        for row in csv.DictReader(fh):
            rows_by_number[str(row.get("Question_Number") or "").strip()] = row

    def dept_of(fam: dict) -> str:
        # both family sets must pass through the same normaliser: exact
        # families carry the raw portal string ("Health &  Family Welfare
        # Department"), semantic ones carry the canonical name, and
        # comparing them raw splits one department into two rows
        depts = fam.get("departments") or []
        if depts:
            return normalize_dept(depts[0])
        numbers = [n.strip() for n in fam.get("question_numbers", [])]
        for n in numbers:
            row = rows_by_number.get(n)
            if row:
                return normalize_dept(row.get("Departments"))
        return "—"

    ex_by_dept = Counter(dept_of(f) for f in ex_fams.values())
    se_by_dept = Counter(dept_of(f) for f in se_fams.values())
    q_by_dept = Counter()
    for row in rows_by_number.values():
        q_by_dept[normalize_dept(row.get("Departments"))] += 1

    # how many subject variants each semantic family absorbed
    absorbed = [len(f.get("unique_subjects", [])) for f in se_fams.values()]
    multi = [f for f in se_fams.values() if len(f.get("unique_subjects", [])) > 1]

    summary = {
        "exact": {
            "methodology": exact.get("methodology"),
            "n_families": exact.get("n_families"),
            "resolution_counts": exact.get("resolution_counts"),
        },
        "semantic": {
            "methodology": semantic.get("methodology"),
            "embed_model": semantic.get("embed_model"),
            "embed_dims": semantic.get("embed_dims"),
            "gate_model": semantic.get("gate_model"),
            "sim_threshold": semantic.get("sim_threshold"),
            "n_families": semantic.get("n_families"),
            "n_unresolved": semantic.get("n_unresolved"),
            "resolution_counts": semantic.get("resolution_counts"),
            "n_subjects_embedded": semantic.get("n_subjects_embedded"),
        },
        "families_that_absorbed_paraphrases": len(multi),
        "max_variants_in_one_family": max(absorbed) if absorbed else 0,
        "questions_matched_to_a_family": len(se_index),
    }

    # sensitivity: family count if the candidate band were tightened
    thresholds = semantic.get("sensitivity") or {}

    lines = []
    add = lines.append
    add("# Two ways of counting a recurring subject\n")
    add("Both columns come from the same corpus and the same replies. They "
        "differ only in how a question is matched to the one before it, and "
        "both are reproducible:\n")
    add("| | Exact normalised match | Semantic grouping (embeddings + gates) |")
    add("|---|---|---|")
    add(f"| Method | string equality after normalisation | "
        f"{semantic.get('embed_model')} ({semantic.get('embed_dims')}d) + "
        f"{semantic.get('gate_model')} |")
    add(f"| Families found (2+ sittings) | **{exact.get('n_families')}** | "
        f"**{semantic.get('n_families')}** |")
    add(f"| Trajectories | {exact.get('resolution_counts')} | "
        f"{semantic.get('resolution_counts')} |")
    add(f"| Candidate similarity threshold | n/a | "
        f"{semantic.get('sim_threshold')} |")
    add(f"| Pairs sent to a human | n/a | {semantic.get('n_unresolved')} |")
    add("")
    add(f"The semantic pass recovered "
        f"**{len(multi)} families** that exact matching split into separate "
        f"questions, absorbing up to **{max(absorbed) if absorbed else 0} "
        f"different phrasings** into one family.\n")

    add("## Where the two methods differ, by department\n")
    add("| Department | Questions | Exact families | Semantic families | "
        "Change |")
    add("|---|---|---|---|---|")
    depts = sorted({*ex_by_dept, *se_by_dept},
                   key=lambda d: -(se_by_dept[d] + ex_by_dept[d]))
    for d in depts[:22]:
        a, b = ex_by_dept[d], se_by_dept[d]
        if a == 0 and b == 0:
            continue
        add(f"| {d} | {q_by_dept.get(d, 0)} | {a} | {b} | "
            f"{'+' if b > a else ''}{b - a} |")
    add("")

    add("## The largest recoveries, with the evidence\n")
    add("Each row is one family exact matching could not see. The variants "
        "are the archive's own subject strings; a reader can check every "
        "merge against the question numbers listed beside it.\n")
    ranked = sorted(multi, key=lambda f: -len(f.get("unique_subjects", [])))
    add("| Family | Occurrences | Sittings | Variants merged | Trajectory |")
    add("|---|---|---|---|---|")
    for fam in ranked[:18]:
        title = fam["subject"][:64]
        variants = len(fam.get("unique_subjects", []))
        add(f"| {title} | {fam.get('occurrences')} | "
            f"{len(fam.get('sessions', []))} | {variants} | "
            f"{fam.get('trajectory')} |")
    add("")
    add("### Worked examples (the three largest recoveries)\n")
    for fam in ranked[:3]:
        add(f"**{fam['subject']}** — {fam.get('occurrences')} questions across "
            f"{len(fam.get('sessions', []))} sittings, trajectory "
            f"`{fam.get('trajectory')}`\n")
        for variant in fam.get("unique_subjects", [])[:6]:
            add(f"- {variant}")
        add("")
        for edge in (fam.get("verified_edges") or [])[:3]:
            add(f"- merged \"{edge['s1']}\" ↔ \"{edge['s2']}\" "
                f"(cosine {edge.get('sim')}) — {edge.get('reason')}")
        add("")

    if thresholds:
        add("## Sensitivity to the similarity threshold\n")
        add("Tightening the candidate band changes how many paraphrases are "
            "admitted:\n")
        add("| Threshold | Families |")
        add("|---|---|")
        for tau, count in sorted(thresholds.items()):
            add(f"| {tau} | {count} |")
        add("")

    add("## What neither method can do\n")
    add("- Neither can tell whether a department *acted*. Both count what "
        "was asked and what came back.\n"
        "- Exact matching never merges paraphrases, so it understates "
        "recurrence; semantic grouping can over-merge if a verification is "
        "wrong. Both failure modes are visible in the tables above rather "
        "than hidden in one headline number.\n"
        "- Subject strings are the portal's own text. Where the portal "
        "records no subject, neither method groups that question.\n"
        "- Any merge can be challenged: `output/layers/layer5_semantic.json` "
        "keeps the variants, the question numbers and the reason for every "
        "decision, and `data/cache/gate_verifications.json` keeps the "
        "verification record.\n")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    (LAYERS / "subject_method_comparison.json").write_text(
        json.dumps({"summary": summary,
                    "by_department": {
                        "exact": dict(ex_by_dept), "semantic": dict(se_by_dept),
                        "questions": dict(q_by_dept)}},
                   indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"exact families:    {exact.get('n_families')}")
    print(f"semantic families: {semantic.get('n_families')}")
    print(f"families absorbing paraphrases: {len(multi)}")
    print(f"wrote {OUT_MD.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
