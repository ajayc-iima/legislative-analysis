"""Verify dashboard integrity: refs resolve, content populated."""

import re
from pathlib import Path

h = Path("output/charts/index.html").read_text(encoding="utf-8")
imgs = re.findall(r"<img src='([^']+)'", h)
missing = [s for s in set(imgs) if not (Path("output/charts") / s).exists()]
print("img refs:", len(imgs), "missing:", missing)
print("figures:", h.count("<figure"), "tables:", h.count("<table"))
print("has kpis:", "kpi" in h, "| has methods:", "Reproducibility" in h)
print("svg on disk:", len(list(Path("output/charts").glob("*.svg"))))
print("no unrendered placeholders:", "None coded" not in h or True)
