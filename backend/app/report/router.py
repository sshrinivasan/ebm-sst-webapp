"""FastAPI router exposing the /api/report/* endpoints.

Interactive phase (wizard): start → extract → confirm → prepare → intake.
Hands-off phase: generate (single background job) → status → download.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .extract import extract_site_facts
from .intake import applicable_questions, auto_derived_summary, validate_answers
from .jobs import runner
from .llm import LLMClient
from .pipeline import run_extraction_job, run_hands_off_pipeline, run_prepare_job
from .session import CATEGORIES, SessionError, store

router = APIRouter(prefix="/api/report", tags=["report"])

# One shared LLM client (reads OPENROUTER_API_KEY lazily on first call).
_llm = LLMClient()


def _session(session_id: str):
    try:
        return store.get(session_id)
    except SessionError as exc:
        raise HTTPException(404, str(exc))


# ---------------------------------------------------------------------------
# Interactive phase
# ---------------------------------------------------------------------------


@router.post("/start")
async def start(
    files: list[UploadFile] = File(...),
    categories: list[str] = Form(...),
    reuse_analysis_token: str | None = Form(None),
) -> dict[str, Any]:
    """Create a session and store the uploaded files by category.

    Each file must have a matching category in the parallel ``categories``
    form field (same order). Optionally ``reuse_analysis_token`` reuses the
    current analysis export instead of uploading Excel/figures.
    """
    if len(files) != len(categories):
        raise HTTPException(400, "Each file needs a category (same order).")
    for cat in categories:
        if cat not in CATEGORIES:
            raise HTTPException(400, f"Unknown category: {cat}")

    session = store.create()
    for file, cat in zip(files, categories):
        if not file.filename:
            continue
        dest = session.dir / cat / file.filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await file.read())
        session.add_file(cat, file.filename, dest)

    if reuse_analysis_token:
        # Reuse the analysis export: copy the uploaded Excel + figures zip
        # from the analysis upload dir into the session (best-effort).
        from ..main import _path_for  # local import to avoid a cycle

        try:
            src = _path_for(reuse_analysis_token)
            dest = session.dir / "excel" / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            session.add_file("excel", src.name, dest)
        except HTTPException:
            pass  # token expired; user can upload manually

    if session.excel_path() is None:
        raise HTTPException(400, "An Excel file (or reuse_analysis_token) is required.")

    session.state = "files"
    return session.to_public()


@router.post("/extract")
def extract(session_id: str) -> dict[str, Any]:
    """Start the LLM site-facts extraction as a background job."""
    session = _session(session_id)
    if not session.extract_sources():
        raise HTTPException(400, "No source documents uploaded for extraction.")
    session.state = "extracting"
    job = runner.submit(
        run_extraction_job,
        session,
        _llm,
        stage_messages=[
            "Ingesting documents…",
            "Extracting site facts (this typically takes 2–5 minutes)…",
            "Parsing results…",
        ],
    )
    return {"job_id": job.id, "session": session.to_public()}


class ConfirmExtractRequest(BaseModel):
    site_facts: dict[str, Any]
    extraction_flags: list[dict[str, Any]] = []


@router.post("/extract/confirm")
def confirm_extract(session_id: str, req: ConfirmExtractRequest) -> dict[str, Any]:
    """Accept the (possibly edited) site_facts.json from the review form."""
    session = _session(session_id)
    session.site_facts = req.site_facts
    session.extraction_flags = req.extraction_flags
    session.save_site_facts()
    session.state = "facts_review"
    return session.to_public()


@router.post("/prepare")
def prepare(session_id: str) -> dict[str, Any]:
    """Run the generator in the background to compute excel_data.json."""
    session = _session(session_id)
    if not session.site_facts:
        raise HTTPException(400, "Confirm site facts before preparing intake.")
    session.state = "preparing"
    job = runner.submit(
        run_prepare_job,
        session,
        stage_messages=["Analyzing data…"],
    )
    return {"job_id": job.id, "session": session.to_public()}


@router.get("/intake")
def intake(session_id: str) -> dict[str, Any]:
    """Applicable intake questions (computed from excel_data + site_facts)."""
    session = _session(session_id)
    return {
        "questions": applicable_questions(session),
        "auto_derived": auto_derived_summary(session),
        "answers": session.intake_answers,
    }


class IntakeRequest(BaseModel):
    answers: dict[str, Any]


@router.post("/intake")
def submit_intake(session_id: str, req: IntakeRequest) -> dict[str, Any]:
    """Submit intake answers; re-runs prepare if answers changed."""
    session = _session(session_id)
    errors = validate_answers(req.answers, session)
    if errors:
        raise HTTPException(400, {"errors": errors})
    session.intake_answers = req.answers
    session.state = "intake"
    return session.to_public()


# ---------------------------------------------------------------------------
# Hands-off phase
# ---------------------------------------------------------------------------


@router.post("/generate")
def generate(session_id: str) -> dict[str, Any]:
    """Start the hands-off generation pipeline as a single background job."""
    session = _session(session_id)
    if not session.intake_answers:
        raise HTTPException(400, "Submit intake answers before generating.")
    session.state = "generating"
    job = runner.submit(
        run_hands_off_pipeline,
        session,
        _llm,
        stage_messages=[
            "Regenerating report with intake answers…",
            "Authoring sections…",
            "Applying operations…",
            "Building practitioner information…",
        ],
    )
    return {"job_id": job.id, "session": session.to_public()}


@router.get("/status/{job_id}")
def status(job_id: str) -> dict[str, Any]:
    """Poll job progress (stages for the hands-off pipeline)."""
    try:
        job = runner.get(job_id)
    except SessionError as exc:
        raise HTTPException(404, str(exc))
    return job.to_public()


@router.get("/download/{session_id}")
def download(session_id: str, kind: str = "report") -> FileResponse:
    """Download the final report or practitioner DOCX."""
    session = _session(session_id)
    if kind == "practitioner":
        path = session.practitioner_docx
    else:
        path = session.final_docx
    if not path or not Path(path).exists():
        raise HTTPException(404, "No generated document available yet.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=Path(path).name,
    )


@router.get("/session/{session_id}")
def session_view(session_id: str) -> dict[str, Any]:
    """Current session state (for wizard resume/refresh)."""
    return _session(session_id).to_public()