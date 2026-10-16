"""Operation JSON validation + ``apply_operations.py`` subprocess wrapper.

``apply_operations.py`` is a dumb executor with zero EBM wording logic; it
supports nine operation types. This module validates the operations array
produced by Step 3 and applies it to the partial DOCX in one pass (Step 4).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .session import ReportSession

_SKILL_ROOT = Path(__file__).resolve().parents[2] / "report_skill"
APPLY_SCRIPT = _SKILL_ROOT / "scripts" / "apply_operations.py"
ASSEMBLE_SCRIPT = _SKILL_ROOT / "scripts" / "assemble_operations.py"

# Operation types supported by apply_operations.py.
KNOWN_OPS = {
    "replace_table_cells",
    "insert_blocks",
    "replace_text",
    "delete_table",
    "replace_between",
    "strip_markers",
    "replace_table_rows",
    "delete_paragraph",
    "set_table_cells_by_position",
}


class OperationsError(RuntimeError):
    """Raised when operations are invalid or the apply step fails."""


def _marker_fields(op: dict[str, Any]) -> tuple[str, str]:
    """Resolve a replace_between op's start/end markers across both field-name
    conventions: ``start_placeholder``/``end_placeholder`` (what
    ``assemble_operations.py`` and ``apply_operations.py`` use) and
    ``start_text``/``end_text`` (the older convention)."""
    return (
        str(op.get("start_placeholder") or op.get("start_text") or ""),
        str(op.get("end_placeholder") or op.get("end_text") or ""),
    )


def normalize_marker_fields(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill both marker field-name conventions on every replace_between op.

    ``assemble_operations.py`` emits ``start_placeholder``/``end_placeholder``;
    ``apply_operations.py`` reads those, while ``validate_operations`` accepts
    either. Filling both keeps every consumer working regardless of which
    convention a producer used.
    """
    for op in operations:
        if not isinstance(op, dict) or op.get("op") != "replace_between":
            continue
        start, end = _marker_fields(op)
        if not op.get("start_placeholder"):
            op["start_placeholder"] = start
        if not op.get("end_placeholder"):
            op["end_placeholder"] = end
        if not op.get("start_text"):
            op["start_text"] = start
        if not op.get("end_text"):
            op["end_text"] = end
    return operations


def validate_operations(operations: list[dict[str, Any]]) -> list[str]:
    """Return a list of validation errors (empty when valid)."""
    errors: list[str] = []
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            errors.append(f"Operation {i} is not an object.")
            continue
        op_type = op.get("op")
        if op_type not in KNOWN_OPS:
            errors.append(f"Operation {i}: unknown op '{op_type}'.")
        if op_type == "replace_between":
            start, end = _marker_fields(op)
            if not start or not end:
                errors.append(
                    f"Operation {i}: replace_between needs start/end markers "
                    "(start_placeholder/end_placeholder or start_text/end_text)."
                )
            if "blocks" not in op:
                errors.append(f"Operation {i}: replace_between needs a blocks list.")
        elif op_type == "insert_blocks":
            if not op.get("placeholder") or "blocks" not in op:
                errors.append(f"Operation {i}: insert_blocks needs placeholder + blocks.")
        elif op_type == "replace_text":
            if "find" not in op or "replace" not in op:
                errors.append(f"Operation {i}: replace_text needs find + replace.")
    return errors


def apply_operations(
    session: ReportSession,
    *,
    input_docx: Path,
    output_docx: Path,
    timeout: int = 300,
) -> Path:
    """Apply the session's operations to ``input_docx`` in one pass (Step 4)."""
    if not APPLY_SCRIPT.exists():
        raise OperationsError(f"apply_operations.py not found: {APPLY_SCRIPT}")
    if not input_docx.exists():
        raise OperationsError(f"Input DOCX not found: {input_docx}")

    errors = validate_operations(session.operations)
    if errors:
        raise OperationsError("Invalid operations:\n" + "\n".join(errors))

    operations_path = session.save_operations()
    output_docx.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(APPLY_SCRIPT),
        str(input_docx),
        str(operations_path),
        str(output_docx),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_SKILL_ROOT),
        )
    except subprocess.TimeoutExpired as exc:
        raise OperationsError(f"apply_operations timed out after {timeout}s.") from exc

    if not output_docx.exists():
        raise OperationsError(
            f"apply_operations did not produce the output DOCX (exit {proc.returncode}):\n"
            f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )

    # apply_operations.py exits 1 when placeholders remain unfilled (e.g.
    # Python-authored sections or the DWDA variant when DWDA-NIL applies), but
    # it still saves the DOCX. Treat that as a warning, not a hard failure —
    # the practitioner hand-off records the unfilled placeholders.
    if proc.returncode != 0:
        session.messages.append({
            "level": "warning",
            "workflow": "report",
            "message": "Some report placeholders were left unfilled (see practitioner info).",
        })
    session.final_docx = str(output_docx)
    return output_docx


def assemble_operations(
    session: ReportSession,
    *,
    input_docx: Path,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    """Run ``assemble_operations.py``: authored.json → operations + practitioner info.

    Reads the session's ``authored.json`` (Step 3 one-call output) and the
    partial DOCX, validates the authored content (including the Section 5
    gate), and writes ``operations.json`` plus ``practitioner_info.json`` into
    the session dir. Both are loaded back onto the session.
    """
    if not ASSEMBLE_SCRIPT.exists():
        raise OperationsError(f"assemble_operations.py not found: {ASSEMBLE_SCRIPT}")
    if not input_docx.exists():
        raise OperationsError(f"Input DOCX not found: {input_docx}")
    if not session.authored:
        raise OperationsError("No authored.json to assemble — run authoring first.")

    authored_path = session.save_authored()
    excel_data_path = session.excel_data_path or str(session.dir / "excel_data.json")
    operations_path = session.dir / "operations.json"

    cmd = [
        sys.executable,
        str(ASSEMBLE_SCRIPT),
        str(authored_path),
        str(input_docx),
        str(excel_data_path),
        str(operations_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_SKILL_ROOT),
        )
    except subprocess.TimeoutExpired as exc:
        raise OperationsError(f"assemble_operations timed out after {timeout}s.") from exc

    if proc.returncode != 0:
        raise OperationsError(
            f"assemble_operations failed (exit {proc.returncode}):\n"
            f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )

    session.operations = normalize_marker_fields(
        json.loads(operations_path.read_text(encoding="utf-8"))
    )
    pi_path = session.dir / "practitioner_info.json"
    if pi_path.exists():
        session.practitioner_info = json.loads(pi_path.read_text(encoding="utf-8"))
    return session.operations