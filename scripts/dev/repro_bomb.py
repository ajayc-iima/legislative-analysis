"""Repro the 4093 DecompressionBomb through render_page's DPI fallback."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "packages/extract/src"))

from legislative_extract import nvidia

PDF = (r"D:\ISB\legislative-analysis\data\pdfs\assembly-11\autumn-session-2026"
       r"\11_9_S_4093_V1_signed.pdf")
for dpi in (200, 100, 72):
    t0 = time.time()
    try:
        data = nvidia.render_page(PDF, page=0, dpi=dpi)
        print(f"dpi={dpi}: OK {len(data)} bytes in {time.time()-t0:.1f}s", flush=True)
    except Exception as exc:
        print(f"dpi={dpi}: FAIL {type(exc).__name__}: {str(exc)[:100]} "
              f"in {time.time()-t0:.1f}s", flush=True)
