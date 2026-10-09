"""Manual validation harness for Layers 1-3 (PLAN.md requirement).

Step 1 (now): draw a stratified 100-question sample and write a CSV
  with the automatic classifications plus empty manual_* columns.
Step 2 (human): fill the manual_* columns. A second coder fills
  manual2_* for the inter-coder check.
Step 3: `python scripts/validate_layers.py --score coded.csv`
  reports per-layer accuracy (auto vs manual) and Cohen's kappa
  (coder 1 vs coder 2). Stdlib only.

Usage:
  python scripts/validate_layers.py --sample 100 --seed 7
  python scripts/validate_layers.py --score output/validation/coded.csv
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))

from legislative_analysis import analysis as base
from legislative_analysis.codebook import classify_all
from legislative_analysis.geography import tag_all
from legislative_analysis.demand import classify_all as classify_demand_all

OUT_DIR = REPO / "output/validation"
SAMPLE_COLS = ["question_id", "assembly", "session", "department", "mla",
               "subject", "question_text",
               "auto_theme", "auto_sub_theme", "auto_demand",
               "auto_region", "auto_scope",
               "manual_theme", "manual_demand", "manual_scope",
               "manual2_theme", "manual2_demand", "manual2_scope",
               "notes"]


def draw_sample(n=100, seed=7):
    import random
    rows = base.load(str(REPO / "data/dl_questions_raw.csv"))
    classify_all(rows, base.subject_of)
    tag_all(rows, base.subject_of)
    seen = defaultdict(set)
    for r in rows:
        key = base.normalize_subject(base.subject_of(r))
        if len(key) >= base.MIN_SUBJECT_CHARS:
            seen[key].add((r.get("Assembly"), r.get("Session")))
    recurring = {k for k, v in seen.items() if len(v) >= 2}
    classify_demand_all(rows, base.subject_of, recurring)

    rng = random.Random(seed)
    by_theme = defaultdict(list)
    for i, r in enumerate(rows):
        by_theme[r["_theme"]].append((i, r))
    # proportional allocation, at least 1 per theme
    quota = {t: max(1, round(n * len(v) / len(rows))) for t, v in by_theme.items()}
    sample = []
    for theme, members in by_theme.items():
        sample += rng.sample(members, min(quota[theme], len(members)))
    # top up / trim to exactly n
    if len(sample) < n:
        rest = [(i, r) for i, r in enumerate(rows)
                if all(i != s[0] for s in sample)]
        sample += rng.sample(rest, n - len(sample))
    sample = rng.sample(sample, n)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "validation_sample.csv"
    with open(dest, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, SAMPLE_COLS)
        writer.writeheader()
        for i, r in sample:
            writer.writerow({
                "question_id": f"Q{i:04d}",
                "assembly": r.get("Assembly"), "session": r.get("Session"),
                "department": r.get("Departments"), "mla": r.get("Asked_By"),
                "subject": base.subject_of(r),
                "question_text": (r.get("Questions") or "")[:600],
                "auto_theme": r["_theme"], "auto_sub_theme": r["_sub_theme"],
                "auto_demand": r["_demand_type"], "auto_region": r["_mla_region"],
                "auto_scope": r["_scope"],
                "manual_theme": "", "manual_demand": "", "manual_scope": "",
                "manual2_theme": "", "manual2_demand": "", "manual2_scope": "",
                "notes": "",
            })
    print(f"sample of {n} -> {dest}")
    print("theme mix:", dict(Counter(r["_theme"] for _, r in sample).most_common()))


def cohens_kappa(a, b):
    """Kappa over paired labels (pairs with either side blank are skipped)."""
    pairs = [(x, y) for x, y in zip(a, b) if x and y]
    n = len(pairs)
    if not n:
        return 0.0, 0
    po = sum(1 for x, y in pairs if x == y) / n
    labels = sorted({x for x, _ in pairs} | {y for _, y in pairs})
    pe = sum((sum(1 for x, _ in pairs if x == L) / n) *
             (sum(1 for _, y in pairs if y == L) / n) for L in labels)
    return ((po - pe) / (1 - pe) if pe < 1 else 1.0), n


def accuracy(auto, manual):
    pairs = [(a, m) for a, m in zip(auto, manual) if m]
    if not pairs:
        return 0.0, 0
    return sum(1 for a, m in pairs if a == m) / len(pairs), len(pairs)


def score(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    print(f"scoring {len(rows)} coded rows from {path}")
    for layer, auto_col, man_col, man2_col in [
            ("theme", "auto_theme", "manual_theme", "manual2_theme"),
            ("demand", "auto_demand", "manual_demand", "manual2_demand"),
            ("scope", "auto_scope", "manual_scope", "manual2_scope")]:
        acc, n_acc = accuracy([r[auto_col] for r in rows],
                              [r[man_col] for r in rows])
        kap, n_kap = cohens_kappa([r[man_col] for r in rows],
                                  [r[man2_col] for r in rows])
        coded = sum(1 for r in rows if r[man_col])
        coded2 = sum(1 for r in rows if r[man2_col])
        print(f"[{layer}] auto-vs-manual accuracy: {acc:.3f} (n={n_acc}); "
              f"inter-coder kappa: {kap:.3f} (n={n_kap}); "
              f"coded: {coded}/{len(rows)} + {coded2}/{len(rows)}")
    # error analysis: where auto disagrees with manual
    print("\ntheme disagreements (auto -> manual):")
    disagree = Counter((r["auto_theme"], r["manual_theme"]) for r in rows
                       if r["manual_theme"] and r["auto_theme"] != r["manual_theme"])
    for (auto, man), c in disagree.most_common(10):
        print(f"  {c:3d}x  {auto} -> {man}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Layer validation harness")
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--score", default="")
    args = parser.parse_args(argv)
    if args.score:
        score(args.score)
    else:
        draw_sample(n=args.sample or 100, seed=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
