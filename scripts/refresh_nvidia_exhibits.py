"""Re-extract replies used in Documentary Exhibit cards with NVIDIA vision.

The result is cached so report builds remain deterministic and do not make
network calls. Existing corpus extraction is not overwritten: this is a
targeted exhibit-quality layer with explicit PDF/page/model provenance.

Usage:
    python scripts/refresh_nvidia_exhibits.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/analysis/src"))
sys.path.insert(0, str(REPO / "packages/extract/src"))
sys.path.insert(0, str(REPO / "scripts"))

from legislative_extract import nvidia  # noqa: E402
from build_compendium import load_extracted  # noqa: E402

OUT = REPO / "data/cache/nvidia_exhibit_replies.json"
PDF_ROOT = REPO / "data/pdfs"
MAX_PAGES = 12


def _pdf_index() -> dict[str, Path]:
    return {path.name: path for path in PDF_ROOT.rglob("*.pdf")}


def reextract(pdf: Path, key: str) -> dict:
    import pymupdf

    pages = []
    errors = []
    with pymupdf.open(pdf) as doc:
        page_count = min(len(doc), MAX_PAGES)
    for page in range(page_count):
        print(f"    page {page + 1}/{page_count}: rendering", flush=True)
        try:
            png = nvidia.render_page(str(pdf), page=page, dpi=220)
            print(f"    page {page + 1}/{page_count}: NVIDIA request", flush=True)
            ok, text, error, ms = nvidia.extract_reply_page(key, png)
        except Exception as exc:  # record the page failure; do not hide it
            ok, text, error, ms = False, "", f"{type(exc).__name__}: {exc}", 0
        print(f"    page {page + 1}/{page_count}: "
              f"{'ok' if ok else 'failed'} in {ms}ms", flush=True)
        if ok and text.strip() and text.strip().upper() != "NO_REPLY":
            pages.append({"page": page + 1, "text": text.strip(), "ms": ms})
        elif not ok:
            errors.append({"page": page + 1, "error": error, "ms": ms})
    reply = "\n\n".join(item["text"] for item in pages).strip()
    return {
        "pdf": pdf.name,
        "reply": reply,
        "pages": pages,
        "errors": errors,
        "model": "meta/llama-3.2-11b-vision-instruct",
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="call NVIDIA and write the exhibit cache")
    parser.add_argument("--pdf", action="append",
                        help="restrict extraction to one or more PDF filenames")
    args = parser.parse_args(argv)
    extracted = load_extracted()
    names = set(args.pdf or extracted)
    index = _pdf_index()
    missing = sorted(names - set(index))
    if missing:
        raise SystemExit("PDFs not found: " + ", ".join(missing))
    if not args.apply:
        print(f"dry run: {len(names)} exhibit PDFs would be sent to NVIDIA")
        return 0
    key = nvidia.load_key()
    if not key:
        raise SystemExit("NVIDIA_API_KEY or NIM_API_KEY is required")
    cache = {}
    if OUT.exists():
        try:
            cache = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}
    for name in sorted(names):
        started = time.time()
        print(f"  NVIDIA exhibit extraction: {name}", flush=True)
        cache[name] = reextract(index[name], key)
        if cache[name]["errors"]:
            print(f"    page errors: {len(cache[name]['errors'])}", flush=True)
        if not cache[name]["reply"]:
            print("    WARNING: no reply text returned", flush=True)
        print(f"  finished {name} in {time.time() - started:.1f}s", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT} ({len(cache)} PDFs)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
