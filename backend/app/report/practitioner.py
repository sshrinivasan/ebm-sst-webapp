"""Step 6 — practitioner information hand-off DOCX.

The practitioner content is authored by the LLM in the Step 3 one-call pass
(``authored.json`` → ``practitioner_information``) and written to
``practitioner_info.json`` by ``assemble_operations.py``. This module just
runs ``write_practitioner_info.py`` to produce
``Practitioner_Information_<site>.docx``; leftover placeholders in the final
DOCX are auto-scanned by the script (Python, not Claude).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .session import ReportSession

_SKILL_ROOT = Path(__file__).resolve().parents[2] / "report_skill"
WRITER_SCRIPT = _SKILL_ROOT / "scripts" / "write_practitioner_info.py"


class PractitionerError(RuntimeError):
    """Raised when the practitioner hand-off cannot be built."""


def write_practitioner_docx(
    session: ReportSession,
    *,
    timeout: int = 120,
) -> Path:
    """Build and save the practitioner hand-off DOCX (Step 6).

    Requires ``session.practitioner_info`` (populated by
    ``assemble_operations`` from the authored ``practitioner_information``).
    """
    if not WRITER_SCRIPT.exists():
        raise PractitionerError(f"write_practitioner_info.py not found: {WRITER_SCRIPT}")
    if not session.practitioner_info:
        raise PractitionerError(
            "No practitioner info available — run assemble_operations first."
        )

    info_path = session.save_practitioner_info()

    cmd = [
        sys.executable,
        str(WRITER_SCRIPT),
        str(info_path),
        str(session.dir),
    ]
    if session.final_docx:
        cmd.append(session.final_docx)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_SKILL_ROOT),
        )
    except subprocess.TimeoutExpired as exc:
        raise PractitionerError(f"Practitioner writer timed out after {timeout}s.") from exc

    if proc.returncode != 0:
        raise PractitionerError(
            f"Practitioner writer failed (exit {proc.returncode}):\n{proc.stderr[-2000:]}"
        )

    # Locate the produced DOCX (named Practitioner_Information_<site>.docx).
    matches = sorted(session.dir.glob("Practitioner_Information_*.docx"))
    if not matches:
        raise PractitionerError("Practitioner writer did not produce a DOCX.")
    session.practitioner_docx = str(matches[-1])
    return matches[-1]