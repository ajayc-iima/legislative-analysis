"""Geographic tagging: MLA-based mapping + place-name gazetteer.

Two independent methods per PLAN.md Task 1.2:
  1. MLA-based: every question carries an asker; the ported MLA_DB maps
     asker → constituency → district → region for all 60 constituencies.
  2. Text-based: subject + question text are scanned against a Meghalaya
     gazetteer (11 districts, 60 constituencies, major towns/blocks).

Scope flags (feeds Pillar 1 Ch 3):
  constituency_specific — names the asker's own constituency
  district_specific    — names a district but not the asker's own seat
  state_wide           — no place mention at all

Known limitation (documented in the Compendium): MLA-based geography
assumes the question concerns the asker's own constituency — true for
most local questions, not for state-wide policy ones. That is exactly
why the text method runs alongside it rather than being replaced by it.
"""

import re

from . import reference_data as ref
from .codebook import normalize_dept

# ── Gazetteer ──

DISTRICTS = sorted(ref.DISTRICT_REGION)

CONSTITUENCIES = sorted(ref.CONSTITUENCY_DISTRICT)

TOWNS = [
    "shillong", "tura", "jowai", "nongstoin", "nongpoh", "williamnagar",
    "baghmara", "resubelpara", "baghmara", "bholaganj", "dawki", "cherrapunji",
    "sohra", "mawsynram", "umroi", "airport", "mairang", "rongjeng", "songsak",
    "akhonghata", "dadenggre", "phulbari", "selsella", "rajabala", "ampati",
    "mahendraganj", "salmanpara", "chokpot", "rongsai", "mendipathar",
    "kharkutta", "bajengdoba", "tikrikilla", "raksamgre", "ranikor",
    "mawkyrwat", "mawshynrut", "rambrai", "gambegre", "rangsakona",
    "mawhati", "msing", "umsning", "jirang", "khliehriat", "amlarem",
    "nartiang", "raliang", "mowkaiaw", "sutnga", "pynthorumkhrah", "mawlai",
    "mawphlang", "shella", "pynursla", "mawkynrew", "sohiong", "nongkrem",
    "nongthymmai", "mawryngkneng", "mawsynram", "nongshillong",
    "laitumkhrah", "mawdiengrim", "diengdeng", "jorethang", "rangjung",
    "wahlyngkhat", "nongbare", "mynkre", "umiam", "barapara", "bhoirymbong",
    "nongmahmai", "mukhla", "dangri", "rakshi", "tikrikilla",
]

BLOCKS = [
    "mawkynrew", "mawphlang", "mawsynram", "sohra", "shella", "pynursla",
    "nongstoin", "mairang", "mawkyrwat", "ranikor", "rongsakong", "smit",
    "laitkor", "mylliem", "mawtar", "nongkhlaw", "khyrim", "mawthadraishien",
    "jirang", "umroi", "umsning", "nongpoh", "mawhati", "bholaganj",
    "dawki", "saipung", "lkmiat", "jowai", "raliang", "mowkaiaw",
    "amlarem", "dadenggre", "selsella", "phulbari", "rajabala", "tikrikilla",
    "raksamgre", "dalu", "gambegre", "rongsakona", "ampati", "mahendraganj",
    "salmanpara", "chokpot", "rongara", "baghmara", "siju", "mendipathar",
    "kharkutta", "resubelpara", "bajengdoba", "songsak", "rongjeng",
    "williamnagar", "bhoirymbong", "nongstoin",
]

# order matters: match longest names first so "west garo hills" is not
# eaten by a shorter token
_GAZETTEER = sorted(
    [(name.lower(), "district") for name in DISTRICTS]
    + [(name.lower(), "constituency") for name in CONSTITUENCIES]
    + [(name.lower(), "town") for name in TOWNS]
    + [(name.lower(), "block") for name in BLOCKS],
    key=lambda kv: -len(kv[0]),
)

# canonical district spelling for places that differ from the district name
PLACE_TO_DISTRICT = {d.lower(): d for d in DISTRICTS}
for place in TOWNS + BLOCKS:
    for cons, district in ref.CONSTITUENCY_DISTRICT.items():
        if place in cons.lower():
            PLACE_TO_DISTRICT.setdefault(place, district)


# Historical MLAs (10th Assembly, 2018–2023) whose names appear
# in the CSV but not in the current MLA_DB alias lists.
# Constituencies verified against ECI 2018 results / Wikipedia.
# Keys are _norm_name() output (lowercase, no spaces/punctuation).
HISTORICAL_MLA = {
    "azadzaman": ("Rajabala", "", ""),
    "davidanongrum": ("Mawryngkneng", "", ""),
    "lambormalngiang": ("Nongkrem", "", ""),
    "salengasangma": ("Gambegre", "", ""),
    "salengsangma": ("Gambegre", "", ""),
}


def _mla_name(row):
    return re.sub(r"\s+", " ", str(row.get("Asked_By") or "").strip()).rstrip(",. ")


# Portal spelling variants absent from the legacy alias lists.
# Each entry mirrors an MLA_DB row (seat, constituency, [alias],
# party-10th, party-11th, district, region); parties verified from
# the matching MLA_DB row, names from CSV asker spellings.
EXTRA_ALIASES = {
    "mehtabchandeeasangma": (
        56, "Gambegre", ["Mehtab Chandee A Sangma"], "NCP", "INC",
        "West Garo Hills", "Garo Hills"),
}

MLA_ROWS = list(ref.MLA_DB) + list(EXTRA_ALIASES.values())


def _norm_name(name):
    """Punctuation/space-insensitive name key."""
    return re.sub(r"[^a-z]", "", str(name or "").lower())


def _resolve(constituency, fallback_district="", fallback_region=""):
    """District/region via the authoritative map, not MLA_DB's stale copy."""
    district = ref.CONSTITUENCY_DISTRICT.get(constituency, fallback_district)
    region = ref.DISTRICT_REGION.get(district, fallback_region)
    return district, region


def lookup_mla(name):
    """Match an asker against MLA_DB name variants (handles portal typos)."""
    target = _norm_name(name)
    if not target:
        return None
    if target in HISTORICAL_MLA:
        constituency, _d, _r = HISTORICAL_MLA[target]
        district, region = _resolve(constituency)
        return {"constituency": constituency, "district": district,
                "region": region, "match": "historical"}
    for entry in MLA_ROWS:
        _seat, constituency, aliases, _p10, _p11, fb_district, fb_region = entry
        for alias in aliases:
            if _norm_name(alias) == target:
                district, region = _resolve(constituency, fb_district, fb_region)
                return {"constituency": constituency, "district": district,
                        "region": region, "match": alias}
    # historical MLAs from the ported reference table
    for alias, (constituency, _d, _r, _party) in ref.HISTORICAL_MLA_CONSTITUENCY.items():
        if _norm_name(alias) == target:
            district, region = _resolve(constituency)
            return {"constituency": constituency, "district": district,
                    "region": region, "match": alias}
    return None


def find_places(text):
    """Gazetteer scan: returns dicts of place/level/district mentioned."""
    blob = " " + re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()) + " "
    found = []
    seen = set()
    for name, level in _GAZETTEER:
        if f" {name} " in blob and name not in seen:
            seen.add(name)
            found.append({"place": name, "level": level,
                          "district": PLACE_TO_DISTRICT.get(name)})
    return found


def tag_row(row, subject_of):
    """Attach geography columns to one question row (in place)."""
    mla = _mla_name(row)
    mla_geo = lookup_mla(mla)
    subject = subject_of(row)
    places = find_places(subject + " " + str(row.get("Questions") or ""))
    mentioned_districts = sorted({p["district"] for p in places if p["district"]})
    mentioned_constituencies = sorted({p["place"] for p in places if p["level"] == "constituency"})

    scope = "state_wide"
    own = (mla_geo or {}).get("constituency")
    if own and any(own.lower() == p["place"] for p in places):
        scope = "constituency_specific"
    elif mentioned_districts or mentioned_constituencies:
        scope = "place_specific"

    row["_mla_constituency"] = (mla_geo or {}).get("constituency", "")
    row["_mla_district"] = (mla_geo or {}).get("district", "")
    row["_mla_region"] = (mla_geo or {}).get("region", "")
    row["_mentioned_places"] = [p["place"] for p in places]
    row["_mentioned_districts"] = mentioned_districts
    row["_scope"] = scope
    return row


def tag_all(rows, subject_of):
    for row in rows:
        tag_row(row, subject_of)
    return rows


def mentioned_tops(rows, top=10):
    """Top mentioned districts/places across all question texts.

    MLA-based geography assumes the question concerns the asker's own
    seat; this counts what the TEXT actually names (gazetteer scan),
    so state-wide questions contribute their explicit mentions and
    constituency-specific ones count twice (once per method). Both
    views are reported; neither replaces the other.
    """
    from collections import Counter
    districts, places, any_mention = Counter(), Counter(), 0
    for row in rows:
        mentioned_districts = row.get("_mentioned_districts") or []
        mentioned_places = row.get("_mentioned_places") or []
        if mentioned_districts or mentioned_places:
            any_mention += 1
        districts.update(mentioned_districts)
        places.update(mentioned_places)
    total = len(rows) or 1

    def share(count):
        return round(100 * count / total, 1)

    return {
        "districts": [{"place": k, "questions": v, "share_pct": share(v)}
                      for k, v in districts.most_common(top)],
        "places": [{"place": k, "questions": v, "share_pct": share(v)}
                   for k, v in places.most_common(top)],
        "questions_with_any_mention": any_mention,
        "share_with_any_mention_pct": share(any_mention),
    }


def party_of(asker_name, assembly):
    """Asker's party in the relevant assembly (10th or 11th)."""
    target = _norm_name(asker_name)
    if not target:
        return ""
    eleventh = "Eleventh" in str(assembly or "")
    for entry in MLA_ROWS:
        for alias in entry[2]:
            if _norm_name(alias) == target:
                return entry[4] if eleventh else entry[3]
    for alias, (_c, _d, _r, party) in ref.HISTORICAL_MLA_CONSTITUENCY.items():
        if _norm_name(alias) == target:
            return party
    return {"azadzaman": "INC", "davidanongrum": "INC",
            "lambormalngiang": "IND"}.get(target, "")


def bloc_of(asker_name, assembly):
    """Ruling / Opposition / Unknown per the legacy bloc sets."""
    party = party_of(asker_name, assembly)
    eleventh = "Eleventh" in str(assembly or "")
    ruling = ref.RULING_11 if eleventh else ref.RULING_10
    opposition = ref.OPPOSITION_11 if eleventh else ref.OPPOSITION_10
    if party in ruling:
        return "Ruling"
    if party in opposition:
        return "Opposition"
    return "Unknown"
