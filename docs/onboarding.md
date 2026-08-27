# EBM SST Webapp — Onboarding & Workflow Guide

> **Purpose:** A self-contained orientation for any future session (or contributor)
> working on `ebm-sst-webapp`. Read this first to pick up the architecture, the
> "add a workflow" pattern, and the key files — without re-deriving it from scratch.

---

## 1. What this app is

A lightweight webapp that runs **soil / SST (site-specific) analytical workflows**
in Python and displays the results as **tables** and **charts** in a schema-driven
React frontend.

- **Backend:** FastAPI + pandas + matplotlib (Python 3.13, venv at `ebm-sst-env/`).
- **Frontend:** React + Vite + TypeScript, fully **schema-driven** — it renders
  whatever the backend's `/api/schema` describes. No frontend changes are needed
  for standard tables/charts.
- **Input:** an `.xlsm` soil analytical table (see `backend/2026_filled_full.xlsm`
  and `backend/2026_small_npp.xlsm` for samples).

The user's main work is **Python** — adding new analysis workflows that produce
tables or charts.

---

## 2. Directory layout (the parts that matter)

```
ebm-sst-webapp/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI surface: /api/schema, /api/upload, /api/run
│   │   ├── manifest.py            # SCHEMA CONTRACT: NAV tabs, OUTPUTS tables, CHARTS figures
│   │   ├── params.py              # hand-authored input params (schema-driven, with defaults)
│   │   ├── pipeline.py            # orchestrator: run(excel_path, params) -> Context
│   │   ├── context.py             # Context dataclass (frames/options/outputs/charts/exports/messages)
│   │   ├── loader.py              # load + clean the .xlsm soil table (trunk prep)
│   │   ├── ec_sar_rating.py       # workflow: EC/SAR rating
│   │   ├── background_guidelines.py # workflow: SCARG guidelines
│   │   ├── borehole_stats.py      # workflow: borehole characteristics
│   │   ├── tier1_exceedances.py   # workflow: Tier-1 exceedances
│   │   ├── sst_exceedances.py     # workflow: site-specific (SST) exceedances
│   │   ├── tier1_charts.py        # workflow: Tier-1 profile + variable charts
│   │   └── bg_chloride.py         # workflow: BG chloride scatter plots
│   ├── tests/                    # pytest + golden-CSV regression fixtures
│   ├── requirements.txt
│   └── dev.py
├── frontend/
│   └── src/
│       ├── App.tsx               # renders nav/tabs/inputs/outputs/charts generically
│       ├── api.ts                # getSchema / uploadFile / runWorkflow
│       ├── types.ts              # Schema, RunResult, InputSpec, ...
│       └── components/           # DataTable, Field, MultiSelect, TableInput, icons
└── docs/
    ├── onboarding.md             # THIS FILE
    └── parallel-workflows-plan.md # future design: trunk + branches, parallelism
```

---

## 3. The data flow (end to end)

1. **Frontend** calls `GET /api/schema` → gets `{nav, tabs, inputs, outputs, charts}`.
2. User uploads an `.xlsm` → `POST /api/upload` → backend stores it by a `token`
   and returns `{token, filename, options}` (file-derived option lists for the UI).
3. Frontend calls `POST /api/run` with `{token, params}` → backend runs the full
   pipeline → returns `{outputs, charts, options, messages, errors}`.
4. Frontend renders tables (`outputs`) and chart images (`charts`) on the tab the
   schema says they belong to.

### The `Context` object ([`context.py`](backend/app/context.py))
A single mutable bag threaded through every step:
- `frames` — pandas DataFrames (analysis state)
- `options` — selector option-lists for the UI (e.g. `sample_ids`, `columns`)
- `outputs` — JSON-safe display tables (`{columns, rows}`)
- `charts` — name → PNG data URI
- `exports` — dicts/frames bound for Excel export
- `messages` — user-facing notices (shown in UI + printed as boxes on CLI)
- `notify(message, level, workflow)` — record + print a notice

---

## 4. THE core pattern: how to add a new workflow

This is the single most important thing to remember. Adding a table or chart
workflow is a **4-file change**, all in the backend. The frontend needs **no
changes** for standard tables/charts.

### Step 1 — Write a Python module with a `step(ctx) -> ctx` function
Create e.g. `backend/app/my_workflow.py`. It reads frames/params from `ctx`,
computes results, and writes them back:

```python
from .context import Context

def my_workflow(ctx: Context) -> Context:
    df = ctx.frames["soil_data_filtered"]          # read a prepped frame
    # ... compute ...
    ctx.frames["my_result_df"] = result_df          # store the frame
    ctx.outputs["my_result"] = df_to_records(result_df)  # JSON-safe table
    return ctx
```

- Use `df_to_records(df)` (in `pipeline.py`) to make a JSON-safe
  `{columns, rows}` for `ctx.outputs`.
- For charts, render a matplotlib figure to a PNG buffer and store the data URI
  in `ctx.charts["my_chart"]` (see `tier1_charts.py` for the pattern).
- Use `ctx.notify(...)` for user-facing warnings/errors.

### Step 2 — Register it in the pipeline ([`pipeline.py`](backend/app/pipeline.py))
Import the function and append it to the sequential list inside `run()`:

```python
from .my_workflow import my_workflow
# ...
ctx = my_workflow(ctx)
```

Also, if the output frame is already display-named, add it to the
`for frame_key, out_key in [...]` serialization block near the bottom of `run()`.

### Step 3 — Add any inputs to [`params.py`](backend/app/params.py)
Each param is a dict: `name`, `label`, `kind`, `control`, `tab`, `default`,
`choices`/`options`. Controls: `file | text | number | select | multiselect |
toggle | date | table`. The frontend renders these automatically.

### Step 4 — Declare the tab/output/chart in [`manifest.py`](backend/app/manifest.py)
- Add a tab to `NAV` (or a child under a group).
- Add a table to `OUTPUTS`: `{"var": ..., "label": ..., "tab": ...}`.
- Add a chart to `CHARTS`: `{"var": ..., "label": ..., "tab": ...}`.

The frontend reads `build_schema()` and renders everything automatically.

---

## 5. Key conventions & gotchas

- **`Context` is mutable and shared.** Steps read/write the same `frames` dict.
  This is fine for the current linear pipeline but blocks parallelism — see
  [`parallel-workflows-plan.md`](parallel-workflows-plan.md) for the future
  trunk + branches design (immutability + per-workflow namespaces).
- **`df_to_records`** (in `pipeline.py`) is the standard way to serialize a
  DataFrame for the frontend. It handles NaN/Inf/None, numpy scalars, and
  timestamps.
- **Charts** use `matplotlib` with `matplotlib.use("Agg")` (headless) and are
  stored as PNG data URIs in `ctx.charts`.
- **Golden-CSV regression tests** live in `backend/tests/` with fixtures in
  `tests/fixtures/`. When you change a workflow's output, update the expected
  CSVs. Run with `pytest` from `backend/`.
- **Params are schema-driven, not a rigid model.** `params.py` + `defaults()`
  merge is intentional — keep it that way (see the "What NOT to change" section
  of the parallel-workflows plan).
- **Frontend tabs with special rendering** (not purely generic) are handled
  explicitly in `App.tsx`: `tds_charts`, `tier1_graphs`, `bg_chloride`. Standard
  table tabs are generic.

---

## 6. Useful commands

```bash
# from backend/
source ../ebm-sst-env/bin/activate   # or use the venv
uvicorn app.main:app --reload         # run the API
pytest                                # run the regression tests
```

---

## 7. Related design doc

[`parallel-workflows-plan.md`](parallel-workflows-plan.md) — the future-proofing
plan for running multiple workflows concurrently (trunk + branches, read-only
base frames, per-workflow result namespaces, cache-prep-by-token). Not yet
implemented; the current `run()` is a flat sequential list.