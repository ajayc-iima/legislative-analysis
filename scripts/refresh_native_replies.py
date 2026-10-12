"""Refresh stored native-path reply texts to match the current splitter.

Why: reply texts were produced across incremental revisions of
split_reply, so re-running the pipeline today would not reproduce the
stored bytes for a subset of native-path records (128 as of
2026-10-12). For records read entirely from the PDF text layer the
result is deterministic, so it can be recomputed locally - no OCR, no
API, no date changes.

Records that used OCR (pages_ocr > 0) are never touched: their text
depends on OCR output, which is not bit-reproducible, and their dates
come from the consensus pass.

Usage:
    python scripts/refresh_native_replies.py            # dry run, report
    python scripts/refresh_native_replies.py --apply    # rewrite jsonl
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages/extract/src"))

import pymupdf  # noqa: E402
from legislative_extract.extract import (MAX_OCR_PAGES, NATIVE_MIN_CHARS,  # noqa: E402
                                         cut_footer, looks_gibberish, split_parts,
                                         split_reply)

DEFAULT_RUN = Path(r"C:\Users\chou_\AppData\Local\Temp\opencode\extract_run")
DEFAULT_BACKUP = Path(r"C:\Users\chou_\AppData\Local\Temp\opencode\extract_backup")
NOTE = ("reply text refreshed to current splitter "
        "(native-layer recompute, dates untouched)")
HEAD = "This tool recomputes reply text only"


def recompute(path):
    """Reply text for a PDF read entirely from its native text layer."""
    with pymupdf.open(path) as doc:
        n_pages = len(doc)
    replies, questions = [], []
    for page in range(min(n_pages, MAX_OCR_PAGES)):
        with pymupdf.open(path) as doc:
            obj = doc[page]
            raw = obj.get_text("words")
            text = " ".join(w[4] for w in raw)
            if len(text.strip()) < NATIVE_MIN_CHARS or looks_gibberish(text):
                return None  # would need OCR: out of scope for this tool
            width, height = obj.rect.width, obj.rect.height
            words = [(w[0], w[1], w[2], w[3], w[4]) for w in raw]
            reply = split_reply(words, width, height)
            question = split_reply(words, width, height, side="left")
        if reply.strip():
            replies.append(reply)
        if question.strip():
            questions.append(question)
    reply = cut_footer("\n".join(replies).strip())
    parts = split_parts("\n".join(questions).strip(), reply)
    return reply, parts


def main(argv=None):
    parser = argparse.ArgumentParser(description=HEAD)
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN))
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    jsonl = run_dir / "extracted.jsonl"
    pdf_root = REPO / "data/pdfs"
    index = {}
    for p in pdf_root.rglob("*.pdf"):
        index.setdefault(p.name, p)

    lines = [l for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    recs = [json.loads(l) for l in lines]

    changed, skipped_ocr, skipped_missing, skipped_quarantine = [], 0, 0, 0
    for rec in recs:
        if rec.get("pages_ocr"):
            skipped_ocr += 1
            continue
        if any(str(n).startswith("quarantined:")
               for n in rec.get("needs_review", [])):
            # Quarantined by human review: its text is withheld on purpose
            # and must never be recomputed back into the corpus.
            skipped_quarantine += 1
            continue
        path = index.get(rec.get("pdf", ""))
        if path is None:
            skipped_missing += 1
            continue
        out = recompute(str(path))
        if out is None:
            skipped_missing += 1
            continue
        reply, parts = out
        if reply.strip() == (rec.get("reply") or "").strip():
            continue
        changed.append(rec["pdf"])
        rec["reply"] = reply
        rec["parts"] = parts
        notes = rec.get("needs_review", [])
        if NOTE not in notes:
            notes.append(NOTE)
        rec["needs_review"] = notes

    print(f"records={len(recs)} changed={len(changed)} "
          f"ocr-path untouched={skipped_ocr} quarantined untouched={skipped_quarantine} "
          f"not-native/not-found={skipped_missing}")
    if changed and args.apply:
        backup = Path(args.backup_dir)
        backup.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(jsonl, backup / f"extracted_full_{ts}.jsonl")
        jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
                         encoding="utf-8")
        (backup / f"refresh_native_replies_{ts}.json").write_text(
            json.dumps(sorted(changed), indent=1), encoding="utf-8")
        print(f"applied; backup -> extracted_full_{ts}.jsonl")
    elif changed:
        print("dry run; pass --apply to rewrite")
    return 0


if __name__ == "__main__":
    sys.exit(main())