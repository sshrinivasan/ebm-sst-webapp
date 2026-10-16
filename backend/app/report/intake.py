"""Intake question definitions + applicability logic (from intake_quiz.md).

Always-ask: Q21 (report type), Q22(a) (DWDA exploratory boreholes).
Conditional: Q22(b) (exploratory max depth, when exploratory boreholes
exist), Q22(c) (EM survey, only when no sump found), Q6 (impact volume).
The site-specific chloride threshold (Q14) is fixed at 100 mg/L and no
longer asked.
Auto-derived (shown in review, not asked): Q0 (identity reconciliation),
Q1 (site type), Q22(d) (sump found — from excel_data.json's dwda_data).
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
            "Add the exploratory boreholes advanced to locate the drilling "
            "waste disposal area and assign each to an APEC. Boreholes from "
            "the workbook's 'DWDA Search' row (case-insensitive) are used "
            "automatically when present."
        ),
        "type": "table",
        "columns": [
            {"key": "borehole_id", "label": "Borehole ID"},
            {"key": "apec", "label": "APEC"},
        ],
        "always": True,
    },
    "q22b": {
        "id": "q22b",
        "title": "DWDA exploratory borehole max depth",
        "prompt": (
            "What is the maximum depth (m) the DWDA exploratory boreholes "
            "were advanced to? (e.g. 6.0.)"
        ),
        "type": "text",
        "always": False,
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
AUTO_DERIVED_IDS = ["q0", "q1", "q22d"]


# ---------------------------------------------------------------------------
# Applicability logic
# ---------------------------------------------------------------------------


def _dwda_found(session: ReportSession) -> bool:
    """Q22(b): sump found iff excel_data.json's dwda_data is non-null."""
    dwda = session.excel_data.get("dwda_data")
    return dwda is not None and bool(dwda)


def _has_impacts(session: ReportSession) -> bool:
    """Q6: estimated volume of impact applies when exceedances exist."""
    data = session.excel_data
    exc = data.get("tier1_exceedances") or data.get("exceedances")
    if isinstance(exc, list):
        return len(exc) > 0
    if isinstance(exc, dict):
        return bool(exc)
    return False


def _has_exploratory_boreholes(session: ReportSession) -> bool:
    """Q22(b): max depth applies when exploratory boreholes were given (Q22a)."""
    value = (session.intake_answers or {}).get("q22a")
    if isinstance(value, list):
        return any(
            isinstance(row, dict) and str(row.get("borehole_id", "")).strip()
            for row in value
        )
    return bool(value and str(value).strip())


def applicable_questions(session: ReportSession) -> list[dict[str, Any]]:
    """Return the intake questions that apply for this session's data."""
    result: list[dict[str, Any]] = []
    for qid, q in QUESTION_DEFS.items():
        if q["always"]:
            result.append(q)
            continue
        if qid == "q22b" and _has_exploratory_boreholes(session):
            result.append(q)
        elif qid == "q22c" and not _dwda_found(session):
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
            "id": "q22d",
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
        elif isinstance(value, list) and not any(
            isinstance(row, dict) and str(row.get("borehole_id", "")).strip()
            for row in value
        ):
            errors.append(f"{QUESTION_DEFS[qid]['title']} is required.")
    return errors