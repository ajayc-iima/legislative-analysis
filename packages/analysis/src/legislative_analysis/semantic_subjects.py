"""Semantic subject grouping with multi-gate verification.

This *complements*, never replaces, the deterministic exact-match recurrence
layer. Exact matching is reproducible but under-merges paraphrases; this
module recovers those paraphrases and is held to the same evidentiary
standard as the rest of the analysis:

  - Gate 1  portfolio isolation - grouping never crosses a department
  - Gate 2  locality anchor - conflicting districts/towns block a merge
  - Gate 3  deterministic resolver - spelling, acronym, content-word rules
  - Gate 4  cosine band - only pairs at or above SIM_CANDIDATE are
            considered; similarity alone merges only above
            SIM_DETERMINISTIC_AUTO
  - Gate 5  verification model - borderline pairs are put to
            `meta/llama-3.2-11b-vision-instruct`; a pair no gate can decide
            is NOT merged, it is written to the human adjudication queue

Embeddings come from `nvidia/nemotron-3-embed-1b` (2048 dimensions,
verified against the live endpoint). Because it is an embedding model it
cannot hallucinate: it groups, it never writes a fact.

Every cluster keeps its provenance: the exact NeVA question numbers, the
subject variants it merged, and the similarity and reason behind each
merge, so any grouping can be challenged by reading the evidence.
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional

import numpy as np
import requests

from . import analysis as base
from . import response as resp
from .codebook import normalize_dept
from .reference_data import CONSTITUENCY_DISTRICT, DISTRICT_REGION

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
CACHE_DIR = REPO / "data/cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
EMBED_CACHE_FILE = CACHE_DIR / "nemotron_subject_embeddings.json"
GATE_CACHE_FILE = CACHE_DIR / "gate_verifications.json"

# Known districts and major headquarters in Meghalaya
DISTRICTS = [
    "east khasi hills", "west khasi hills", "south west khasi hills",
    "eastern west khasi hills", "east garo hills", "west garo hills",
    "south garo hills", "north garo hills", "south west garo hills",
    "ri bhoi", "east jaintia hills", "west jaintia hills"
]

TOWNS = [
    "tura", "shillong", "jowai", "nongpoh", "nongstoin", "williamnagar",
    "baghmara", "resubelpara", "ampati", "khliehriat", "mairang",
    "mawkyrwat", "mawlai", "sohra", "pynursla", "dawki", "phulbari",
    "rajabala", "dadenggre", "mendipathar", "kharkutta", "tikrikilla",
    "selsella", "chokpot", "rongjeng", "mawsynram", "nongthymmai"
]

COMMON_ABBREVS = {
    "emrs": "eklavya model residential school",
    "ssa": "samagra shiksha abhiyan",
    "cuet": "common university entrance test",
    "neet": "national eligibility cum entrance test",
    "nep": "national education policy",
    "pmgsy": "pradhan mantri gram sadak yojana",
    "mhis": "meghalaya health insurance scheme",
    "jjm": "jal jeevan mission",
    "mgnrega": "mahatma gandhi national rural employment guarantee act",
    "mbose": "meghalaya board of school education",
    "nta": "national testing agency",
    "nh": "national highway",
    "sh": "state highway",
    "phc": "primary health centre",
    "chc": "community health centre",
    "mepdcl": "meghalaya power distribution corporation limited",
    "icu": "intensive care unit",
}

# ── One threshold, stated once ────────────────────────────────────────────────
# Previously three different numbers were in play (0.72 in the module
# docstring, 0.84 as the candidate threshold, 0.88 as the API-failure
# fallback), so the published description of the method did not match any
# threshold the code actually applied. They are now one documented band:
#
#   sim <  SIM_CANDIDATE              not a candidate at all
#   sim >= SIM_CANDIDATE              enters the gate (deterministic rules,
#                                     then the verification model)
#   unresolved by any gate            NOT merged: written to the human
#                                     adjudication queue instead
SIM_CANDIDATE = 0.84          # cosine at which a pair becomes a candidate
SIM_DETERMINISTIC_AUTO = 0.95  # above this, similarity alone may merge
EMBED_MODEL = "nvidia/nemotron-3-embed-1b"
EMBED_DIMS = 2048              # verified against the live endpoint
GATE_MODEL = "meta/llama-3.2-11b-vision-instruct"

# verdicts a pair can receive
SAME, DIFFERENT, UNRESOLVED = "same", "different", "unresolved"


def _format_session(s: Any) -> str:
    if isinstance(s, (tuple, list)) and len(s) >= 2:
        asm, sess = str(s[0] or "").strip(), str(s[1] or "").strip()
        short_asm = asm.split()[0] if asm.split() else ""
        return f"{short_asm} {sess}".strip() or "Unknown"
    return str(s)


def _get_api_key() -> str:
    key = os.getenv("NVIDIA_API_KEY") or os.getenv("NGC_API_KEY")
    if key:
        return key
    env_file = REPO / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                if line.startswith("NVIDIA_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return ""


def extract_locations(text: str) -> Set[str]:
    """Find specific districts, towns or constituencies in text.

    Districts are matched longest-first and *consumed* once matched. A plain
    substring scan finds "west khasi hills" inside "south west khasi hills",
    reports both districts for one sentence, and then - because one detected
    set is a subset of the other - declares a South West Khasi Hills question
    and a West Khasi Hills question compatible, which is exactly the
    cross-district merge this locality gate exists to prevent.
    """
    low = f" {str(text or '').lower()} "
    found: Set[str] = set()
    remaining = low
    for district in sorted(DISTRICTS, key=len, reverse=True):
        pattern = rf"(?<![a-z]){re.escape(district)}(?![a-z])"
        if re.search(pattern, remaining):
            found.add(district)
            remaining = re.sub(pattern, " ", remaining)
    for town in TOWNS:
        if re.search(rf"(?<![a-z]){re.escape(town)}(?![a-z])", low):
            found.add(town)
    return found


def are_locations_conflicting(locs1: Set[str], locs2: Set[str]) -> bool:
    """True if both mention specific locations that are mutually incompatible."""
    if not locs1 or not locs2:
        return False
    # If identical sets, not conflicting
    if locs1 == locs2:
        return False
    # If one is a subset of the other (e.g. 'tura' and 'tura, west garo hills'), not conflicting
    if locs1.issubset(locs2) or locs2.issubset(locs1):
        return False
    # Distinct non-overlapping locations are conflicting
    intersection = locs1.intersection(locs2)
    if not intersection:
        return True
    return False


def load_embed_cache() -> Dict[str, List[float]]:
    if EMBED_CACHE_FILE.exists():
        try:
            with open(EMBED_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_embed_cache(cache: Dict[str, List[float]]) -> None:
    with open(EMBED_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def load_gate_cache() -> Dict[str, Dict[str, Any]]:
    if not GATE_CACHE_FILE.exists():
        return {}
    try:
        with open(GATE_CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:                                           # noqa: BLE001
        return {}
    return {_migrate_gate_entry(k, v): v for k, v in raw.items()}


def _migrate_gate_entry(key: str, entry: Dict[str, Any]) -> str:
    """Accept both cache schemas.

    The first pass wrote `same_issue: true/false`; the gate now records a
    three-state `verdict`. Existing decisions are kept rather than discarded
    - they were expensive (a model call each) and are still valid - by
    normalising the old boolean into the new vocabulary.
    """
    if isinstance(entry, dict) and "verdict" not in entry:
        if "same_issue" in entry:
            entry["verdict"] = SAME if entry["same_issue"] else DIFFERENT
        else:
            entry["verdict"] = UNRESOLVED
    return key


def save_gate_cache(cache: Dict[str, Dict[str, Any]]) -> None:
    with open(GATE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def embed_subjects(subjects: List[str], batch_size: int = 50) -> Dict[str, np.ndarray]:
    """Embed list of subject strings using nvidia/nemotron-3-embed-1b with caching."""
    cache = load_embed_cache()
    api_key = _get_api_key()
    if not api_key:
        print("Warning: NVIDIA_API_KEY not found. Fallback to cached embeddings only.")
        return {s: np.array(cache[s]) for s in subjects if s in cache}

    missing = [s for s in set(subjects) if s not in cache and s.strip()]
    if missing:
        print(f"Embedding {len(missing)} new subjects with nvidia/nemotron-3-embed-1b...")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        url = "https://integrate.api.nvidia.com/v1/embeddings"
        for i in range(0, len(missing), batch_size):
            batch = missing[i:i + batch_size]
            payload = {
                "input": batch,
                "model": EMBED_MODEL,
                "input_type": "passage"
            }
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=30)
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    for orig, item in zip(batch, data):
                        cache[orig] = item["embedding"]
                else:
                    print(f"Embedding API error {r.status_code}: {r.text[:200]}")
            except Exception as e:
                print(f"Embedding request exception: {e}")
            time.sleep(0.1)
        save_embed_cache(cache)

    out = {}
    for s in subjects:
        if s in cache:
            out[s] = np.array(cache[s], dtype=np.float32)
    return out


def cosine_sim(v1: np.ndarray, v2: np.ndarray) -> float:
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


STOPWORDS = {
    'of', 'the', 'in', 'at', 'for', 'and', '&', 'to', 'under', 'regarding', 'status',
    'on', 'by', 'all', 'a', 'an', 'is', 'are', 'with', 'from', 'across', 'into', 'over'
}

# Words that name a *kind of thing* rather than a particular thing. Two
# subjects that share only these are not evidence of a shared subject:
# "Health Centres in the State" and "Community Health Centre" overlap on
# {health, centre}, and letting that create a merge turns the generic one
# into a hub that welds every facility family in the department together.
GENERIC_HEADS = {
    "health", "centre", "center", "school", "college", "university", "hospital",
    "road", "bridge", "project", "scheme", "mission", "facility", "facilities",
    "infrastructure", "department", "office", "staff", "post", "posts",
    "service", "services", "management", "development", "construction",
    "upgradation", "upgrade", "implementation", "function", "state", "district",
    "block", "circle", "division", "issue", "matter", "status", "detail",
    "doctor", "doctors", "medical", "primary", "community", "rural", "urban",
    "phc", "chc", "sub", "centre", "building", "buildings",
}


def _norm_word(w: str) -> str:
    w = w.lower()
    w = re.sub(r'[^a-z0-9]', '', w)
    w = w.replace('programme', 'program').replace('centre', 'center')
    w = re.sub(r'ment$', '', w)
    w = re.sub(r'ing$', '', w)
    w = re.sub(r's$', '', w)
    # fold repeated letters (e.g. ll -> l)
    w = re.sub(r'([a-z])\1+', r'\1', w)
    return w


def get_content_words(text: str) -> Set[str]:
    words = [_norm_word(w) for w in text.split()]
    return {w for w in words if w and w not in STOPWORDS and len(w) >= 3}


def abbrev_expansions(text: str) -> Set[str]:
    """Full names of any official schemes/abbreviations named in the text.

    "Bhaitbari CHC" yields {"community health centre"}; "PHCs and CHCs"
    yields both. A subject naming *two different* schemes is handled
    separately by the caller: it must not be allowed to join two families,
    because a bridging subject is how single-linkage clustering silently
    welds unrelated clusters together.
    """
    low = f" {str(text or '').lower()} "
    found: Set[str] = set()
    for abbr, expansion in COMMON_ABBREVS.items():
        # the spelled-out name counts too, and plurals are normal in the
        # archive ("PHCs and CHCs", "Primary Health Centres"): a bridging
        # subject that slips past this test is enough to weld two families
        hit = (re.search(rf"(?<![a-z]){re.escape(abbr)}s?(?![a-z])", low)
               or re.search(rf"(?<![a-z]){re.escape(expansion)}s?(?![a-z])", low))
        if hit:
            found.add(expansion)
    return found


def check_deterministic_match(s1: str, s2: str) -> Optional[Tuple[bool, str, str]]:
    """Quick deterministic rule check before invoking the verification model.

    Returns (same_issue, canonical_title, reason) or None if no rule decides.
    """
    n1 = base.normalize_subject(s1)
    n2 = base.normalize_subject(s2)
    canon = s1 if len(s1) >= len(s2) else s2

    if n1 == n2:
        return (True, canon, "Identical normalized subject string")

    # Check location conflicts first: if conflicting locations, definite NO
    loc1 = extract_locations(s1)
    loc2 = extract_locations(s2)
    if are_locations_conflicting(loc1, loc2):
        return (False, "", f"Geographic entity conflict: "
                           f"'{', '.join(sorted(loc1))}' vs '{', '.join(sorted(loc2))}'")

    # Two *different* named schemes are two different subjects, however
    # similar the sentence around them: "Primary Health Centre" and
    # "Community Health Centre" share a head noun, so an embedding model
    # rates them highly, yet they are different facility types.
    e1, e2 = abbrev_expansions(s1), abbrev_expansions(s2)
    if e1 and e2 and not (e1 & e2):
        return (False, "", f"Different named schemes: {'; '.join(sorted(e1))} "
                           f"vs {'; '.join(sorted(e2))}")

    # Minor typo or & vs and
    clean1 = re.sub(r"[^\w\s]", "", s1.lower()).replace("and", "").replace("&", "")
    clean2 = re.sub(r"[^\w\s]", "", s2.lower()).replace("and", "").replace("&", "")
    clean1 = " ".join(clean1.split())
    clean2 = " ".join(clean2.split())
    if clean1 == clean2:
        return (True, canon, "Spelling or formatting variant (& vs and)")

    # High string sequence similarity (e.g. typos like College vs Collage)
    from difflib import SequenceMatcher
    seq_ratio = SequenceMatcher(None, s1.lower(), s2.lower()).ratio()
    if seq_ratio >= 0.88:
        return (True, canon, f"String sequence similarity ({seq_ratio:.3f})")

    # Acronyms
    for ac, exp in COMMON_ABBREVS.items():
        if (ac in n1 and exp in n2) or (ac in n2 and exp in n1):
            return (True, exp.title(), f"Abbreviation match: {ac.upper()} <=> {exp.title()}")

    # Substantive content-word matching (ignoring word order and grammatical
    # particles). At least one *specific* word must be shared: sharing only
    # generic head nouns ("health", "centre") is not evidence of a shared
    # subject, it is evidence that both questions are about the same field.
    w1 = get_content_words(s1)
    w2 = get_content_words(s2)
    if w1 and w2:
        shared = w1 & w2
        specific = shared - GENERIC_HEADS
        inter = len(shared)
        union = len(w1 | w2)
        jaccard = inter / union if union else 0.0
        is_subset = (w1.issubset(w2) or w2.issubset(w1)) and inter >= 2
        if specific and (jaccard >= 0.60 or is_subset):
            return (True, canon, f"Content words overlap (Jaccard: {jaccard:.2f}, "
                                 f"shared: {', '.join(sorted(specific))})")
        if shared and not specific:
            return (False, "", f"Overlap is generic only: "
                               f"{', '.join(sorted(shared))}")

    return None


def verify_pair_gate(s1: str, s2: str, dept: str, sim: float,
                     gate_cache: Dict[str, Any], api_key: str,
                     det: Optional[Tuple[bool, str, str]] = None,
                     http: Optional["requests.Session"] = None) -> Tuple[str, str, str]:
    """Multi-gate verification.

    Returns (verdict, canonical_title, reason) where verdict is SAME,
    DIFFERENT or UNRESOLVED.

    UNRESOLVED is a real outcome, not an error path. Previously a failed or
    timed-out API call fell through to "merge if similarity >= 0.88", which
    meant the *method* silently changed depending on network state and two
    rebuilds could disagree. Now an undecidable pair is never merged: it is
    recorded and handed to a human.
    """
    # Gate 1-3: deterministic rules, no model involved
    if det is None:
        det = check_deterministic_match(s1, s2)
    if det is not None:
        return (SAME if det[0] else DIFFERENT), det[1], det[2]

    pair_key = f"{dept}:::{sorted([s1, s2])[0]}:::{sorted([s1, s2])[1]}"
    if pair_key in gate_cache:
        cached = gate_cache[pair_key]
        return (cached["verdict"], cached.get("canonical_title", s1),
                cached.get("reason", "cached"))

    if sim >= SIM_DETERMINISTIC_AUTO:
        reason = f"Similarity {sim:.3f} at or above the deterministic ceiling {SIM_DETERMINISTIC_AUTO}"
        gate_cache[pair_key] = {"verdict": SAME, "canonical_title": s1, "reason": reason}
        return SAME, s1, reason

    if not api_key:
        reason = f"No verification key available; similarity {sim:.3f} left to human review"
        return UNRESOLVED, "", reason

    prompt = f"""You are an expert legislative auditor for the Meghalaya State Government.
You are evaluating whether two parliamentary question subjects refer to the EXACT SAME specific government project, institution, incident, policy, or recurring controversy across assembly sessions within the {dept} department.

Subject A: "{s1}"
Subject B: "{s2}"

Strict Rules:
1. If they differ by geographic location, district, or town (e.g. East Jaintia vs West Jaintia, or Tura vs Shillong), they are NOT the same issue (same_issue: false).
2. If they refer to different specific schemes or facilities (e.g. LP School vs College, or NH-6 vs NH-127B), they are NOT the same issue (same_issue: false).
3. If they are progressive status updates, tender inquiries, or paraphrases of the same underlying scheme/facility/issue, they ARE the same issue (same_issue: true).

Reply with JSON only:
{{"same_issue": true/false, "canonical_title": "...", "reason": "..."}}"""

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": GATE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 120
    }
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    post = (http.post if http is not None else requests.post)
    try:
        r = post(url, json=payload, headers=headers, timeout=20)
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if m:
                res = json.loads(m.group(0))
                same = bool(res.get("same_issue"))
                canon = str(res.get("canonical_title") or s1).strip()
                reason = str(res.get("reason") or "Verified by model").strip()
                verdict = SAME if same else DIFFERENT
                gate_cache[pair_key] = {"verdict": verdict, "canonical_title": canon,
                                       "reason": reason, "similarity": round(sim, 4)}
                return verdict, canon, reason
        reason = (f"Verification model returned HTTP {r.status_code}; "
                  f"similarity {sim:.3f} left to human review")
    except Exception as exc:                                     # noqa: BLE001
        reason = f"Verification model unavailable ({type(exc).__name__}); " \
                 f"similarity {sim:.3f} left to human review"
    # Not cached: a transient failure must not be frozen into the record.
    return UNRESOLVED, "", reason


def cluster_department_subjects(rows: List[dict], dept: str,
                                embeddings: Dict[str, np.ndarray],
                                gate_cache: Dict[str, Any],
                                api_key: str,
                                sim_threshold: float = SIM_CANDIDATE,
                                unresolved: Optional[List[dict]] = None,
                                http: Optional["requests.Session"] = None
                                ) -> List[Dict[str, Any]]:
    """Build semantically clustered issue families for one department.

    `unresolved` collects every pair no gate could decide. Those are never
    merged; the caller writes them to the human adjudication queue.
    """
    dept_rows = [r for r in rows if normalize_dept(r.get("Departments")) == dept]
    if not dept_rows:
        return []

    # Map each cleaned subject to its rows
    by_subject = defaultdict(list)
    for r in dept_rows:
        sub = base.subject_of(r)
        if sub and len(sub) >= 4:
            by_subject[sub].append(r)

    unique_subjects = sorted(list(by_subject.keys()))
    n_subs = len(unique_subjects)

    # Subjects that name two or more different schemes ("Upgradation of X PHC
    # to Y CHC") are not allowed to create edges. In single-linkage
    # clustering such a subject is a bridge: it welds the PHC family and the
    # CHC family into one, which is how a "Primary Health Centre" family
    # ended up containing community health centres. They are attached to
    # every family they name afterwards, which is both true and harmless.
    expansions = {s: abbrev_expansions(s) for s in unique_subjects}
    multi_named = {s for s, e in expansions.items() if len(e) > 1}

    adjacency = defaultdict(set)
    verified_edges = {}
    canonical_candidates = defaultdict(list)
    stats = Counter()

    for i in range(n_subs):
        s1 = unique_subjects[i]
        v1 = embeddings.get(s1)
        if v1 is None:
            stats["no_embedding"] += 1
            continue
        for j in range(i + 1, n_subs):
            s2 = unique_subjects[j]
            if s1 in multi_named or s2 in multi_named:
                stats["bridging_subject_not_merged"] += 1
                continue
            v2 = embeddings.get(s2)
            if v2 is None:
                continue

            det = check_deterministic_match(s1, s2)
            if det is not None and not det[0]:
                stats["rejected_by_locality_or_rule"] += 1
                continue

            sim = cosine_sim(v1, v2)
            is_candidate = (sim >= sim_threshold) or (det is not None and det[0])
            if not is_candidate:
                continue

            verdict, canon, reason = verify_pair_gate(
                s1, s2, dept, sim, gate_cache, api_key, det=det, http=http)
            if verdict == SAME:
                adjacency[s1].add(s2)
                adjacency[s2].add(s1)
                verified_edges[(s1, s2)] = {"sim": round(sim, 3), "reason": reason,
                                           "canon": canon, "verdict": verdict}
                canonical_candidates[s1].append(canon)
                canonical_candidates[s2].append(canon)
                stats["merged"] += 1
            elif verdict == DIFFERENT:
                stats["kept_apart"] += 1
            else:
                stats["unresolved"] += 1
                if unresolved is not None:
                    unresolved.append({"department": dept, "subject_a": s1,
                                       "subject_b": s2, "similarity": round(sim, 4),
                                       "reason": reason})
    dept_gate_stats = dict(stats)

    # Connected components
    visited = set()
    components = []

    for s in unique_subjects:
        if s in multi_named:
            continue          # attached below; never seeded as its own family
        if s in visited:
            continue
        component = []
        queue = [s]
        visited.add(s)
        while queue:
            curr = queue.pop(0)
            component.append(curr)
            for neighbor in adjacency.get(curr, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(component)

    # Attach the subjects that name several schemes to every family they
    # name, so their questions are counted where they belong instead of
    # disappearing or forcing two families together.
    for subject in sorted(multi_named):
        wanted = expansions[subject]
        for component in components:
            if expansions[component[0]] & wanted or any(
                    expansions.get(member, set()) & wanted for member in component):
                component.append(subject)
                stats["bridging_subject_attached"] += 1

    clusters = []
    for component in components:
        # Aggregate questions
        cluster_rows = []
        for subj in component:
            cluster_rows.extend(by_subject[subj])

        # Pick canonical title: most frequent title in cluster or shortest clear candidate
        if len(component) == 1:
            canon_title = component[0]
        else:
            all_canons = [c for subj in component for c in canonical_candidates.get(subj, []) if c]
            if all_canons:
                canon_title = Counter(all_canons).most_common(1)[0][0]
            else:
                canon_title = sorted(component, key=lambda x: (len(x), x))[0]

        # Gather edge details
        edges = []
        for i_c in range(len(component)):
            for j_c in range(i_c + 1, len(component)):
                s_a, s_b = component[i_c], component[j_c]
                pair = (min(s_a, s_b), max(s_a, s_b))
                if pair in verified_edges:
                    edges.append({"s1": pair[0], "s2": pair[1], **verified_edges[pair]})

        sessions = sorted(list({(r.get("Assembly") or "", r.get("Session") or "") for r in cluster_rows}))
        askers = sorted(list({str(r.get("Asked_By") or "").strip() for r in cluster_rows if r.get("Asked_By")}))

        clusters.append({
            "department": dept,
            "canonical_subject": canon_title,
            "unique_subjects": component,
            "occurrences": len(cluster_rows),
            "n_sessions": len(sessions),
            "sessions": [_format_session(s) for s in sessions],
            "sessions_raw": sessions,
            "askers": askers,
            "question_numbers": [str(r.get("Question_Number") or "") for r in cluster_rows],
            "rows": cluster_rows,
            "verified_edges": edges,
            "gate_stats": dept_gate_stats,
        })

    # Sort by occurrences descending
    clusters.sort(key=lambda c: (-c["occurrences"], -c["n_sessions"], c["canonical_subject"]))
    return clusters


def build_semantic_pipeline(rows: List[dict], reply_lookup: Dict[str, dict],
                            session_order: List[Tuple[str, str]],
                            sim_threshold: float = SIM_CANDIDATE,
                            http: Optional["requests.Session"] = None) -> Dict[str, Any]:
    """Run full semantic embedding + multi-gate longitudinal analysis."""
    all_subjects = [base.subject_of(r) for r in rows if base.subject_of(r)]
    embeddings = embed_subjects(all_subjects)
    gate_cache = load_gate_cache()
    api_key = _get_api_key()

    dept_totals = Counter(normalize_dept(r.get("Departments")) for r in rows)
    all_clusters = []
    families_out = {}
    unresolved: List[dict] = []

    for dept, count in dept_totals.most_common():
        print(f"Processing department: {dept} ({count} questions)...", flush=True)
        dept_clusters = cluster_department_subjects(
            rows, dept, embeddings, gate_cache, api_key,
            sim_threshold=sim_threshold, unresolved=unresolved, http=http,
        )
        all_clusters.extend(dept_clusters)
        save_gate_cache(gate_cache)

    # Build Layer 5 families (recurring across >= 2 sessions)
    for c in all_clusters:
        if c["n_sessions"] < 2:
            continue

        by_session = defaultdict(list)
        for r in c["rows"]:
            by_session[(r.get("Assembly") or "", r.get("Session") or "")].append(r)

        ordered = []
        for sk in session_order:
            if sk not in by_session:
                continue
            rep = sorted(by_session[sk], key=lambda r: str(r.get("Question_Number") or ""))[0]
            name = str(rep.get("Document_Link") or "").rsplit("/", 1)[-1]
            rec = reply_lookup.get(name, {})
            ordered.append((sk, rec.get("reply", ""), rep))

        from .longitudinal import code_trajectory
        status, detail = code_trajectory([(s, t) for s, t, _ in ordered])
        stage_names = [resp.code_stage(t)["stage"] for _s, t, _r in ordered]
        stage_idx = [resp.code_stage(t)["index"] for _s, t, _r in ordered]

        key = base.normalize_subject(c["canonical_subject"])
        families_out[key] = {
            "subject": c["canonical_subject"],
            "sessions": [_format_session(s) for s, _t, _r in ordered],
            "occurrences": c["occurrences"],
            "departments": [c["department"]],
            "askers": c["askers"],
            "trajectory": status,
            "detail": detail,
            "stage_first": stage_names[0] if stage_names else "None evidenced",
            "stage_last": stage_names[-1] if stage_names else "None evidenced",
            "stage_delta": (stage_idx[-1] - stage_idx[0]) if stage_idx else 0,
            "question_numbers": c["question_numbers"],
            "unique_subjects": c["unique_subjects"],
            "verified_edges": c["verified_edges"],
        }

    # Resolution counts
    res_counts = defaultdict(int)
    for f in families_out.values():
        res_counts[f["trajectory"]] += 1

    # Emerging issues (first seen in last 3 sessions, asked by >= 2 MLAs)
    recent_sessions = set(session_order[-3:])
    emerging_out = []
    for c in all_clusters:
        first_session = min(c["sessions_raw"], key=lambda s: session_order.index(s))
        if first_session in recent_sessions and c["occurrences"] >= 2 and len(c["askers"]) >= 2:
            emerging_out.append({
                "subject": c["canonical_subject"],
                "department": c["department"],
                "first_session": _format_session(first_session),
                "occurrences": c["occurrences"],
                "askers": c["askers"],
                "unique_subjects": c["unique_subjects"],
            })
    emerging_out.sort(key=lambda e: (-e["occurrences"], e["subject"]))

    return {
        "methodology": "semantic_embedding_multi_gate",
        "embed_model": EMBED_MODEL,
        "embed_dims": EMBED_DIMS,
        "gate_model": GATE_MODEL,
        "sim_threshold": sim_threshold,
        "n_subjects_embedded": len(embeddings),
        "n_clusters": len(all_clusters),
        "n_families": len(families_out),
        "resolution_counts": dict(res_counts),
        "families": families_out,
        "emerging_issues": emerging_out,
        "clusters": all_clusters,
        "unresolved_pairs": unresolved,
        "n_unresolved": len(unresolved),
    }
