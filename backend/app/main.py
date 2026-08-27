"""FastAPI surface for the SST app. Same contract as ebm-webapp so the shared
frontend works unchanged."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .context import Context, InputValidationError
from .loader import load
from .manifest import build_schema
from .params import defaults
from .pipeline import run as run_pipeline

app = FastAPI(title="EBM SST")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_UPLOAD_DIR = Path(tempfile.gettempdir()) / "ebm_sst_uploads"
_UPLOAD_DIR.mkdir(exist_ok=True)


def _path_for(token: str) -> Path:
    p = _UPLOAD_DIR / f"{token}.xlsm"
    if not p.exists():
        raise HTTPException(404, "Unknown or expired file token; please re-upload.")
    return p


@app.get("/api/schema")
def schema() -> dict:
    return build_schema()


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith((".xlsm", ".xlsx")):
        raise HTTPException(400, "Please upload an .xlsm soil analytical table.")
    token = uuid.uuid4().hex
    dest = _UPLOAD_DIR / f"{token}.xlsm"
    dest.write_bytes(await file.read())
    # Load-only: populate file-derived option lists for the UI selectors. The
    # full analysis runs on the frontend's first "Run analysis" call.
    ctx = load(Context(str(dest), params=defaults()))
    return {"token": token, "filename": file.filename, "options": ctx.options}


class RunRequest(BaseModel):
    token: str
    params: dict = {}


@app.post("/api/run")
def run(req: RunRequest) -> dict:
    path = _path_for(req.token)
    try:
        ctx = run_pipeline(str(path), req.params)
    except InputValidationError as exc:
        raise HTTPException(400, str(exc))
    return {"outputs": ctx.outputs, "charts": ctx.charts, "options": ctx.options,
            "messages": ctx.messages, "errors": []}
