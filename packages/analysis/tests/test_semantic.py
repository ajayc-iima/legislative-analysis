"""The gates that decide whether two subjects are the same issue.

Each test here corresponds to a real failure found while the semantic layer
was being audited: a district pair that was not recognised as conflicting,
a family that welded primary and community health centres together, and an
API outage that silently changed the method.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legislative_analysis import semantic_subjects as sem  # noqa: E402


# ── locality: distinct districts must never merge ─────────────────────────────

def test_overlapping_district_names_are_distinguished():
    """'west khasi hills' is a substring of 'south west khasi hills'."""
    a = sem.extract_locations("Road works in South West Khasi Hills")
    b = sem.extract_locations("Road works in West Khasi Hills")
    assert a == {"south west khasi hills"}
    assert b == {"west khasi hills"}
    assert sem.are_locations_conflicting(a, b)


@pytest.mark.parametrize("a,b", [
    ("Teachers of LP Schools, East Jaintia Hills",
     "Teachers of LP Schools, West Jaintia Hills"),
    ("Medical College, Tura", "Medical College, Shillong"),
    ("Road in West Garo Hills", "Road in East Garo Hills"),
])
def test_conflicting_localities_block_a_merge(a, b):
    verdict, _title, reason = sem.check_deterministic_match(a, b)
    assert verdict is False
    assert "conflict" in reason.lower()


def test_same_town_is_not_a_conflict():
    a, b = sem.extract_locations("College of Architecture, Tura"), \
        sem.extract_locations("College of Architecture and Urban Planning, Tura")
    assert not sem.are_locations_conflicting(a, b)


def test_town_inside_its_district_is_not_a_conflict():
    a = sem.extract_locations("Tura, West Garo Hills")
    assert sem.are_locations_conflicting(a, sem.extract_locations("West Garo Hills")) is False


# ── named schemes: different programmes are different subjects ───────────────

@pytest.mark.parametrize("a,b", [
    ("Darenggre PHC", "Rongjeng CHC"),
    ("PHC in Tura", "CHC in Tura"),
    ("Status of JJM", "Status of PMGSY"),
])
def test_different_named_schemes_block_a_merge(a, b):
    verdict, _title, reason = sem.check_deterministic_match(a, b)
    assert verdict is False
    assert "different named schemes" in reason.lower()


def test_abbreviation_and_its_expansion_still_merge():
    verdict, title, reason = sem.check_deterministic_match(
        "Bhaitbari CHC", "Community Health Centre")
    assert verdict is True
    assert "abbreviation" in reason.lower()


def test_plurals_are_recognised_as_named_schemes():
    """'PHCs and CHCs' names two programmes and must not act as a bridge."""
    assert sem.abbrev_expansions("PHCs and CHCs assigned to NGO") == {
        "primary health centre", "community health centre"}
    assert sem.abbrev_expansions("Upgradation of existing PHCs to CHCs") == {
        "primary health centre", "community health centre"}


def test_spelled_out_scheme_names_are_recognised():
    found = sem.abbrev_expansions(
        "Upgradation of Darengre Primary Health Centre to Community Health Centre")
    assert found == {"primary health centre", "community health centre"}


# ── generic overlap is not evidence of a shared subject ──────────────────────

@pytest.mark.parametrize("a,b", [
    ("Health Centres in the State", "Community Health Centre"),
    ("Health Infrastructure", "Primary Health Centre"),
])
def test_generic_head_overlap_does_not_merge(a, b):
    verdict, _title, reason = sem.check_deterministic_match(a, b)
    assert verdict is False
    assert "generic" in reason.lower()


def test_specific_word_overlap_still_merges():
    verdict, _title, _reason = sem.check_deterministic_match(
        "Setting up of Sawsymper PHC", "PHC in Sawsymper")
    assert verdict is True


# ── typos and formatting ─────────────────────────────────────────────────────

def test_typos_are_folded():
    verdict, _title, reason = sem.check_deterministic_match(
        "Science and Commerce Collage at Mawphlang",
        "Science and Commerce College at Mawphlang")
    assert verdict is True
    assert reason


def test_identical_normalised_subject_merges():
    verdict, _title, reason = sem.check_deterministic_match(
        "Jal Jeevan Mission.", "jal  jeevan mission")
    assert verdict is True
    assert "identical" in reason.lower()


# ── the gate itself: an undecided pair is never merged ───────────────────────

def test_no_api_key_leaves_the_pair_unresolved():
    """A pair no rule can decide must not be merged just because the API is
    missing - that is how the method used to change with network state."""
    verdict, title, reason = sem.verify_pair_gate(
        "Rehabilitation of the bridge at Umsning",
        "Progress of market construction at Jowai",
        "Public Works (Roads)", 0.86, {}, api_key="")
    assert verdict == sem.UNRESOLVED
    assert title == ""
    assert "human" in reason.lower()


def test_a_pair_no_rule_can_decide_is_unresolved_even_without_a_key():
    verdict, _title, reason = sem.verify_pair_gate(
        "Functional Household Tap Connection under JJM",
        "Tap water coverage in Garo Hills",
        "Public Health Engineering", 0.86, {}, api_key="")
    assert verdict == sem.UNRESOLVED
    assert "human" in reason.lower()


def test_cached_verdicts_are_migrated_from_the_old_schema():
    entry = {"same_issue": True, "canonical_title": "x", "reason": "r"}
    sem._migrate_gate_entry("k", entry)
    assert entry["verdict"] == sem.SAME
    entry = {"same_issue": False, "canonical_title": "x", "reason": "r"}
    sem._migrate_gate_entry("k", entry)
    assert entry["verdict"] == sem.DIFFERENT


def test_cached_verdict_wins_over_re_asking_the_model():
    cache = {"d:::alpha:::beta":
             {"verdict": sem.SAME, "canonical_title": "a", "reason": "cached"}}
    verdict, title, _reason = sem.verify_pair_gate(
        "alpha", "beta", "d", 0.85, cache, api_key="")
    assert verdict == sem.SAME and title == "a"


def test_deterministic_rule_is_applied_before_any_cache():
    """A cache entry must not be able to override the locality gate."""
    cache = {"d:::PHC in Tura:::PHC in Shillong":
             {"verdict": sem.SAME, "canonical_title": "x", "reason": "stale"}}
    verdict, _title, reason = sem.verify_pair_gate(
        "PHC in Tura", "PHC in Shillong", "d", 0.99, cache, api_key="")
    assert verdict == sem.DIFFERENT and "conflict" in reason.lower()


# ── the published constants must agree with the code ─────────────────────────

def test_one_threshold_is_documented():
    assert sem.SIM_DETERMINISTIC_AUTO > sem.SIM_CANDIDATE
    assert sem.SIM_CANDIDATE == 0.84
    assert sem.EMBED_DIMS == 2048          # verified against the live endpoint
    assert "nemotron" in sem.EMBED_MODEL
