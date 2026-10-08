"""Download NeVA reply PDFs into assembly/session folders.

Layout: <out>/assembly-N/<session-slug>/<original-filename>.pdf — the
portal's own files already carry assembly/session codes in their names,
so nothing is renamed. Two modes:

- download (default): fetch missing PDFs from the links in the CSV,
  with an optional per-session limit for pilot runs.
- --copy-from DIR: copy matching PDFs from an existing folder (flat or
  nested) instead of downloading, skipping what is already stored.
"""

import argparse
import csv
import re
import shutil
import time
from collections import defaultdict
from pathlib import Path

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/154"
TIMEOUT = 60
PAUSE_SECONDS = 0.4
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
            "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "unknown"


def assembly_number(row):
    match = re.search(r"/PaperLaid/(\d+)/", row.get("Document_Link") or "")
    if match:
        return int(match.group(1))
    first = str(row.get("Assembly") or "").strip().lower().split()
    return ORDINALS.get(first[0] if first else "", 0)


def target_path(root, row):
    """Local path for a row's reply PDF: root/assembly-N/session-slug/filename."""
    name = str(row.get("Document_Link") or "").rsplit("/", 1)[-1]
    assembly = assembly_number(row)
    return Path(root) / f"assembly-{assembly or 'unknown'}" / slug(row.get("Session")) / name


def unique_rows(csv_path):
    """Rows with downloadable links, deduplicated by destination path."""
    seen, rows = set(), []
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            url = str(row.get("Document_Link") or "").strip()
            if not url.lower().startswith(("http://", "https://")):
                continue
            key = str(target_path("", row))
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def download(csv_path, root, limit_per_session=0):
    """Fetch missing PDFs; returns (saved, per-session counts, failures)."""
    rows = unique_rows(csv_path)
    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    counts, failures, saved = defaultdict(int), [], 0
    for row in rows:
        path = target_path(root, row)
        session = str(path.parent)
        if path.exists():
            continue
        if limit_per_session and counts[session] >= limit_per_session:
            continue
        try:
            response = http.get(str(row["Document_Link"]).strip(), timeout=TIMEOUT)
            response.raise_for_status()
        except Exception as exc:
            failures.append((row["Document_Link"], str(exc)))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        counts[session] += 1
        saved += 1
        time.sleep(PAUSE_SECONDS)
    return saved, counts, failures


def copy_from(csv_path, root, source, limit_per_session=0):
    """Copy matching PDFs from an existing folder; returns (copied, skipped, missing)."""
    rows = unique_rows(csv_path)
    available = {p.name: p for p in Path(source).rglob("*.pdf")}
    counts = defaultdict(int)
    copied = skipped = missing = 0
    for row in rows:
        path = target_path(root, row)
        session = str(path.parent)
        if path.exists():
            skipped += 1
            counts[session] += 1
            continue
        if limit_per_session and counts[session] >= limit_per_session:
            continue
        origin = available.get(path.name)
        if origin is None:
            missing += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, path)
        counts[session] += 1
        copied += 1
    return copied, skipped, missing


def main(argv=None):
    parser = argparse.ArgumentParser(description="Download/backfill NeVA reply PDFs by session")
    parser.add_argument("--csv", default="data/dl_questions_raw.csv", help="scraped questions CSV")
    parser.add_argument("--out", default="data/pdfs", help="PDF root folder")
    parser.add_argument("--limit", type=int, default=0, help="max PDFs per session (0 = all)")
    parser.add_argument("--copy-from", default="", help="existing folder to copy matching PDFs from")
    args = parser.parse_args(argv)
    if not Path(args.csv).exists():
        print(f"Input CSV not found: {args.csv}")
        return 1
    if args.copy_from:
        copied, skipped, missing = copy_from(args.csv, args.out, args.copy_from, args.limit)
        print(f"copied {copied} | already present {skipped} | not in source {missing}")
        return 0
    saved, counts, failures = download(args.csv, args.out, args.limit)
    print(f"downloaded {saved} files")
    for session, n in sorted(counts.items()):
        print(f"  {session}: {n}")
    if failures:
        print(f"{len(failures)} failed (first 3):")
        for url, error in failures[:3]:
            print(f"  {url} -> {error}")
    return 0
