"""Audit: CSV links vs PDFs on disk vs extracted records (with D: retries)."""

import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path(r"C:\Users\chou_\AppData\Local\Temp\opencode\extract_run")


def read_csv_rows(tries=5):
    for i in range(tries):
        try:
            with open(REPO / "data/dl_questions_raw.csv", encoding="utf-8-sig") as h:
                return list(csv.DictReader(h))
        except OSError:
            time.sleep(10)
    raise OSError("CSV unreadable after retries")


def walk_pdfs(tries=5):
    for i in range(tries):
        try:
            return {p.name for p in (REPO / "data/pdfs").rglob("*.pdf") if p.is_file()}
        except OSError:
            time.sleep(10)
    raise OSError("pdf walk failed after retries")


def main():
    rows = read_csv_rows()
    links = [r["Document_Link"].rsplit("/", 1)[-1] for r in rows
             if (r.get("Document_Link") or "").strip().lower().startswith("http")]
    print(f"csv rows: {len(rows)}, http links: {len(links)}, unique basenames: {len(set(links))}")
    files = walk_pdfs()
    print(f"pdf files on disk: {len(files)}")
    linkset = set(links)
    print(f"linked but not on disk: {len(linkset - files)}")
    print(f"on disk but not linked: {len(files - linkset)}")
    done = set()
    for line in open(OUT / "extracted.jsonl", encoding="utf-8"):
        if line.strip():
            done.add(json.loads(line).get("pdf", ""))
    print(f"extracted records: {len(done)}")
    print(f"linked, on disk, not extracted: {len(linkset & files - done)}")
    by_session = Counter()
    for missing in sorted(linkset - files):
        by_session[missing.split("_")[1]] += 1
    print("missing-on-disk by session code:", dict(by_session))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
