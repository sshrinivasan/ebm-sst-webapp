"""Hands-off generation pipeline orchestrator (single background job).

Stages (mirrors the skill's Steps 2 → 3 → 4 → 6):
1. Regenerate the partial DOCX with intake answers (generator subprocess)
2. LLM section authoring (one call per Step 3 section prompt)
3. Apply all operations in one pass (apply_operations.py)
4. Practitioner information hand-off DOCX

The user never interacts mid-pipeline; ``progress`` callbacks report stage
messages to the job status store.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .extract import extract_site_facts
from .generator import run_generator
from .llm import LLMClient
from .operations import apply_operations
from .practitioner import write_practitioner_docx
from .sections import author_sections
from .session import ReportSession, SessionError

Progress = Callable[[str], None]


def _require(session: ReportSession, what: str) -> None:
    if not session.site_facts:
        raise SessionError(f"Cannot generate: {what} — run extraction first.")
    if session.excel_path() is None:
        raise SessionError("Cannot generate: no Excel file uploaded.")


def run_hands_off_pipeline(
    session: ReportSession,
    llm: LLMClient,
    *,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Run the full hands-off pipeline; returns a summary dict."""
    _require(session, "site facts missing")

    excel = session.excel_path()
    assert excel is not None
    figures_zip = session.figures_zip_path()
    site_facts_path = session.save_site_facts()
    output_dir = session.dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Stage 1: regenerate the partial DOCX with intake answers.
    if progress:
        progress("Regenerating report with intake answers…")
    run_generator(
        session,
        excel_path=excel,
        output_folder=output_dir,
        site_facts_path=site_facts_path,
        figures_zip_path=figures_zip,
    )

    # Stage 2: LLM section authoring.
    if progress:
        progress("Authoring sections…")
    author_sections(session, llm, progress=progress)

    # Stage 3: apply all operations in one pass.
    if progress:
        progress("Applying operations…")
    partial = Path(session.partial_docx or "")
    final = output_dir / "EBM_Report_Final.docx"
    apply_operations(session, input_docx=partial, output_docx=final)

    # Stage 4: practitioner information hand-off.
    if progress:
        progress("Building practitioner information…")
    write_practitioner_docx(session)

    session.state = "done"
    return {
        "session_id": session.id,
        "state": session.state,
        "final_docx": session.final_docx,
        "practitioner_docx": session.practitioner_docx,
        "operations_count": len(session.operations),
        "extraction_flags_count": len(session.extraction_flags),
    }


def run_extraction_job(
    session: ReportSession,
    llm: LLMClient,
    *,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Background extraction job (Step 1c)."""
    if progress:
        progress("Ingesting documents…")
    if progress:
        progress("Extracting site facts (this typically takes 2–5 minutes)…")
    extract_site_facts(session, llm)
    if progress:
        progress("Parsing results…")
    session.state = "facts_review"
    return {
        "session_id": session.id,
        "state": session.state,
        "site_facts": session.site_facts,
        "extraction_flags": session.extraction_flags,
    }


def run_prepare_job(
    session: ReportSession,
    *,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Background prepare job: run the generator to compute excel_data.json.

    Drives the conditional intake questions. Uses the confirmed site facts.
    """
    if progress:
        progress("Analyzing data…")
    excel = session.excel_path()
    if excel is None:
        raise SessionError("No Excel file uploaded.")
    site_facts_path = session.save_site_facts()
    output_dir = session.dir / "prepare"
    run_generator(
        session,
        excel_path=excel,
        output_folder=output_dir,
        site_facts_path=site_facts_path,
        figures_zip_path=session.figures_zip_path(),
    )
    session.state = "intake"
    return {
        "session_id": session.id,
        "state": session.state,
        "excel_data": session.excel_data,
    }