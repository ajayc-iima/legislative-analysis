"""Which recurrence result the outputs publish, and how they say so.

There are two ways to decide that a subject returned in a later sitting,
and both are computed:

* **semantic** (published when present) - dense embeddings with locality,
  named-scheme and specificity gates plus model verification. This measures
  the construct we actually claim: an issue that persisted. It recovers
  paraphrases, so it finds families exact matching cannot see.
* **exact** (always available) - string equality after normalisation. It
  needs no model and no network, so it is the reproducible floor and the
  fallback, and it is reported beside the semantic count everywhere.

Substituting one for the other silently is the failure mode this module
exists to prevent. Every consumer takes its result from here, so the method
travels with the data and is stamped into every caption that uses it. When
the semantic layer is missing, the fallback is recorded rather than hidden.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
LAYERS = REPO / "output/layers"

EXACT_FILE = LAYERS / "layer5_resolution.json"
SEMANTIC_FILE = LAYERS / "layer5_semantic.json"

# short labels for captions and prose
LABEL = {
    "semantic_embedding_multi_gate": "semantic grouping (embeddings + verification gates)",
    "exact_normalized_subject_match": "exact match on the normalised subject",
}


def load(prefer: str = "semantic") -> dict:
    """Return the recurrence result to publish.

    The returned dict always carries `methodology`, `source` and `label`, so
    a caller cannot use these numbers without also being able to say how
    they were produced.
    """
    exact = _read(EXACT_FILE)
    semantic = _read(SEMANTIC_FILE)

    order = [("semantic", semantic), ("exact", exact)] if prefer == "semantic" \
        else [("exact", exact), ("semantic", semantic)]

    chosen_key, chosen = next(((k, v) for k, v in order if v), (None, None))
    if chosen is None:
        raise SystemExit(
            f"no recurrence layer found - run scripts/run_layers.py "
            f"(and optionally scripts/build_semantic_clusters.py)")

    result = {
        "methodology": chosen.get("methodology", chosen_key),
        "source": (SEMANTIC_FILE if chosen_key == "semantic"
                   else EXACT_FILE).name,
        "label": LABEL.get(chosen.get("methodology", chosen_key), chosen_key),
        "families": chosen.get("families", {}),
        "n_families": chosen.get("n_families", 0),
        "resolution_counts": chosen.get("resolution_counts", {}),
        "embed_model": chosen.get("embed_model"),
        "embed_dims": chosen.get("embed_dims"),
        "gate_model": chosen.get("gate_model"),
        "sim_threshold": chosen.get("sim_threshold"),
        "n_subjects_embedded": chosen.get("n_subjects_embedded"),
        "n_unresolved": chosen.get("n_unresolved"),
        # Emerging issues travel with the layer that produced them. The
        # semantic layer carries its own; the exact-match layer keeps them
        # in layer6_trends.json, so this is empty when exact is chosen —
        # consumers must not read that as "nothing emerged".
        "emerging_issues": chosen.get("emerging_issues", []),
        "used_fallback": chosen_key != prefer,
    }
    # the other method, so callers can always show both
    other_key = "exact" if chosen_key == "semantic" else "semantic"
    other = exact if other_key == "exact" else semantic
    result["other"] = {
        "key": other_key,
        "available": bool(other),
        "n_families": (other or {}).get("n_families"),
        "resolution_counts": (other or {}).get("resolution_counts", {}),
        "methodology": (other or {}).get("methodology"),
        "label": LABEL.get((other or {}).get("methodology"), other_key),
    }
    return result


def _read(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:                                          # noqa: BLE001
        return None
