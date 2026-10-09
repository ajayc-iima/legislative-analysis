"""Thematic codebook: rule-based policy-domain classification.

Seeded from the legacy topic_hierarchy.json (17 top-level themes and
~140 subcluster labels) but keywords are hand-assigned to the theme they
actually describe — the legacy LLM clusters had cross-topic noise
(e.g. "Jal Jeevan Mission" under Education).

Design: keyword hits are counted per theme; the department's sector
(from ported DEPT_HIERARCHY) breaks ties; unmatched text is
"General / Other". Every classification records the evidence that
produced it, so any row can be audited.
"""

from . import reference_data as ref

# (theme, sub-theme, keywords). Keywords are matched as substrings on
# lowercased, punctuation-stripped text. Order matters: earlier themes
# win ties when two themes score equally.
CODEBOOK = [
    # ── Health ──
    ("Health Services", "Facilities", ["phc", "chc", "health centre", "health center", "sub centre",
     "sub center", "hospital", "medical college", "dispensary", "health sub centre", "upgradation of sub"]),
    ("Health Services", "Medical Staffing", ["doctor", "mbbs", "dentist", "specialist", "nurse",
     "staff nurse", "medical officer", "health officer", "vacant post", "sanctioned post"]),
    ("Health Services", "Substance Abuse", ["drug", "narcotic", "alcohol", "liquor", "de addiction",
     "addiction", "hiv", "aids", "substance abuse"]),
    ("Health Services", "Scheme Implementation", ["nhm", "nrhm", "ayushman", "pmjay", "mission health",
     "national health mission", "health insurance", "mjpjay"]),
    ("Health Services", "Disease & Mortality", ["death", "dead", "died", "disease", "patient",
     "maternal death", "infant death", "epidemic", "outbreak"]),

    # ── Education ──
    ("Education & Schools", "Schools", ["school", "lp school", "hs school", "primary school",
     "high school", "secondary school", "deficit school", "government school", "lp s school",
     "student", "pupil", "enrollment", "enrolment", "dropout"]),
    ("Education & Schools", "Teachers & Staff", ["teacher", "teaching staff", "assistant teacher",
     "post of teacher", "regularisation", "regularization of teacher", "posting of teacher"]),
    ("Education & Schools", "Higher Education", ["college", "university", "degree college",
     "polytechnic", "engineering college", "iit", "central university", "nehu", "martin luther"]),
    ("Education & Schools", "Schemes & Policy", ["ssa", "sarva shiksha", "rmsa", "mid day meal",
     "mid-day meal", "national education policy", " nep ", "eklavya", "emrs", "cbse", "board exam",
     "scholarship", "hostel"]),

    # ── Roads ──
    ("Roads & Infrastructure", "Roads", ["road", "pmgsy", "highway", "bypass", "blacktop",
     "black topping", "resurfacing", "metalling", "rcc road", "internal road", "approach road"]),
    ("Roads & Infrastructure", "Bridges", ["bridge", "culvert", "underpass", "flyover"]),
    ("Roads & Infrastructure", "Projects & Tenders", ["construction of", "upgradation of road",
     "repairing of", "maintenance of road", "tender", "work order", "project sanction"]),

    # ── Water ──
    ("Water Supply", "Piped Water", ["jal jeevan", "jjm", "fhtc", "functional household tap",
     "tap connection", "piped water", "water supply", "drinking water",
     "water supply scheme", "greater shillong water",
     "reticulated water"]),
    ("Water Supply", "Sanitation", ["swachh", "sbm", "sanitation", "toilet", "sewerage", "sewage",
     "liquid waste", "solid waste"]),
    ("Water Supply", "Irrigation & Conservation", ["irrigation", "check dam", "percolation",
     "water harvesting", "drip irrigation", "sprinkler", "soil and water conservation"]),

    # ── Power ──
    ("Power & Electricity", "Supply & Outages", ["power supply", "electricity supply", "load shedding",
     "power cut", "transformer", "electrification", "village electrification", "power interruption"]),
    ("Power & Electricity", "Distribution & Dues", ["mepdcl", "meghalaya power distribution",
     "energy corporation", "electricity bill", "power purchase", "outstanding dues", "substation",
     "132 kv", "33 kv", "11 kv"]),
    ("Power & Electricity", "Generation & Renewables", ["hydel", "hydro power", "power house",
     "solar", "renewable energy", "generator", "meghalaya energy"]),

    # ── Law & Order ──
    ("Law & Order", "Police", ["police", "ps", "police station", "police outpost", "pop",
     "sub inspector", "sp of", "fir", "arrest", "custody", "policeman", "police personnel",
     "police post", "community police"]),
    ("Law & Order", "Crime & Drugs", ["crime", "murder", "theft", "smuggling", "peddling",
     "ndps", "cyber crime", "trafficking", "kidnapping", "robbery", "snatching", "extortion"]),
    ("Law & Order", "Fire & Civil Defence", ["fire service", "fire station", "civil defence",
     "home guards", "emergency response"]),

    # ── Social Welfare ──
    ("Social Welfare", "Pensions & Assistance", ["pension", "old age", "widow", "disability",
     "divyang", "social security", "assistance to", "financial assistance", "one time grant"]),
    ("Social Welfare", "Women & Child", ["icds", "anganwadi", "child development", "women and child",
     "malnutrition", "nutrition", "maternity", "creche", "beti", "poshan"]),
    ("Social Welfare", "Welfare Boards & Schemes", ["social welfare", "welfare", "welfare board", "scholarship",
     "orphan", "destitute", "destitute", "adoption", "janaushadhi"]),

    # ── Employment ──
    ("Employment & Jobs", "Rural Employment", ["mgnrega", "mgnregs", "job card", "job-card",
     "rural employment", "employment guarantee", "vec ", "village employment"]),
    ("Employment & Jobs", "Recruitment", ["recruitment", "appointment", "vacancy", "vacant post",
     "selection committee", "post of", "engagement of", "engagement", "contractual",
     "backlog vacancy", "direct recruitment"]),
    ("Employment & Jobs", "Skill & Self Employment", ["skill", "mssds", "training centre",
     "self employment", "entrepreneur", "startup", "pmegp", "udyog", "unemployment",
     "employment exchange", "placement"]),
    ("Employment & Jobs", "Labour Welfare", ["labour", "worker", "shram", "unorganised",
     "unorganized", "minimum wage", "bonus", "welfare of workers", "migrant worker",
     "e-shram", "labour welfare"]),

    # ── Agriculture ──
    ("Agriculture & Farming", "Crops", ["paddy", "rice", "ginger", "turmeric", "areca", "betel nut",
     "arecanut", "black pepper", "broom grass", "maize", "potato", "vegetable", "spice",
     "crop production", "cultivation"]),
    ("Agriculture & Farming", "Schemes & Infrastructure", ["focus", "pmkisan", "kisan credit",
     "agriculture", "farmer", "farm", "godown", "cold storage", "warehouse", "seed",
     "fertilizer", "subsidy"]),
    ("Agriculture & Farming", "Allied Activities", ["animal husbandry", "veterinary", "dairy",
     "poultry", "piggery", "fisheries", "aquaculture", "sericulture", "horticulture",
     "banana", "orange", "areca nut plantation", "apple"]),

    # ── Urban ──
    ("Urban Development", "Municipal Services", ["municipal", "municipality", "urban", "shillong municipal",
     "tura municipal", "ward", "urban local body", "urban affairs"]),
    ("Urban Development", "City Infrastructure", ["market", "parking", "traffic", "street light",
     "streetlight", "solid waste", "dumping ground", "sewerage", "smart city", "town",
     "market complex", "hawker"]),
    ("Urban Development", "Housing", ["housing board", "rental house", "mig", "lig", "economically weaker",
     "urban housing", "pmay", "awas"]),

    # ── Governance ──
    ("Governance & Administration", "Administration", ["government employee", "transfer",
     "posting", "department", "scheme implementation", "policy", "notification", "order",
     "chief minister", "minister in charge", "secretariat", "administrative"]),
    ("Governance & Administration", "Digital & IT", ["internet", "mobile tower", "broadband",
     "digital", "online portal", "it park", "data centre", "wifi", "connectivity project",
     "information technology", "e-governance"]),
    ("Governance & Administration", "Missions & Funds", ["cm special", "chief minister special",
     "special development fund", "mbda", "basin development", "sasci", "sasci"]),
    ("Governance & Administration", "Transparency", ["rti", "right to information", "corruption",
     "vigilance", "audit", "accountability", "grievance", "public servant"]),

    # ── Finance ──
    ("Finance & Budget", "Revenue & Taxation", ["revenue collection", "tax", "taxation", "gst",
     "excise duty", "non tax revenue", "receipt", "collection of revenue", "irregularities",
     "revenue receipt"]),
    ("Finance & Budget", "Expenditure & Budget", ["budget", "expenditure", "allocation",
     "financial year", "crore", "granted", "supplementary", "surrender", "savings",
     "account of state", "funds released"]),

    # ── Mining ──
    ("Mining & Geology", "Mining Operations", ["mining", "coal", "limestone", "quarry",
     "minor mineral", "sand mining", "stone crusher", "mineral"]),
    ("Mining & Geology", "Revenue & Regulation", ["mine", "lease", "minerall", "geology",
     "mining lease", "royalty", "illegal mining", "cement plant", "coal mine"]),

    # ── District Council ──
    ("District Council", "ADC Affairs", ["district council", "autonomous district council",
     "adc", "traditional head", "syiem", "nokma", "rajabahadur", "village council",
     "village employment council"]),
    ("District Council", "Council Powers", ["sixth schedule", "autonomous district",
     "council election", "council fund", "district council affairs"]),

    # ── Tribal & Traditional ──
    ("Tribal & Traditional", "Language & Culture", ["khasi language", "garo language", "jaintia",
     "8th schedule", "eighth schedule", "script", "language", "literature", "culture",
     "tradition", "customary law"]),
    ("Tribal & Traditional", "Land & Rights", ["inner line permit", "ilp", "land record",
     "land acquisition", "land use", "deed", "land revenue", "document registration",
     "inheritance", "community land"]),

    # ── Border ──
    ("Border & Inter-State", "Assam Border", ["assam border", "inter state boundary",
     "boundary dispute", "border dispute", "border piller", "border pillar", "meghalaya assam",
     "boundary agreement", "joint working committee"]),
    ("Border & Inter-State", "International Border", ["bangladesh", "international border",
     "zero line", "fence", "border trade", "haat", "dawki", "transit"]),

    # ── Environment ──
    ("Environment & Natural Resources", "Forests & Wildlife", ["forest", "wildlife", "tiger",
     "elephant", "national park", "sanctuary", "jhum", "afforestation", "social forestry",
     "timber", "felling"]),
    ("Environment & Natural Resources", "Pollution & Climate", ["pollution", "environment",
     "climate change", "waste management", "emission", "noise", "air quality", "river",
     "catchment", "conservation of"]),
]

# Department → theme prior (used to break ties and to classify text with
# no keyword hits). Derived from the ported DEPT_HIERARCHY sector map.
DEPT_SECTOR_THEME = {
    "Social Services": "Education & Schools",
    "Infrastructure": "Roads & Infrastructure",
    "Primary Sector": "Agriculture & Farming",
    "Administration": "Governance & Administration",
    "Revenue": "Finance & Budget",
    "Strategic": "Governance & Administration",
    "Governance": "Governance & Administration",
    "Executive": "Governance & Administration",
    "Commerce": "Governance & Administration",
}

DEPT_THEME = {
    "Education": "Education & Schools",
    "Health & Family Welfare": "Health Services",
    "Social Welfare": "Social Welfare",
    "Women & Child Development": "Social Welfare",
    "Sports & Youth Affairs": "Governance & Administration",
    "Public Works (Roads)": "Roads & Infrastructure",
    "Public Works (Buildings)": "Roads & Infrastructure",
    "Power": "Power & Electricity",
    "Water Resources": "Water Supply",
    "Public Health Engineering": "Water Supply",
    "Transport": "Roads & Infrastructure",
    "Agriculture": "Agriculture & Farming",
    "Animal Husbandry & Veterinary": "Agriculture & Farming",
    "Fisheries": "Agriculture & Farming",
    "Forests & Environment": "Environment & Natural Resources",
    "Horticulture": "Agriculture & Farming",
    "Sericulture & Weaving": "Agriculture & Farming",
    "Mining & Geology": "Mining & Geology",
    "Home (Police)": "Law & Order",
    "Home (Political)": "Law & Order",
    "Home (Civil Defence)": "Law & Order",
    "District Council Affairs": "District Council",
    "Urban Affairs": "Urban Development",
    "Community & Rural Development": "Employment & Jobs",
    "General Administration": "Governance & Administration",
    "Personnel & AR": "Employment & Jobs",
    "Revenue & Disaster Management": "Finance & Budget",
    "Finance": "Finance & Budget",
    "Registration & Stamps": "Tribal & Traditional",
    "Border Areas": "Border & Inter-State",
    "Meghalaya Basin Dev. Authority": "Governance & Administration",
    "IT & Communication": "Governance & Administration",
    "Tourism": "Environment & Natural Resources",
    "Law": "Law & Order",
    "Parliamentary Affairs": "Governance & Administration",
    "Elections": "Governance & Administration",
    "Information & Public Relations": "Governance & Administration",
    "Chief Minister": "Governance & Administration",
    "Planning": "Governance & Administration",
    "Food & Civil Supplies": "Governance & Administration",
    "Commerce & Industries": "Agriculture & Farming",
    "Excise": "Law & Order",
    "Labour": "Employment & Jobs",
    "Housing": "Urban Development",
    "Prisons & Correctional Services": "Law & Order",
}


# Aliases for long portal forms absent from the legacy table.
DEPT_NORM_EXTRA = {
    "department of labour, employment & skill development": "Labour",
}


def normalize_dept(name):
    """Canonical department name via the ported alias table."""
    key = " ".join(str(name or "").lower().split())
    if key in DEPT_NORM_EXTRA:
        return DEPT_NORM_EXTRA[key]
    if key in ref.DEPT_NORM:
        return ref.DEPT_NORM[key]
    # long portal forms: "Department of Labour, Employment & ..." / "... Department"
    for variant in (key.removeprefix("department of ").removesuffix(" department"),
                    key.removesuffix(" department"),
                    key.removeprefix("department of ")):
        if variant in ref.DEPT_NORM:
            return ref.DEPT_NORM[variant]
    return str(name or "").strip() or "Unknown"


def _clean(text):
    """Lowercase with punctuation folded to spaces (keyword-match friendly)."""
    import re
    return " " + re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()) + " "


# Plural exceptions shared with analysis.normalize_subject: words whose
# trailing 's' must not be folded ('status' -> 'statu' would be wrong).
SINGULAR_EXCEPTIONS = {"news", "status", "crisis", "class", "gas", "bus",
                       "lens", "series", "basis", "analysis", "species"}


def _stem(word):
    if len(word) > 3 and word.endswith("s") and word not in SINGULAR_EXCEPTIONS:
        return word[:-1]
    return word


def _kw_hit(keyword, text_tokens):
    """Stemmed token-sequence match: 'road' hits 'roads', but 'ps'
    never hits 'collapse' and 'fir' never hits 'affirmative'.

    Single-token keywords match whole tokens only; multi-word
    keywords must appear as a contiguous token run.
    """
    parts = [_stem(w) for w in _clean(keyword).split()]
    if not parts:
        return False
    if len(parts) == 1:
        return parts[0] in text_tokens
    return any(text_tokens[i:i + len(parts)] == parts
               for i in range(len(text_tokens) - len(parts) + 1))


def classify(subject, question_text, department):
    """Return (theme, sub_theme, evidence) for one question.

    evidence lists which keywords hit and whether the department prior
    was used, so every classification is auditable.
    """
    text = _clean(subject) + _clean(question_text)
    text_tokens = [_stem(w) for w in text.split()]
    dept = normalize_dept(department)
    dept_theme = DEPT_THEME.get(dept)
    if dept_theme is None:
        sector = ref.DEPT_HIERARCHY.get(dept, {}).get("parent")
        dept_theme = DEPT_SECTOR_THEME.get(sector)

    scores = {}
    hits = {}
    for theme, sub, keywords in CODEBOOK:
        for kw in keywords:
            if _kw_hit(kw, text_tokens):
                scores[theme] = scores.get(theme, 0) + 1
                hits.setdefault(theme, []).append((sub, kw))

    if not scores:
        if dept_theme:
            return dept_theme, "", {"method": "department_prior", "department": dept}
        return "General / Other", "", {"method": "fallback", "department": dept}

    best = max(scores.values())
    tied = sorted(t for t, s in scores.items() if s == best)
    if len(tied) > 1 and dept_theme in tied:
        winner = dept_theme
        how = "keyword_tiebreak_department"
    else:
        winner = tied[0]
        how = "keyword"
    # dominant sub-theme = the sub-theme with most hits in winning theme
    sub_counts = {}
    for sub, kw in hits.get(winner, []):
        sub_counts[sub] = sub_counts.get(sub, 0) + 1
    sub = max(sub_counts, key=sub_counts.get) if sub_counts else ""
    return winner, sub, {"method": how, "keywords": sorted({kw for _, kw in hits.get(winner, [])}),
                         "scores": scores}


def classify_all(rows, subject_of):
    """Annotate each question row dict in place with theme/sub_theme."""
    for row in rows:
        theme, sub, ev = classify(subject_of(row), row.get("Questions"), row.get("Departments"))
        row["_theme"] = theme
        row["_sub_theme"] = sub
        row["_theme_evidence"] = ev
    return rows
