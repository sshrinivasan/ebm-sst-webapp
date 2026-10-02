"""Intake question definitions + applicability logic (from intake_quiz.md).

Always-ask: Q21 (report type), Q22(a) (DWDA exploratory boreholes).
Conditional: Q22(c) (EM survey, only when no sump found), Q14 (chloride
threshold, only when background chloride is in play), Q6 (impact volume).
Auto-derived (shown in review, not asked): Q0 (identity reconciliation),
Q1 (site type), Q22(b) (sump found — from excel_data.json's dwda_data).
"""
from __future__ import annotations

from typing import Any

from .session import ReportSession

# ---------------------------------------------------------------------------
# Question definitions
# ---------------------------------------------------------------------------

QUESTION_DEFS: dict[str, dict[str, Any]] = {
    "q21": {
        "id": "q21",
        "title": "Report type",
        "prompt": (
            "Is this a Presence/Absence Phase 2 assessment, or a Standard "
            "Tier 1 routine report (characterization + delineation + closure "
            "evaluation)?"
        ),
        "type": "radio",
        "options": ["Presence/Absence P2", "Standard Tier 1 P1"],
        "always": True,
    },
    "q22a": {
        "id": "q22a",
        "title": "DWDA exploratory boreholes",
        "prompt": (
            "For the DWDA, how many exploratory boreholes were advanced to "
            "locate the drilling waste disposal area, and what are their "
            "borehole IDs? (e.g. BH26-01 to BH26-04.)"
        ),
        "type": "text",
        "always": True,
    },
    "q22c": {
        "id": "q22c",
        "title": "Geophysical (EM) survey",
        "prompt": (
            "Was a geophysical (EM) survey conducted at this site? If so, did "
            "it show a response indicative of a drilling waste disposal area?"
        ),
        "type": "radio",
        "options": [
            "No survey was conducted",
            "Survey conducted, no anomaly/response indicative of a DWDA",
            "Survey conducted, anomaly present but not attributed to a DWDA",
        ],
        "always": False,
    },
    "q14": {
        "id": "q14",
        "title": "Site-specific chloride threshold",
        "prompt": (
            "What is the site-specific chloride threshold used for "
            "delineation (mg/kg and/or mg/L)?"
        ),
        "type": "text",
        "always": False,
    },
    "q6": {
        "id": "q6",
        "title": "Estimated volume of impact",
        "prompt": (
            "What is the estimated volume of impact (m³ and tonnes)?"
        ),
        "type": "text",
        "always": False,
    },
}

# Auto-derived questions surfaced in the review step (not asked).
AUTO_DERIVED_IDS = ["q0", "q1", "q22b"]


# ---------------------------------------------------------------------------
# Applicability logic
# ---------------------------------------------------------------------------


def _dwda_found(session: ReportSession) -> bool:
    """Q22(b): sump found iff excel_data.json's dwda_data is non-null."""
    dwda = session.excel_data.get("dwda_data")
    return dwda is not None and bool(dwda)


def _background_chloride_in_play(session: ReportSession) -> bool:
    """Q14: background chloride detected AND a background outcome applies.

    Heuristic over excel_data.json: look for chloride delineation data with a
    background outcome (NOT_ACHIEVED_BACKGROUND / ACHIEVED_ALL with
    background). Falls back to True when the data is ambiguous so the
    question is asked rather than silently skipped.
    """
    data = session.excel_data
    for key in ("chloride_delineation_data", "cl_delineation", "chloride"):
        block = data.get(key)
        if isinstance(block, dict):
            outcome = str(block.get("outcome", "")).upper()
            if "BACKGROUND" in outcome:
                return True
            if "ACHIEVED" in outcome:
                return True
    # No explicit signal: ask if any chloride data exists at all.
    return bool(data.get("chloride_delineation_data") or data.get("cl_delineation"))


def _has_impacts(session: ReportSession) -> bool:
    """Q6: estimated volume of impact applies when exceedances exist."""
    data = session.excel_data
    exc = data.get("tier1_exceedances") or data.get("exceedances")
    if isinstance(exc, list):
        return len(exc) > 0
    if isinstance(exc, dict):
        return bool(exc)
    return False


def applicable_questions(session: ReportSession) -> list[dict[str, Any]]:
    """Return the intake questions that apply for this session's data."""
    result: list[dict[str, Any]] = []
    for qid, q in QUESTION_DEFS.items():
        if q["always"]:
            result.append(q)
            continue
        if qid == "q22c" and not _dwda_found(session):
            result.append(q)
        elif qid == "q14" and _background_chloride_in_play(session):
            result.append(q)
        elif qid == "q6" and _has_impacts(session):
            result.append(q)
    return result


def auto_derived_summary(session: ReportSession) -> list[dict[str, Any]]:
    """Q0/Q1/Q22(b) values shown in the review step (not asked)."""
    facts = session.site_facts or {}
    summary = [
        {
            "id": "q0",
            "title": "Identity reconciliation",
            "value": {
                "site_lsd": facts.get("site_lsd"),
                "uwi": facts.get("uwi"),
                "client_name": facts.get("client_name"),
            },
        },
        {
            "id": "q1",
            "title": "Site type",
            "value": facts.get("site_type"),
        },
        {
            "id": "q22b",
            "title": "Sump / soil waste-mix zone found",
            "value": _dwda_found(session),
        },
    ]
    return summary


def validate_answers(answers: dict[str, Any], session: ReportSession) -> list[str]:
    """Validate submitted intake answers; returns a list of error messages."""
    errors: list[str] = []
    applicable = {q["id"] for q in applicable_questions(session)}
    for qid in applicable:
        value = answers.get(qid)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"{QUESTION_DEFS[qid]['title']} is required.")
    return errors