"""Pipeline orchestrator — runs the modular analysis in order.

Each step is a plain function `step(ctx) -> ctx` (see loader.py). As we port
more sections, append them below. Also holds the small df -> JSON helper used to
build display outputs for the frontend.
"""
from __future__ import annotations

import math
import datetime as dt
from typing import Any

import pandas as pd
import numpy as np

from .context import Context
from .params import defaults
from .loader import (
    load, drop_duplicate_rows, convert_units, average_duplicates,
    read_sst_guidelines, cleaned_name_to_excel_header_map,
)
from .ec_sar_rating import validate_topsoil_depths, compute_ec_sar_ratings
from .background_guidelines import compute_scarg_guidelines
from .borehole_stats import filter_borehole_data
from .tier1_exceedances import tier1_exceedances
from .sst_exceedances import sst_exceedances
from .tier1_charts import tier1_charts, tier1_variable_charts
from .bg_chloride import bg_chloride_charts
from .sst_charts import seed_sst_chloride, sst_chloride_charts
from .texture import texture_analysis, saturation_profile
from .tds import tds_analysis, tds_tests
from .percentile_95 import ninetyfifth_percentile
from .npp import npp_analysis, npp_sulphate_tests

def _clean_scalar(v: Any) -> Any:
    if v is None or v is pd.NA:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (pd.Timestamp, dt.datetime, dt.date)):
        return v.isoformat()
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def df_to_records(df: pd.DataFrame) -> dict:
    """JSON-safe {columns, rows} for the frontend."""
    columns = [str(c) for c in df.columns]
    rows = [
        {str(col): _clean_scalar(val) for col, val in zip(columns, row)}
        for row in df.itertuples(index=False, name=None)
    ]
    return {"columns": columns, "rows": rows}


def build_context(excel_path: str, params: dict | None = None) -> Context:
    merged = {**defaults(), **(params or {})}
    return Context(excel_path=excel_path, params=merged)


def run(excel_path: str, params: dict | None = None) -> Context:
    ctx = build_context(excel_path, params)

    # Site-specific (SST) workflows are gated by the sst_flag param. When it is
    # off, the SST analysis steps are skipped entirely (and the corresponding
    # tabs are filtered from the schema — see manifest.build_schema).
    sst_enabled = bool(ctx.params.get("sst_flag", True))

    ctx = load(ctx)
    ctx = read_sst_guidelines(ctx)
    ctx = drop_duplicate_rows(ctx)
    ctx = convert_units(ctx)
    ctx = average_duplicates(ctx)
    ctx = validate_topsoil_depths(ctx)
    ctx = compute_ec_sar_ratings(ctx)
    ctx = compute_scarg_guidelines(ctx)
    ctx = filter_borehole_data(ctx)
    ctx = tier1_exceedances(ctx)
    if sst_enabled:
        ctx = npp_analysis(ctx)
        ctx = npp_sulphate_tests(ctx)
        ctx = sst_exceedances(ctx)
    ctx = tier1_charts(ctx)
    ctx = tier1_variable_charts(ctx)
    ctx = bg_chloride_charts(ctx)
    if sst_enabled:
        ctx = texture_analysis(ctx)
        ctx = saturation_profile(ctx)
        ctx = tds_analysis(ctx)
        ctx = tds_tests(ctx)
        ctx = ninetyfifth_percentile(ctx)
        ctx = seed_sst_chloride(ctx)
        ctx = sst_chloride_charts(ctx)

    # future: ctx = texture_split(ctx); ...

    # snake_case frames shown with human-friendly display names
    for frame_name, out_key in [
        ("soil_data_filtered", "soil_data_preview"),
    ]:
        frame = ctx.frames.get(frame_name)
        if frame is not None:
            preview = frame.rename(columns=cleaned_name_to_excel_header_map)
            ctx.outputs[out_key] = df_to_records(preview.head(200))

    # already-display-named frames -> serialize as-is
    for frame_key, out_key in [
        ("ec_sar_category_report_df", "ec_sar_category_report"),
        ("scarg_rating_guideline_summary_df", "scarg_rating_guideline_summary"),
        ("scarg_guidelines_df", "scarg_guidelines"),
        ("ec_report_data_display_df_hex", "ec_guidelines_summary"),
        ("sar_report_data_display_df_hex", "sar_guidelines_summary"),
        ("borehole_characteristics", "borehole_characteristics"),
        ("borehole_data", "borehole_data"),
        ("tier1_exceedances_display_df", "tier1_exceedances"),
        ("all_exceedances_display_df", "site_specific_exceedances"),
        ("bg_chloride_df", "bg_chloride_df"),
        ("texture_analysis", "texture_analysis"),
        ("tds_data_table", "tds_data_table"),
        ("tds_grouped_data", "tds_grouped_data"),
        ("tds_test_results", "tds_test_results"),
        ("npp_test_results", "npp_test_results"),
        ("npp_marginal_results", "npp_marginal_results"),
        ("npp_numerical_ref_info", "npp_numerical_ref_info"),
        ("npp_test_statistics", "npp_test_statistics"),
        ("npp_selected_data", "npp_selected_data"),
        ("borehole_sa_df", "borehole_sa_df"),
        ("additional_guidelines_df", "additional_guidelines_df"),
        ("chloride_plot_config", "chloride_plot_config"),
    ]:
        if frame_key in ctx.frames:
            ctx.outputs[out_key] = df_to_records(ctx.frames[frame_key])

    # Per-subarea 95th Percentile tables (dynamic keys, e.g. p95_subsoil_mass_<key>).
    for frame_key in ctx.frames:
        if frame_key.startswith("p95_"):
            ctx.outputs[frame_key] = df_to_records(ctx.frames[frame_key])

    # 95th Percentile subarea data table (displayed inside the 95th Percentile tab).
    if "percentile_95_subarea_data" in ctx.frames:
        ctx.outputs["percentile_95_subarea_data"] = df_to_records(ctx.frames["percentile_95_subarea_data"])
    return ctx
