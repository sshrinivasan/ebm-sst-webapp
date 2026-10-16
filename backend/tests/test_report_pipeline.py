"""Hands-off pipeline orchestrator tests (subprocess steps mocked)."""
from pathlib import Path

import pytest

from app.report import pipeline as pipeline_mod
from app.report.session import ReportSession, SessionError


class FakeLLM:
    def complete_json(self, system, user, **kwargs):
        # Single consolidated call -> authored.json (Section 5 absent here, so
        # the s5_* keys are null).
        return {
            "exec_summary": [{"style": "body", "text": "x"}],
            "s4_3_chloride": [{"style": "body", "text": "x"}],
            "s5_1_phase1": None,
            "s5_2_transport": None,
            "s5_3_footprint": None,
            "s8_summary": [{"style": "body", "text": "x"}],
            "practitioner_information": {
                "site": "x", "report": "x",
                "check": [], "uncertain": [], "not_found": [], "incomplete": [],
            },
        }


def _ready_session(tmp_path: Path) -> ReportSession:
    s = ReportSession(id="t", dir=tmp_path / "s")
    s.dir.mkdir(parents=True, exist_ok=True)
    excel = s.dir / "excel" / "soil.xlsm"
    excel.parent.mkdir(parents=True, exist_ok=True)
    excel.write_bytes(b"xlsm")
    s.add_file("excel", "soil.xlsm", excel)
    s.site_facts = {"site_lsd": "08-13-016-01 W4", "client_name": "Canlin"}
    s.intake_answers = {"q21": "Standard Tier 1 P1", "q22a": "BH26-01"}
    return s


def test_pipeline_requires_site_facts(tmp_path: Path):
    s = ReportSession(id="t", dir=tmp_path / "s")
    with pytest.raises(SessionError):
        pipeline_mod.run_hands_off_pipeline(s, FakeLLM())


def test_pipeline_requires_excel(tmp_path: Path):
    s = ReportSession(id="t", dir=tmp_path / "s")
    s.site_facts = {"site_lsd": "x"}
    with pytest.raises(SessionError):
        pipeline_mod.run_hands_off_pipeline(s, FakeLLM())


def test_pipeline_runs_all_stages(tmp_path: Path, monkeypatch):
    s = _ready_session(tmp_path)
    stages: list[str] = []

    def fake_generator(session, **kwargs):
        session.partial_docx = str(session.dir / "output" / "partial.docx")
        Path(session.partial_docx).parent.mkdir(parents=True, exist_ok=True)
        Path(session.partial_docx).write_bytes(b"docx")
        session.save_excel_data({"dwda_data": None, "tier1_exceedances": []})
        return session.excel_data

    def fake_assemble(session, **kwargs):
        session.operations = [
            {"op": "replace_between", "start_placeholder": "<INSERT_EXEC_SUMMARY_START>",
             "end_placeholder": "<INSERT_EXEC_SUMMARY_END>", "blocks": [{"style": "body", "text": "x"}]},
        ]
        session.practitioner_info = {
            "site": "x", "report": "x",
            "check": [], "uncertain": [], "not_found": [], "incomplete": [],
        }
        return session.operations

    def fake_apply(session, **kwargs):
        session.final_docx = str(session.dir / "output" / "final.docx")
        Path(session.final_docx).write_bytes(b"docx")
        return Path(session.final_docx)

    def fake_practitioner(session, **kwargs):
        session.practitioner_docx = str(session.dir / "Practitioner_Information_x.docx")
        Path(session.practitioner_docx).write_bytes(b"docx")
        return Path(session.practitioner_docx)

    monkeypatch.setattr(pipeline_mod, "run_generator", fake_generator)
    monkeypatch.setattr(pipeline_mod, "assemble_operations", fake_assemble)
    monkeypatch.setattr(pipeline_mod, "apply_operations", fake_apply)
    monkeypatch.setattr(pipeline_mod, "write_practitioner_docx", fake_practitioner)

    result = pipeline_mod.run_hands_off_pipeline(
        s, FakeLLM(), progress=lambda msg: stages.append(msg)
    )

    assert result["state"] == "done"
    assert s.state == "done"
    assert s.final_docx is not None
    assert s.practitioner_docx is not None
    assert len(s.operations) == 1
    assert s.authored["exec_summary"] == [{"style": "body", "text": "x"}]
    assert stages[0].startswith("Regenerating")
    assert any("Authoring all report sections" in m for m in stages)
    assert any("Assembling operations" in m for m in stages)


def test_prepare_job(tmp_path: Path, monkeypatch):
    s = _ready_session(tmp_path)

    def fake_generator(session, **kwargs):
        session.save_excel_data({"dwda_data": None})
        return session.excel_data

    monkeypatch.setattr(pipeline_mod, "run_generator", fake_generator)
    result = pipeline_mod.run_prepare_job(s)
    assert result["state"] == "intake"
    assert s.excel_data == {"dwda_data": None}