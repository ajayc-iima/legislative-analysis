"""Semantic subject grouping (NVIDIA Nemotron-3-Embed-1b + multi-gate).

Writes its own artefacts and touches nothing the deterministic pipeline
produces:

    output/layers/layer5_semantic.json        semantic families + provenance
    output/layers/semantic_clusters.json       per-cluster detail
    data/review/semantic_adjudication.csv     pairs no gate could decide
    data/review/subject_method_comparison.md  exact vs semantic, side by side

The exact-match baseline (layer5_resolution.json) is produced by
run_layers.py and is never overwritten: a reader must always be able to see
both methods and what each one finds.

Usage:
    python scripts/build_semantic_clusters.py            # cached embeddings
    python scripts/build_semantic_clusters.py --fresh    # ignore gate cache
    python scripts/build_semantic_clusters.py --threshold 0.80
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))
sys.path.insert(0, str(REPO / "scripts"))

from legislative_analysis import analysis as base                    # noqa: E402
from legislative_analysis import semantic_subjects as sem             # noqa: E402
from legislative_analysis.longitudinal import session_order_of       # noqa: E402
from build_compendium import load_extracted                          # noqa: E402

LAYERS = REPO / "output/layers"
REVIEW = REPO / "data/review"


def write_adjudication_queue(pairs: list[dict], path: Path) -> None:
    """Human gate: pairs no automated gate could decide.

    Written as a review sheet in the same shape as FLAGGED_EMPTY.md, so it
    can be worked through with the same discipline: a person marks each pair
    same/different, and the answer is recorded with a date.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "department", "subject_a", "subject_b", "similarity",
            "why_unresolved", "decision_same_issue", "decided_by", "decided_on",
        ])
        w.writeheader()
        for pair in sorted(pairs, key=lambda p: (-p["similarity"], p["subject_a"])):
            w.writerow({**pair, "decision_same_issue": "", "decided_by": "", "decided_on": ""})
    md = path.with_suffix(".md")
    md.write_text(
        "# Subject pairs awaiting human adjudication\n\n"
        f"{len(pairs)} pairs reached the verification gate and could not be\n"
        "decided by any rule or by the verification model. They were **not\n"
        "merged**, and they are not counted in either the exact-match or the\n"
        "semantic family totals until someone records a decision here.\n\n"
        "How to work through this sheet:\n\n"
        "1. Read both subjects. They are paraphrases, not duplicates of each\n"
        "   other, which is why exact matching missed them.\n"
        "2. Decide **same issue** if they concern the same project, facility,\n"
        "   scheme or controversy. Decide **different** if they differ by\n"
        "   district, facility type, scheme, or incident.\n"
        "3. Record the decision and your name in the CSV. Re-running\n"
        "   `build_semantic_clusters.py` picks the decision up from the gate\n"
        "   cache on the next run.\n\n"
        f"Similarity threshold in force: {sem.SIM_CANDIDATE}\n\n"
        "| # | Department | Subject A | Subject B | Similarity | Why unresolved | Decision |\n"
        "|---|---|---|---|---|---|---|\n"
        + "\n".join(
            f"| {i} | {p['department']} | {p['subject_a']} | {p['subject_b']} | "
            f"{p['similarity']:.3f} | {p['reason']} | ☐ same ☐ different |\n".replace("\n", "")
            for i, p in enumerate(sorted(pairs, key=lambda p: (-p["similarity"], p["subject_a"])), 1))
        + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threshold", type=float, default=sem.SIM_CANDIDATE,
                    help="cosine at which a pair becomes a candidate")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore the cached gate decisions and re-verify")
    ap.add_argument("--limit", type=int, default=0,
                    help="only the N busiest departments (debugging)")
    args = ap.parse_args()

    if args.fresh:
        sem.save_gate_cache({})

    print("=== Loading scoped corpus and extracted replies ===")
    csv_path = REPO / "data/dl_questions_raw.csv"
    with open(csv_path, encoding="utf-8") as fh:
        rows = base.scope_rows(list(csv.DictReader(fh)))
    extracted = load_extracted()
    order = session_order_of(rows)
    print(f"  {len(rows):,} scoped questions across {len(order)} sittings; "
          f"{len(extracted):,} reply records")

    print(f"\n=== Semantic grouping: {sem.EMBED_MODEL} "
          f"({sem.EMBED_DIMS}d) + gates, candidate at cosine >= {args.threshold} ===")
    started = time.time()
    with requests.Session() as http:
        result = sem.build_semantic_pipeline(rows, extracted, order,
                                             sim_threshold=args.threshold, http=http)
    elapsed = time.time() - started

    print(f"  {result['n_subjects_embedded']:,} subjects embedded "
          f"({elapsed:.0f}s)")
    print(f"  clusters: {result['n_clusters']:,} | families (>=2 sittings): "
          f"{result['n_families']:,}")
    print(f"  trajectories: {result['resolution_counts']}")
    print(f"  pairs left for human adjudication: {result['n_unresolved']:,}")

    LAYERS.mkdir(parents=True, exist_ok=True)

    # --- 1. clusters, without the bulky row objects ---
    clean = []
    for c in result["clusters"]:
        copy = {k: v for k, v in c.items() if k != "rows"}
        copy["questions_meta"] = [
            {"question_number": r.get("Question_Number"),
             "assembly": r.get("Assembly"), "session": r.get("Session"),
             "asked_by": r.get("Asked_By"), "document_link": r.get("Document_Link")}
            for r in c.get("rows", [])
        ]
        clean.append(copy)

    (LAYERS / "semantic_clusters.json").write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "methodology": result["methodology"],
        "embed_model": result["embed_model"],
        "embed_dims": result["embed_dims"],
        "gate_model": result["gate_model"],
        "sim_threshold": result["sim_threshold"],
        "n_subjects_embedded": result["n_subjects_embedded"],
        "n_clusters": result["n_clusters"],
        "n_families": result["n_families"],
        "n_unresolved": result["n_unresolved"],
        "resolution_counts": result["resolution_counts"],
        "clusters": clean,
        "emerging_issues": result["emerging_issues"],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- 2. semantic families, in their own file ---
    (LAYERS / "layer5_semantic.json").write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "methodology": result["methodology"],
        "embed_model": result["embed_model"],
        "embed_dims": result["embed_dims"],
        "gate_model": result["gate_model"],
        "sim_threshold": result["sim_threshold"],
        "n_subjects_embedded": result["n_subjects_embedded"],
        "n_families": result["n_families"],
        "n_unresolved": result["n_unresolved"],
        "resolution_counts": result["resolution_counts"],
        "families": result["families"],
        # Emerging issues were previously only written to
        # semantic_clusters.json, so every consumer of this file read 0
        # emerging subjects no matter what the pipeline found.
        "emerging_issues": result["emerging_issues"],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- 3. human adjudication queue ---
    write_adjudication_queue(result["unresolved_pairs"],
                             REVIEW / "semantic_adjudication.csv")

    for name in ("semantic_clusters.json", "layer5_semantic.json"):
        p = LAYERS / name
        print(f"  wrote {p.relative_to(REPO)} ({p.stat().st_size/1024:.0f} KB)")
    print(f"  wrote data/review/semantic_adjudication.csv "
          f"({result['n_unresolved']} rows)")
    print("\nNext: python scripts/compare_subject_methods.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
