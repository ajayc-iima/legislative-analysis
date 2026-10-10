"""Read the last pages of the legacy draft report PDF (with D: retries)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages/extract/src"))

PDF = Path(r"D:\ISB\Legislative Preparedness\shared\MGLA_Legislative_Preparedness_Report_DRAFT_v1.pdf")

import pymupdf

doc = None
for _ in range(4):
    try:
        doc = pymupdf.open(PDF)
        break
    except Exception as exc:
        print("open failed, retrying:", str(exc)[:80])
        time.sleep(15)
print("pages:", len(doc))
for i in range(max(0, len(doc) - 4), len(doc)):
    print(f"\n{'#' * 30} PAGE {i + 1} {'#' * 30}")
    print(doc[i].get_text()[:2500])
