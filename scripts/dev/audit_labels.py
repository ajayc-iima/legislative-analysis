"""Check every chart for overlapping text, so labelling stays verifiable.

The defect this guards against is the one that reached review: some marks
carrying a value label while their neighbours did not, and labels printed on
top of each other, leaving the reader unable to tell which value belongs to
which mark. Visual inspection catches it once; this catches it on every
rebuild.

Method: matplotlib's SVG output writes one <text> element per label with its
font-size, anchor, and position in absolute figure coordinates, so label
rectangles can be measured from the file itself. Rectangles are estimated
from the declared font-size (0.58 em average advance for DejaVu Sans, which
is what matplotlib ships) - an estimate, but a stable one, and the same
estimate for every chart, which is what makes the comparison fair.

Usage:  python scripts/dev/audit_labels.py [--charts output/charts]
Exit code 1 when any chart reports overlapping text.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SVG_NS = "{http://www.w3.org/2000/svg}"

# average advance width of DejaVu Sans in em units, measured over mixed
# lowercase/digit text; caps and punctuation run wider, digits narrower
ADVANCE_EM = 0.58
# DejaVu Sans ascends ~0.73 em above the baseline and descends ~0.21 em, so a
# tight box is 0.94 em tall; the extra padding here absorbs estimator error
# (a near miss reported as a collision is worse than a miss left unreported,
# because it trains people to ignore the audit)
ASCENT_EM, DESCENT_EM = 0.76, 0.26
TOLERANCE_PX = 2.0          # ignore hairline touches and estimator error


def _style(el: ET.Element) -> dict[str, str]:
    out = {}
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _translate_offset(node: ET.Element, parent_of) -> tuple[float, float]:
    """Offset contributed by translate() transforms on this node's ancestors."""
    dx = dy = 0.0
    cur = node
    while cur is not None:
        for tr in re.findall(r"translate\(([-\d.eE]+)[ ,]+([-\d.eE]+)\)",
                             cur.get("transform") or ""):
            dx += float(tr[0])
            dy += float(tr[1])
        cur = parent_of(cur)
    return dx, dy


def _rotate(el: ET.Element, x: float, y: float) -> tuple[float, float, float]:
    """matplotlib writes rotation as rotate(angle cx cy) about the anchor."""
    for angle, cx, cy in re.findall(
            r"rotate\(([-\d.e]+)(?:[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+))?\)",
            el.get("transform") or ""):
        return (float(angle), float(cx) if cx else x, float(cy) if cy else y)
    return 0.0, x, y


def collect_labels(svg: Path) -> list[dict]:
    """Every <text> label as an axis-aligned box in figure coordinates.

    Rotation is applied to the corners before the box is taken, otherwise
    45-degree tick labels register as collisions with their own neighbours.
    """
    tree = ET.parse(svg)
    root = tree.getroot()
    parents = {child: parent for parent in root.iter() for child in parent}

    def parent_of(el):
        return parents.get(el)

    labels = []
    for el in root.iter(f"{SVG_NS}text"):
        raw = "".join(el.itertext()).strip()
        if not raw:
            continue
        st = _style(el)
        size = float((st.get("font-size") or "10px").replace("px", "") or 10)
        try:
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
        except ValueError:
            continue
        width = ADVANCE_EM * size * len(raw)
        anchor = st.get("text-anchor", "start")
        if anchor == "middle":
            x0 = x - width / 2
        elif anchor == "end":
            x0 = x - width
        else:
            x0 = x
        top, bottom = y - ASCENT_EM * size, y + DESCENT_EM * size
        corners = [(x0, top), (x0 + width, top),
                   (x0 + width, bottom), (x0, bottom)]
        angle, cx, cy = _rotate(el, x, y)
        if angle:
            rad = math.radians(angle)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            corners = [((px - cx) * cos_a - (py - cy) * sin_a + cx,
                        (px - cx) * sin_a + (py - cy) * cos_a + cy)
                       for px, py in corners]
        dx, dy = _translate_offset(el, parent_of)
        corners = corners_offset(corners, dx, dy)
        xs = [px for px, _ in corners]
        ys = [py for _, py in corners]
        group = el
        while parent_of(group) is not None and parent_of(group) is not root:
            group = parent_of(group)
        labels.append({"poly": corners,
                       "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
                       "size": size, "text": raw, "group": id(group)})
    return labels


def corners_offset(corners, dx, dy):
    return [(px + dx, py + dy) for px, py in corners]


def overlaps(a: dict, b: dict) -> bool:
    """Exact overlap test for the two label rectangles.

    Axis-aligned boxes would report every 45-degree tick label as clashing
    with its neighbour, so rotated labels are tested as oriented rectangles
    using the separating axis theorem.
    """
    pa, pb = a["poly"], b["poly"]
    for poly in (pa, pb):
        for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
            # normal to this edge is the candidate separating axis
            nx, ny = -(by - ay), bx - ax
            length = math.hypot(nx, ny)
            if length < 1e-9:
                continue
            nx, ny = nx / length, ny / length
            a_proj = [px * nx + py * ny for px, py in pa]
            b_proj = [px * nx + py * ny for px, py in pb]
            if (max(a_proj) < min(b_proj) + TOLERANCE_PX
                    or max(b_proj) < min(a_proj) + TOLERANCE_PX):
                return False        # a separating axis exists: no overlap
    return True


def audit(chart_dir: Path) -> int:
    svgs = sorted(chart_dir.glob("*.svg"))
    if not svgs:
        print(f"no SVGs in {chart_dir}")
        return 1
    bad = 0
    print(f"{'chart':28} {'labels':>7} {'overlapping pairs':>18}")
    print("-" * 56)
    for svg in svgs:
        labels = collect_labels(svg)
        clashes = []
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                if a["group"] != b["group"]:
                    continue          # separate panels/legends: not a collision
                if overlaps(a, b):
                    clashes.append((a["text"], b["text"]))
        status = "ok" if not clashes else f"{len(clashes)}"
        print(f"{svg.stem:28} {len(labels):>7} {status:>18}")
        if clashes:
            bad += 1
            for first, second in clashes[:4]:
                print(f"    {first!r} over {second!r}")
    print("-" * 56)
    print("PASS: no overlapping labels" if not bad
          else f"FAIL: {bad} chart(s) with overlapping labels")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--charts", default=str(REPO / "output/charts"),
                    help="directory of built charts")
    args = ap.parse_args()
    return audit(Path(args.charts))


if __name__ == "__main__":
    sys.exit(main())
