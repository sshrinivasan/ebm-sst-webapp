"""Subprocess wrapper for ``generate_ebm_report.py`` (skill Step 2).

The generator is a standalone script with 7 positional args:

    references_folder excel output_folder site_lsd client_name site_facts.json figures_zip

It reads the Excel mechanically (openpyxl), writes ``excel_data.json`` into the
output folder, and produces the partial DOCX with template placeholders. The
LLM is never involved here.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .session import ReportSession

# Vendored skill root (sibling of this package: backend/report_skill/).
_SKILL_ROOT = Path(__file__).resolve().parent.parent / "report_skill"
GENERATOR_SCRIPT = _SKILL_ROOT / "scripts" / "generate_ebm_report.py"
REFERENCES_FOLDER = _SKILL_ROOT / "references"


class GeneratorError(RuntimeError):
    """Raised when the generator subprocess fails."""


def _reconciled(site_facts: dict[str, Any], key: str) -> str | None:
    """Pull a reconciled top-level value (site_lsd/client_name/uwi) if present."""
    value = site_facts.get(key)
    return str(value) if value else None


def run_generator(
    session: ReportSession,
    *,
    excel_path: Path,
    output_folder: Path,
    site_facts_path: Path,
    figures_zip_path: Path | None = None,
    site_lsd: str | None = None,
    client_name: str | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    """Run the generator subprocess; returns the parsed ``excel_data.json``.

    ``site_lsd``/``client_name`` default to the reconciled values in
    ``site_facts.json`` (per the skill, they are derived in Step 1c, never
    typed by the user).
    """
    if not GENERATOR_SCRIPT.exists():
        raise GeneratorError(f"Generator script not found: {GENERATOR_SCRIPT}")
    if not REFERENCES_FOLDER.exists():
        raise GeneratorError(f"References folder not found: {REFERENCES_FOLDER}")

    output_folder.mkdir(parents=True, exist_ok=True)

    site_facts = session.site_facts or {}
    site_lsd = site_lsd or _reconciled(site_facts, "site_lsd")
    client_name = client_name or _reconciled(site_facts, "client_name")

    cmd = [
        sys.executable,
        str(GENERATOR_SCRIPT),
        str(REFERENCES_FOLDER),
        str(excel_path),
        str(output_folder),
    ]
    if site_lsd:
        cmd.append(site_lsd)
    if client_name:
        cmd.append(client_name)
    cmd.append(str(site_facts_path))
    if figures_zip_path is not None:
        cmd.append(str(figures_zip_path))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_SKILL_ROOT),
        )
    except subprocess.TimeoutExpired as exc:
        raise GeneratorError(f"Generator timed out after {timeout}s.") from exc

    if proc.returncode != 0:
        raise GeneratorError(
            f"Generator failed (exit {proc.returncode}):\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )

    # The generator prints the partial DOCX path; capture it from stdout.
    session.partial_docx = _find_docx_in_output(output_folder)

    excel_data_path = output_folder / "excel_data.json"
    if not excel_data_path.exists():
        raise GeneratorError(
            f"Generator did not produce excel_data.json in {output_folder}:\n{proc.stdout[-2000:]}"
        )
    excel_data = json.loads(excel_data_path.read_text(encoding="utf-8"))
    session.save_excel_data(excel_data)
    return excel_data


def _find_docx_in_output(output_folder: Path) -> str | None:
    """Return the newest .docx in the output folder (the partial report)."""
    docx_files = sorted(output_folder.glob("*.docx"), key=lambda p: p.stat().st_mtime)
    return str(docx_files[-1]) if docx_files else None