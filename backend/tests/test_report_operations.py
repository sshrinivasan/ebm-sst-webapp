"""Operation validation + apply wrapper tests."""
from pathlib import Path

import pytest

from app.report.operations import validate_operations
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