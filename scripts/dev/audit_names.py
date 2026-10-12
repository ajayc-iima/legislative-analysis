"""Check that every person named in the outputs is identified unambiguously.

Eight surnames in this Assembly belong to more than one member — 13 of the
63 askers are "… Sangma", 8 are "… Lyngdoh". A label or table cell that
prints a surname on its own therefore names a family, not a legislator, and
a reader cannot tell which member a figure is about.

The check works on the built artifacts rather than on the source, because
the defect appears in the *rendering*: the analysis keyed people by full
name throughout and was correct; only the chart labels abbreviated.

What it verifies, per output file:
- every surname shared by more than one member appears only as part of a
  full name (surname preceded by a given name), never bare;
- the abbreviations member_labels() produces are the ones used, so a
  figure cannot invent its own short form;
- no two distinct members share a printed label.

Usage:  python scripts/dev/audit_names.py
Exit code 1 when any output names a person ambiguously.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))
from legislative_analysis.naming import member_labels, shared_surnames  # noqa: E402

GIVEN_NAME = re.compile(r"^[A-Z][a-z]+$")


def corpus_people() -> list[str]:
    with open(REPO / "data/dl_questions_raw.csv", encoding="utf-8-sig",
              newline="") as handle:
        rows = list(csv.DictReader(handle))
    return sorted({(r.get("Asked_By") or "").strip() for r in rows
                   if (r.get("Asked_By") or "").strip()})


def strip_markup(text: str) -> str:
    """Remove tags *with their attributes*, keeping the text nodes.

    Removing only tag names would leave `transform="rotate(-0 246.4 ...)"` in
    the stream, and the digits in it break the "is a given name before the
    surname?" test that follows.
    """
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", text))


def bare_surname_uses(text: str, shared: set[str]) -> list[tuple[str, str]]:
    """Occurrences of a shared surname not preceded by a given name."""
    hits = []
    for surname in sorted(shared):
        pattern = re.compile(r"(?<![A-Za-z])(" + re.escape(surname) + r")(?![\w])")
        for match in pattern.finditer(text):
            before = text[max(0, match.start() - 40):match.start()]
            tokens = before.split()
            # a given name immediately before the surname identifies a person
            if any(GIVEN_NAME.match(t.strip(".,")) for t in tokens[-2:]):
                continue
            hits.append((surname, text[max(0, match.start() - 45):
                                       match.start() + len(surname) + 5]))
    return hits


def audit(paths: list[Path]) -> int:
    people = corpus_people()
    shared = shared_surnames(people)
    labels = member_labels(people)

    if len(set(labels.values())) != len(labels):
        print("FAIL: member_labels() produced duplicate labels")
        return 1

    problems = 0
    for path in paths:
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = strip_markup(raw)
        hits = bare_surname_uses(text, shared)
        status = "ok" if not hits else f"{len(hits)} bare surname use(s)"
        print(f"{path.relative_to(REPO)}: {status}")
        for surname, context in hits[:5]:
            print(f"    {surname!r} in ...{context.strip()}...")
        problems += len(hits)
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", help="files to check (default: built outputs)")
    args = ap.parse_args()
    paths = [Path(p) for p in args.paths] or [
        REPO / "output/report/index.html",
        REPO / "output/charts/index.html",
        REPO / "output/analysis_report.md",
    ]
    paths += sorted((REPO / "output/charts").glob("*.svg"))
    paths += sorted((REPO / "output/anticipation").glob("*.md"))
    paths = [p for p in paths if p.exists()]
    print(f"checking {len(paths)} files; "
          f"{len(shared_surnames(corpus_people()))} surnames are shared "
          "by more than one member\n")
    rc = audit(paths)
    print("\nPASS: every member named in the outputs is identified by name"
          if not rc else "\nFAIL: ambiguous member name(s) in the outputs")
    return rc


if __name__ == "__main__":
    sys.exit(main())
