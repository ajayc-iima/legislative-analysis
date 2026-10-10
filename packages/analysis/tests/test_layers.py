"""Tests for the six analytical layers (synthetic data only)."""

from legislative_analysis import analysis as base
from legislative_analysis import codebook, demand, geography, longitudinal
from legislative_analysis import response as resp_mod


def _row(**kw):
    row = {"Assembly": "Eleventh", "Session": "Autumn Session, 2025",
           "Session_Date": "15/Oct/2025", "Subject": "", "Questions": "",
           "Departments": "", "Asked_By": "", "Question_Number": "Q.No 1",
           "Document_Link": ""}
    row.update(kw)
    return row


# ── Layer 1: thematic codebook ──

def test_theme_keyword_health():
    theme, sub, ev = codebook.classify(
        "Upgradation of Sub-Centers to PHCs", "", "Health & Family Welfare")
    assert theme == "Health Services"
    assert sub == "Facilities"
    assert ev["method"] == "keyword"
    assert ev["keywords"]  # evidence recorded for audit


def test_theme_keyword_roads():
    theme, sub, _ev = codebook.classify(
        "Repairing of internal roads in the village", "", "Power")
    assert theme == "Roads & Infrastructure"


def test_theme_department_prior_when_no_keywords():
    theme, _sub, ev = codebook.classify(
        "A vague subject with no matching terms whatsoever xyz",
        "", "Power Department")
    assert theme == "Power & Electricity"
    assert ev["method"] == "department_prior"


def test_theme_fallback_general_other():
    theme, _sub, ev = codebook.classify("xyzzy nothing matches", "", "Unknown Dept")
    assert theme == "General / Other"
    assert ev["method"] == "fallback"


def test_theme_tiebreak_prefers_own_department():
    # "hospital" (health) + "road" (roads) score 1-1: Health dept wins the tie
    theme, _sub, ev = codebook.classify(
        "hospital road", "", "Health & Family Welfare")
    assert theme == "Health Services"
    assert ev["method"] == "keyword_tiebreak_department"


def test_short_keywords_need_whole_words():
    # regression: 'fir' fired inside "affirmative", 'ps' inside longer words
    theme, _sub, ev = codebook.classify(
        "Whether the government has knowledge of the affirmative report",
        "", "Health & Family Welfare")
    assert theme == "Health Services"
    assert ev["method"] == "department_prior"
    theme, _sub, ev = codebook.classify(
        "The status of the building collapse inquiry", "", "Health & Family Welfare")
    assert theme == "Health Services"


def test_plural_keywords_still_match():
    theme, _sub, _ev = codebook.classify(
        "Repairing of internal roads", "", "Power")
    assert theme == "Roads & Infrastructure"


def test_water_supply_and_labour_classification():
    theme, _sub, _ev = codebook.classify(
        "Upper Shillong Water Supply Project",
        'the status of the scheme "Upper Shillong Water Supply Project"?',
        "Public Health Engineering Department")
    assert theme == "Water Supply"
    theme, _sub, _ev = codebook.classify(
        "Registration under E-Shram Portal",
        "measures for the welfare and safety of unorganised workers",
        "Department of Labour, Employment & Skill Development")
    assert theme == "Employment & Jobs"


def test_normalize_dept_long_portal_forms():
    assert codebook.normalize_dept(
        "Department of Labour, Employment & Skill Development") == "Labour"
    assert codebook.normalize_dept("Health &  Family Welfare Department") == "Health & Family Welfare"


def test_normalize_dept_uses_ported_aliases():
    assert codebook.normalize_dept("Power Department") == "Power"
    assert codebook.normalize_dept("Health & Family Welfare Department") == "Health & Family Welfare"
    assert codebook.normalize_dept("Public Work Department(Road)") == "Public Works (Roads)"


# ── Layer 2: geography ──

def test_mla_lookup_exact():
    geo = geography.lookup_mla("Metbah Lyngdoh")
    assert geo["constituency"] == "Mairang"
    assert geo["district"] == "Eastern West Khasi Hills"
    assert geo["region"] == "Khasi Hills"


def test_mla_lookup_tolerates_trailing_comma():
    geo = geography.lookup_mla("Lambor Malngiang,")
    assert geo["constituency"] == "Nongkrem"


def test_mla_lookup_historical():
    assert geography.lookup_mla("Azad Zaman")["constituency"] == "Rajabala"
    assert geography.lookup_mla("David A Nongrum")["constituency"] == "Mawryngkneng"


def test_mla_lookup_unknown_returns_none():
    assert geography.lookup_mla("Nobody Here") is None


def test_party_and_bloc_of_askers():
    assert geography.party_of("Metbah Lyngdoh", "Eleventh Assembly") == "UDP"
    assert geography.party_of("Metbah Lyngdoh", "Tenth Assembly") == "UDP"
    assert geography.bloc_of("Metbah Lyngdoh", "Eleventh Assembly") == "Ruling"
    assert geography.bloc_of("Mukul Sangma", "Eleventh Assembly") == "Opposition"
    assert geography.bloc_of("Azad Zaman", "Tenth Assembly") == "Opposition"
    assert geography.bloc_of("Nobody Here", "Eleventh Assembly") == "Unknown"
    assert geography.bloc_of("Mehtab Chandee A Sangma", "Eleventh Assembly") == "Opposition"
    assert geography.lookup_mla("Mehtab Chandee A Sangma")["constituency"] == "Gambegre"


def test_mentioned_tops_counts_text_mentions():
    rows = [
        {"_mentioned_districts": ["east khasi hills"], "_mentioned_places": ["shillong"]},
        {"_mentioned_districts": ["east khasi hills", "ri bhoi"], "_mentioned_places": []},
        {"_mentioned_districts": [], "_mentioned_places": []},
    ]
    tops = geography.mentioned_tops(rows, top=10)
    assert tops["districts"][0] == {"place": "east khasi hills", "questions": 2,
                                    "share_pct": 66.7}
    assert tops["questions_with_any_mention"] == 2
    assert tops["share_with_any_mention_pct"] == 66.7


def test_gazetteer_finds_district():
    places = geography.find_places("Jal Jeevan Mission in East Khasi Hills")
    assert any(p["place"] == "east khasi hills" and p["level"] == "district"
               for p in places)


def test_scope_state_wide_without_places():
    row = _row(Subject="Policy on renewable energy tariffs",
               Questions="What is the policy?", Asked_By="Metbah Lyngdoh")
    geography.tag_row(row, base.subject_of)
    assert row["_mla_constituency"] == "Mairang"
    assert row["_scope"] == "state_wide"


def test_scope_constituency_specific():
    row = _row(Subject="Bridges damaged due to flood in Rajabala constituency",
               Questions="How many bridges?", Asked_By="Mizanur Rahman Kazi")
    geography.tag_row(row, base.subject_of)
    assert row["_mla_constituency"] == "Rajabala"
    assert row["_scope"] == "constituency_specific"
    assert "west garo hills" in [d.lower() for d in row["_mentioned_districts"]]


# ── Layer 3: demand types ──

def test_demand_information():
    dtype, _ev = demand.classify_demand("How many teachers are posted in the district?")
    assert dtype == "Information"


def test_demand_explanation():
    dtype, _ev = demand.classify_demand("Why has the road project been delayed for two years?")
    assert dtype == "Explanation"


def test_demand_action():
    dtype, _ev = demand.classify_demand(
        "Whether the government will construct a new bridge over the river?")
    assert dtype == "Action"


def test_demand_accountability_for_recurring():
    dtype, ev = demand.classify_demand("How many transformers were replaced?",
                                       is_recurring=True)
    assert dtype == "Accountability"
    assert ev["recurring_subject"] is True


def test_demand_accountability_for_followup_language():
    dtype, ev = demand.classify_demand(
        "What is the follow-up on the assurance given last session?")
    assert dtype == "Accountability"
    assert ev["followup_language"] is True


# ── Layer 4: response quality ──

def test_response_brief_low_specificity():
    coding = resp_mod.code_reply("Sir, yes.")
    assert coding["substantiveness"]["band"] == "brief"
    assert coding["specificity"]["level"] == "low"


def test_response_detailed_high_specificity():
    text = ("Sir, Rs. 126,94,00,000 has been sanctioned under the Jal Jeevan "
            "Mission. 50% of the work is completed as on 12 March 2025 and the "
            "scheme will cover 200 villages. " + "Additional detail. " * 60)
    coding = resp_mod.code_reply(text)
    assert coding["substantiveness"]["band"] in ("detailed", "very_detailed")
    assert coding["specificity"]["level"] == "high"
    assert coding["specificity"]["amounts"] >= 1
    assert coding["actionability"]["has_budget"] is True


def test_response_boilerplate_detected():
    coding = resp_mod.code_reply(
        "Sir, the matter is receiving attention and necessary steps will be "
        "taken at the earliest. The government is seized of the matter.")
    assert coding["boilerplate"] is True
    assert coding["evasion"]["weight"] > 0


def test_response_contradiction_detected():
    coding = resp_mod.code_reply(
        "Sir, the bridge work has been completed in all respects but funds "
        "have not yet been released so the project is still pending.")
    assert coding["contradiction"]["has_contradiction"] is True


def test_response_no_contradiction_for_clean_reply():
    coding = resp_mod.code_reply(
        "Sir, the bridge work has been completed and Rs. 5 crore released.")
    assert coding["contradiction"]["has_contradiction"] is False


def test_response_timeline_detected():
    coding = resp_mod.code_reply(
        "Sir, the project is expected to be completed by March 2026.")
    assert coding["actionability"]["has_timeline"] is True


def test_execution_stage_ranks_highest_evidence():
    coding = resp_mod.code_reply(
        "Sir, the proposal was submitted and sanctioned. Tenders were floated "
        "and the work order awarded. Work is in progress.")
    assert coding["execution_stage"]["stage"] == "Implementation"
    assert coding["execution_stage"]["index"] == 7


def test_execution_stage_ignores_negated_claims():
    coding = resp_mod.code_reply("Sir, no proposal exists and no funds were sanctioned.")
    assert coding["execution_stage"]["index"] == 0
    assert coding["execution_stage"]["stage"] == "None evidenced"


def test_execution_stage_completion():
    coding = resp_mod.code_reply("Sir, the bridge has been completed and commissioned.")
    assert coding["execution_stage"]["stage"] == "Completion"


def test_progress_evidence_detected():
    coding = resp_mod.code_reply(
        "Sir, physical progress is 78% and the measurement book has been verified.")
    assert coding["actionability"]["has_progress_evidence"] is True
    coding = resp_mod.code_reply("Sir, the matter is under consideration.")
    assert coding["actionability"]["has_progress_evidence"] is False


def test_latency_and_timeliness():
    assert resp_mod.latency("2026-08-21", "2026-08-07") == 14
    assert resp_mod.latency("", "2026-08-07") is None
    summary = resp_mod.timeliness_summary(
        [{"_latency_days": 14}, {"_latency_days": 40}, {"_latency_days": None}])
    assert summary["n"] == 2
    assert summary["median_days"] == 27.0
    assert summary["share_over_30d"] == 50.0


def test_dates_trustworthy_clean_record():
    assert resp_mod.dates_trustworthy({"needs_review": []}) is True
    assert resp_mod.dates_trustworthy({"needs_review": ["no submission date found"]}) is True


def test_dates_trustworthy_flags_implausible_pair():
    rec = {"needs_review": ["submission date 2016-08-17 far from sitting 2026-08-28"]}
    assert resp_mod.dates_trustworthy(rec) is False
    rec = {"needs_review": ["reply date precedes submission date"]}
    assert resp_mod.dates_trustworthy(rec) is False


# ── Layers 5-6: longitudinal ──

def test_trajectory_awaiting_replies():
    status, _detail = longitudinal.code_trajectory([("s1", ""), ("s2", "")])
    assert status == "awaiting_replies"


def test_trajectory_resolved():
    status, _detail = longitudinal.code_trajectory([
        ("s1", "The matter is under consideration."),
        ("s2", "The bridge has been completed and commissioned.")])
    assert status == "resolved"


def test_trajectory_regressed():
    status, _detail = longitudinal.code_trajectory([
        ("s1", "The project is completed."),
        ("s2", "No proposal exists and funds have not been released.")])
    assert status == "regressed"


def test_trajectory_stalled():
    status, _detail = longitudinal.code_trajectory([
        ("s1", "The matter is under consideration."),
        ("s2", "Necessary steps are being taken at the earliest.")])
    assert status == "stalled"


def test_build_families_groups_recurring():
    rows = [
        _row(Assembly="A10", Session="S1", Subject="Replacement of Transformers",
             Departments="Power", Asked_By="X", Question_Number="Q.No 10"),
        _row(Assembly="A11", Session="S2", Subject="Replacement of transformers",
             Departments="Power", Asked_By="Y", Question_Number="Q.No 10"),
        _row(Assembly="A11", Session="S2", Subject="Something entirely different here",
             Departments="Health", Asked_By="Z", Question_Number="Q.No 5"),
    ]
    order = [("A10", "S1"), ("A11", "S2")]
    families = longitudinal.build_families(rows, base.subject_of, {}, order)
    assert len(families) == 1
    fam = next(iter(families.values()))
    assert fam["trajectory"] == "awaiting_replies"
    assert fam["occurrences"] == 2
    assert set(fam["askers"]) == {"X", "Y"}


def test_family_subject_strips_question_number():
    rows = [
        _row(Assembly="A10", Session="S1", Subject="Q.No 10\nReplacement of Transformers",
             Departments="Power", Asked_By="X"),
        _row(Assembly="A11", Session="S2", Subject="Q.No 10\nReplacement of transformers",
             Departments="Power", Asked_By="Y"),
    ]
    families = longitudinal.build_families(rows, base.subject_of, {}, [("A10", "S1"), ("A11", "S2")])
    assert next(iter(families.values()))["subject"] == "Replacement of Transformers"


def test_build_families_codes_resolution_from_replies():
    rows = [
        _row(Assembly="A10", Session="S1", Subject="Replacement of Transformers",
             Departments="Power", Asked_By="X", Question_Number="Q.No 10",
             Document_Link="http://x/a.pdf"),
        _row(Assembly="A11", Session="S2", Subject="Replacement of transformers",
             Departments="Power", Asked_By="Y", Question_Number="Q.No 10",
             Document_Link="http://x/b.pdf"),
    ]
    order = [("A10", "S1"), ("A11", "S2")]
    reply_lookup = {
        "a.pdf": {"reply": "The matter is under consideration."},
        "b.pdf": {"reply": "All transformers have been completed and commissioned."},
    }
    families = longitudinal.build_families(rows, base.subject_of, reply_lookup, order)
    assert next(iter(families.values()))["trajectory"] == "resolved"


def test_build_families_tracks_stage_progression():
    rows = [
        _row(Assembly="A10", Session="S1", Subject="A new bridge project here",
             Departments="Power", Asked_By="X", Question_Number="Q.No 10",
             Document_Link="http://x/a.pdf"),
        _row(Assembly="A11", Session="S2", Subject="A new bridge project here",
             Departments="Power", Asked_By="Y", Question_Number="Q.No 10",
             Document_Link="http://x/b.pdf"),
    ]
    order = [("A10", "S1"), ("A11", "S2")]
    reply_lookup = {
        "a.pdf": {"reply": "The proposal has been submitted for examination."},
        "b.pdf": {"reply": "The bridge work has been completed and commissioned."},
    }
    families = longitudinal.build_families(rows, base.subject_of, reply_lookup, order)
    fam = next(iter(families.values()))
    assert fam["stage_first"] == "Administrative Processing"
    assert fam["stage_last"] == "Completion"
    assert fam["stage_delta"] == 6


def test_department_trends_normalizes_variants():
    rows = [
        _row(Assembly="A", Session="S1", Departments="Power Department"),
        _row(Assembly="A", Session="S2", Departments="Power"),
        _row(Assembly="A", Session="S2", Departments="Power Department"),
    ]
    order = [("A", "S1"), ("A", "S2")]
    trends = longitudinal.department_trends(rows, order)
    assert trends["Power"]["series"] == [1, 2]
    assert trends["Power"]["last_delta"] == 1


def test_new_vs_recurring_first_session_all_new():
    rows = [_row(Assembly="A", Session="S1", Subject="A brand new subject here")]
    out = longitudinal.new_vs_recurring(rows, base.subject_of, [("A", "S1")])
    assert out["A S1"]["new"] == 1 and out["A S1"]["recurring"] == 0


def test_emerging_issues_requires_two_askers():
    rows = [
        _row(Assembly="A", Session="S3", Subject="Mission Education rollout plan",
             Departments="Education", Asked_By="X"),
        _row(Assembly="A", Session="S3", Subject="Mission education rollout plan",
             Departments="Education", Asked_By="Y"),
        _row(Assembly="A", Session="S3", Subject="Solo subject raised once here",
             Departments="Health", Asked_By="X"),
    ]
    order = [("A", "S1"), ("A", "S2"), ("A", "S3")]
    emerging = longitudinal.emerging_issues(rows, base.subject_of, order)
    subjects = [e["subject"].lower() for e in emerging]
    assert any("mission education" in s for s in subjects)
    assert not any("solo subject" in s for s in subjects)


def test_diversity_index_counts_departments_per_mla():
    rows = [
        _row(Assembly="A", Session="S1", Departments="Power", Asked_By="X"),
        _row(Assembly="A", Session="S1", Departments="Health", Asked_By="X"),
        _row(Assembly="A", Session="S1", Departments="Power", Asked_By="Y"),
    ]
    out = longitudinal.diversity_index(rows, [("A", "S1")])
    assert out["A S1"] == 1.5
