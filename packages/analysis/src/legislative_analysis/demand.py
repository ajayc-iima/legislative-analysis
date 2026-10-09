"""Demand-type taxonomy: what each question demands of government.

Four types (PLAN.md Task 1.3), adapted from the legacy
_STRENGTH_ORDER but rule-based and auditable:

  Information       — "how many", "what is the status", counts
  Explanation       — "why", "reasons for", causes
  Action            — "whether the government will", "steps taken",
                      demands for doing something
  Accountability    — re-raised issue: the subject already appeared
                      in an earlier session (set by the caller via
                      the recurring map)

Each question gets a primary type plus per-type evidence lists, so
the classification can be audited row by row.
"""

import re

PATTERNS = {
    "Information": [
        r"\bhow many\b", r"\bhow much\b", r"\bwhat is the (?:total )?number\b",
        r"\bnumber of\b", r"\bcount of\b", r"\bquantity of\b",
        r"\bstatus of\b", r"\bwhat is the status\b", r"\bwhether .* is (?:true|functional|available)\b",
        r"\blist of\b", r"\bdetails of\b", r"\bamount of\b", r"\btotal\b",
        r"\bwhat are\b", r"\bwhat is\b", r"\bis there any\b", r"\bwhether\b",
    ],
    "Explanation": [
        r"\bwhy\b", r"\breasons? for\b", r"\bcause of\b", r"\bcauses of\b",
        r"\bfactors (?:contributing|responsible)\b", r"\bon what basis\b",
        r"\bwhy has\b", r"\bwhy have\b", r"\bwhy is\b", r"\bwhy was\b",
        r"\bwhat are the reasons\b", r"\bhow come\b",
    ],
    "Action": [
        r"\bsteps (?:being |are being |will be |have been )?taken\b",
        r"\baction taken\b", r"\bactions taken\b", r"\bwhat steps\b",
        r"\bmeasures taken\b", r"\bwill (?:the |it |the government )?(?:take|ensure|provide|implement|do)\b",
        r"\bwhether the government (?:will|has)\b",
        r"\bwhat is the government doing\b", r"\bplan to\b",
        r"\bproposal to\b", r"\bwhether any (?:instructions|orders|notification)\b",
        r"\bwhether .* will\b", r"\bto be taken\b", r"\binitiative taken\b",
    ],
}

# Accountability is not text-matched; it is structural (recurring
# subject). This pattern only catches explicit follow-up language.
FOLLOWUP_RE = re.compile(
    r"\b(?:re[- ]?raised|again|once more|repeatedly|still pending|"
    r"earlier also|previous(?:ly)? (?:also|session|year)|last session|"
    r"follow[- ]?up|subsequent|as per (?:the |an? )?(?:earlier |previous )?(?:assurance|commitment|reply))\b",
    re.I,
)


def classify_demand(question_text, is_recurring=False):
    """Return (primary_type, evidence) for one question."""
    text = str(question_text or "")
    blob = " " + re.sub(r"\s+", " ", text.lower()) + " "

    hits = {}
    for dtype, patterns in PATTERNS.items():
        found = []
        for pat in patterns:
            m = re.search(pat, blob)
            if m:
                found.append(m.group(0).strip())
        if found:
            hits[dtype] = found

    evidence = {"hits": hits, "followup_language": bool(FOLLOWUP_RE.search(text)),
                "recurring_subject": bool(is_recurring)}

    if not hits:
        return "Information", evidence  # questions are overwhelmingly requests for data

    # Accountability wins when the subject is re-raised or the
    # question explicitly references a prior commitment.
    if is_recurring or evidence["followup_language"]:
        if "Action" in hits or "Information" in hits:
            return "Accountability", evidence

    # Otherwise: explanation outranks action outranks information
    # (a "why" question demands reasoning, not just data).
    for dtype in ("Explanation", "Action", "Information"):
        if dtype in hits:
            return dtype, evidence
    return "Information", evidence


def classify_all(rows, subject_of, recurring_keys):
    """Annotate rows with _demand_type and _demand_evidence."""
    for row in rows:
        from .codebook import _clean
        key = " ".join(re.sub(r"[^a-z0-9 ]+", " ",
                              str(subject_of(row) or "").lower()).split())
        dtype, ev = classify_demand(row.get("Questions"),
                                    is_recurring=key in recurring_keys)
        row["_demand_type"] = dtype
        row["_demand_evidence"] = ev
    return rows
