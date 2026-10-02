"""Operation JSON validation + ``apply_operations.py`` subprocess wrapper.

``apply_operations.py`` is a dumb executor with zero EBM wording logic; it
supports nine operation types. This module validates the operations array
produced by Step 3 and applies it to the partial DOCX in one pass (Step 4).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .session import ReportSession

_SKILL_ROOT = Path(__file__).resolve().parent.parent / "report_skill"
APPLY_SCRIPT = _SKILL_ROOT / "scripts" / "apply_operations.py"

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
            if not op.get("start_text") or not op.get("end_text"):
                errors.append(f"Operation {i}: replace_between needs start_text/end_text.")
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

    if proc.returncode != 0:
        raise OperationsError(
            f"apply_operations failed (exit {proc.returncode}):\n"
            f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )
    if not output_docx.exists():
        raise OperationsError("apply_operations did not produce the output DOCX.")
    session.final_docx = str(output_docx)
    return output_docx