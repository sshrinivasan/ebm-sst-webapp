"""FastAPI surface for the SST app. Same contract as ebm-webapp so the shared
frontend works unchanged."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .context import Context, InputValidationError
from .loader import load
from .manifest import build_schema
from .params import defaults
from .pipeline import run as run_pipeline
from .percentile_95 import _build_borehole_sa_df
from .npp import seed_npp_options
from .tds import seed_tds_options
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
    # Seed the TDS background-sample multiselect option list so the TDS tab's
    # selector is populated immediately, before the first run.
    ctx = seed_tds_options(ctx)
    # Seed the SST Charts Plot Config tables (file-derived subareas) for the
    # Chloride, Sodium, and SAR subtabs so they are populated immediately,
    # before the first run.
    _plot_config_default = build_plot_config_default(ctx.frames["soil_data_filtered"])
    ctx.options["chloride_plot_config_default"] = _plot_config_default
    ctx.options["na_plot_config_default"] = _plot_config_default
    ctx.options["sar_plot_config_default"] = _plot_config_default
    # Seed the per-subarea borehole lists so the Chloride Plot Config table's
    # Excluded Boreholes multiselect is populated immediately, plus the flat
    # subarea list for the Subarea column's select.
    _sst_subarea_map = build_subarea_borehole_map(ctx.frames["soil_data_filtered"])
    ctx.options["sst_subarea_boreholes"] = _sst_subarea_map
    ctx.options["sst_subareas"] = sorted(_sst_subarea_map.keys())
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


# ---------------------------------------------------------------------------
# Static frontend (registered LAST so the /api/* routes above always win).
# The built React app is copied to /app/frontend/dist by the Dockerfile; this
# serves it from the same container/port as the API. In local dev the frontend
# runs on its own Vite server, so this block is a no-op there.
# ---------------------------------------------------------------------------
_FRONTEND_DIST = Path("/app/frontend/dist")
if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """SPA fallback: serve index.html for any non-/api path (client-side
        routing). /api routes are registered above and take precedence."""
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
