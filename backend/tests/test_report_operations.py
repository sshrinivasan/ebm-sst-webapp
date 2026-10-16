"""Operation validation + apply/assemble wrapper tests."""
import json
import subprocess
from pathlib import Path

import pytest

from app.report.operations import (
    OperationsError,
    assemble_operations,
    normalize_marker_fields,
    validate_operations,
)
from app.report.session import ReportSession


def test_valid_replace_between():
    ops = [{"op": "replace_between", "start_text": "<INSERT_1_START>", "end_text": "<INSERT_1_END>", "blocks": [{"style": "body", "text": "hi"}]}]
    assert validate_operations(ops) == []


def test_missing_blocks():
    ops = [{"op": "replace_between", "start_text": "a", "end_text": "b"}]
    errors = validate_operations(ops)
    assert any("blocks" in e for e in errors)


def test_unknown_op():
    ops = [{"op": "explode", "x": 1}]
    errors = validate_operations(ops)
    assert any("unknown op" in e for e in errors)


def test_replace_text_needs_find_replace():
    ops = [{"op": "replace_text", "find": "a"}]
    errors = validate_operations(ops)
    assert any("find + replace" in e for e in errors)


def test_insert_blocks_needs_placeholder():
    ops = [{"op": "insert_blocks", "blocks": []}]
    errors = validate_operations(ops)
    assert any("placeholder" in e for e in errors)


def test_empty_operations_valid():
    assert validate_operations([]) == []


def test_non_object_operation():
    ops = ["not-an-op"]
    errors = validate_operations(ops)
    assert any("not an object" in e for e in errors)


def test_assemble_style_ops_pass_validation():
    """Ops in the assemble_operations.py convention (start_placeholder/
    end_placeholder) validate without needing start_text/end_text."""
    ops = [
        {"op": "replace_between", "start_placeholder": "<INSERT_EXEC_SUMMARY_START>",
         "end_placeholder": "<INSERT_EXEC_SUMMARY_END>", "blocks": [{"style": "body", "text": "x"}]},
    ]
    assert validate_operations(ops) == []
    normalize_marker_fields(ops)
    assert ops[0]["start_text"] == "<INSERT_EXEC_SUMMARY_START>"
    assert ops[0]["end_text"] == "<INSERT_EXEC_SUMMARY_END>"
    assert ops[0]["start_placeholder"] == "<INSERT_EXEC_SUMMARY_START>"
    assert validate_operations(ops) == []


def test_assemble_operations_requires_authored(tmp_path):
    s = ReportSession(id="t", dir=tmp_path / "s")
    s.dir.mkdir(parents=True, exist_ok=True)
    partial = s.dir / "partial.docx"
    partial.write_bytes(b"docx")
    with pytest.raises(OperationsError):
        assemble_operations(s, input_docx=partial)


def test_assemble_operations_runs_script(tmp_path, monkeypatch):
    s = ReportSession(id="t", dir=tmp_path / "s")
    s.dir.mkdir(parents=True, exist_ok=True)
    s.authored = {"exec_summary": [{"style": "body", "text": "x"}]}
    s.excel_data = {"section5_present": False}
    s.excel_data_path = str(s.dir / "excel_data.json")
    (s.dir / "excel_data.json").write_text('{"section5_present": false}')
    partial = s.dir / "partial.docx"
    partial.write_bytes(b"docx")

    # Both marker field-name conventions, so normalize_marker_fields is a no-op.
    ops = [{"op": "replace_between", "start_placeholder": "S", "end_placeholder": "E",
            "start_text": "S", "end_text": "E", "blocks": []}]
    pi = {"site": "x", "report": "x", "check": [], "uncertain": [], "not_found": [], "incomplete": []}

    class FakeProc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        # Emulate the script's outputs.
        (s.dir / "operations.json").write_text(json.dumps(ops))
        (s.dir / "practitioner_info.json").write_text(json.dumps(pi))
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = assemble_operations(s, input_docx=partial)
    assert result == ops
    assert s.operations == ops
    assert s.practitioner_info == pi
    assert (s.dir / "authored.json").exists()