"""Time the individual NVIDIA calls to find the extraction bottleneck."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "packages/extract/src"))

from legislative_extract import consensus, nvidia

key = nvidia.load_key()
pdf = next((Path("data/pdfs").rglob("*.pdf")))
print("PDF:", pdf)

png = nvidia.render_page(str(pdf), page=0, dpi=200)
print("render: done")

t0 = time.time()
r = consensus.read_ocr(key, png)
print(f"ocr-v1: {time.time() - t0:.1f}s ok={r['ok']} chars={len(r['text'])}")

t0 = time.time()
ok, text, err, ms = nvidia.parse_document(key, png)
print(f"parse: {time.time() - t0:.1f}s ok={ok} chars={len(text)}")

t0 = time.time()
r = consensus.read_vision(key, png)
print(f"vision-11b: {time.time() - t0:.1f}s ok={r['ok']} chars={len(r['text'])}")
