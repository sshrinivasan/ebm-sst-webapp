"""Intake applicability logic tests."""
from pathlib import Path

import pytest

from app.report.intake import (
    applicable_questions,
    auto_derived_summary,
    validate_answers,
)
from app.report.session import ReportSession


def _session(excel_data=None, site_facts=None) -> ReportSession:
    s = ReportSession(id="t", dir=Path("/tmp/t"))
    s.excel_data = excel_data or {}
    s.site_facts = site_facts or {}
    return s


def test_always_questions_present():
    s = _session()
    qs = applicable_questions(s)
    ids = {q["id"] for q in qs}
    assert "q21" in ids
    assert "q22a" in ids


def test_q22b_when_exploratory_boreholes_given():
    s = _session()
    s.intake_answers = {"q22a": "BH26-01 to BH26-04"}
    ids = {q["id"] for q in applicable_questions(s)}
    assert "q22b" in ids


def test_q22b_when_exploratory_boreholes_table_given():
    s = _session()
    s.intake_answers = {"q22a": [{"borehole_id": "BH26-01", "apec": "DWDA"}]}
    ids = {q["id"] for q in applicable_questions(s)}
    assert "q22b" in ids


def test_q22b_absent_when_table_has_no_borehole_ids():
    s = _session()
    s.intake_answers = {"q22a": [{"borehole_id": "", "apec": ""}]}
    ids = {q["id"] for q in applicable_questions(s)}
    assert "q22b" not in ids


def test_q22b_absent_without_exploratory_boreholes():
    s = _session()
    ids = {q["id"] for q in applicable_questions(s)}
    assert "q22b" not in ids


def test_q22c_when_no_sump_found():
    s = _session(excel_data={"dwda_data": None})
    ids = {q["id"] for q in applicable_questions(s)}
    assert "q22c" in ids


def test_q22c_absent_when_sump_found():
    s = _session(excel_data={"dwda_data": {"boreholes": ["BH26-01"]}})
    ids = {q["id"] for q in applicable_questions(s)}
    assert "q22c" not in ids


def test_q14_never_asked():
    # The chloride threshold is fixed at 100 mg/L — Q14 is never asked.
    s = _session(excel_data={"chloride_delineation_data": {"outcome": "NOT_ACHIEVED_BACKGROUND"}})
    ids = {q["id"] for q in applicable_questions(s)}
    assert "q14" not in ids


def test_q6_when_exceedances_exist():
    s = _session(excel_data={"tier1_exceedances": [{"parameter": "Chloride"}]})
    ids = {q["id"] for q in applicable_questions(s)}
    assert "q6" in ids


def test_q6_absent_without_exceedances():
    s = _session(excel_data={"tier1_exceedances": []})
    ids = {q["id"] for q in applicable_questions(s)}
    assert "q6" not in ids


def test_auto_derived_summary():
    s = _session(
        site_facts={"site_lsd": "08-13-016-01 W4", "site_type": "wellsite"},
        excel_data={"dwda_data": None},
    )
    summary = auto_derived_summary(s)
    by_id = {a["id"]: a for a in summary}
    assert by_id["q0"]["value"]["site_lsd"] == "08-13-016-01 W4"
    assert by_id["q1"]["value"] == "wellsite"
    assert by_id["q22d"]["value"] is False


def test_validate_answers_requires_applicable():
    s = _session()
    errors = validate_answers({}, s)
    assert any("Report type" in e for e in errors)
    assert any("DWDA exploratory boreholes" in e for e in errors)


def test_validate_answers_passes_when_filled():
    s = _session()
    # Empty session -> no sump found -> q22c (EM survey) also applies.
    answers = {
        "q21": "Standard Tier 1 P1",
        "q22a": [{"borehole_id": "BH26-01", "apec": "DWDA"}],
        "q22c": "No survey was conducted",
    }
    assert validate_answers(answers, s) == []


def test_validate_answers_rejects_empty_table():
    s = _session()
    answers = {
        "q21": "Standard Tier 1 P1",
        "q22a": [{"borehole_id": "", "apec": ""}],
        "q22c": "No survey was conducted",
    }
    errors = validate_answers(answers, s)
    assert any("DWDA exploratory boreholes" in e for e in errors)