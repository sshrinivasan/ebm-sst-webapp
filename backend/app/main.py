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
from .percentile_95 import _build_borehole_sa_df
from .npp import seed_npp_options
from .sst_charts import build_plot_config_default, build_subarea_borehole_map

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
def schema(sst_flag: bool = True) -> dict:
    """Presentation schema. When ``sst_flag`` is false, the SST tabs/outputs/
    charts/params are filtered out so the frontend hides them."""
    return build_schema(sst_flag=sst_flag)


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
    # Seed the 95th Percentile subarea assigner with the file-derived default
    # mapping (computed here so it's available before the first run).
    borehole_sa_df = _build_borehole_sa_df(ctx.frames["soil_data_filtered"])
    ctx.options["borehole_sa_df"] = {
        "columns": list(borehole_sa_df.columns),
        "rows": borehole_sa_df.to_dict(orient="records"),
    }
    # Seed the NPP background / near-APEC multiselect option lists so the NPP
    # tab's selectors are populated immediately, before the first run.
    ctx = seed_npp_options(ctx)
    # Seed the SST Charts Chloride Plot Config table (file-derived subareas)
    # so the table is populated immediately, before the first run.
    ctx.options["chloride_plot_config_default"] = build_plot_config_default(
        ctx.frames["soil_data_filtered"]
    )
    # Seed the per-subarea borehole lists so the Chloride Plot Config table's
    # Excluded Boreholes multiselect is populated immediately.
    ctx.options["sst_subarea_boreholes"] = build_subarea_borehole_map(
        ctx.frames["soil_data_filtered"]
    )
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
