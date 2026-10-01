"""Chloride Delineation — vertical chloride profiles with a reference line.

Plots the selected chloride column (mg/L or mg/kg) vs depth for the
user-selected boreholes, batched 15 per figure so each profile stays legible,
with a horizontal reference line at the user-supplied chloride reference value.

Each figure is pushed into ``ctx.charts["cl_delineation_profile_<n>"]`` as a
PNG data URI; the frontend renders them on the Chloride Delineation tab (see
the special-cased tab render in App.tsx / ResultsViewer.tsx).
"""
from __future__ import annotations

import pandas as pd

from .context import Context
from .tier1_charts import plot_profile, _fig_to_data_uri

# Chloride Units dropdown value -> soil_data_filtered column.
PROFILE_TYPE_MAP = {
    "mg/L": "soluble_ions_chloride_mg_l",
    "mg/kg": "soluble_ions_chloride_mg_kg",
}

# Max boreholes per figure (keeps each profile legible).
BOREHOLES_PER_PLOT = 15


def chloride_delineation(ctx: Context) -> Context:
    """Render one vertical chloride profile per 15-borehole batch.

    Reads from ``ctx.params``:
      cl_delineation_samples  multiselect of boreholes to plot (sample_ids)
      cl_delineation_units    "mg/L" | "mg/kg" — picks the chloride column
      chloride_guideline      shared "Chloride guideline (mg/kg)" input from the
                              Configure page — the reference line value
      cl_delineation_x_max    x-axis max (concentration), from the Plot config
      cl_delineation_y_max    y-axis max (depth), from the Plot config
    """
    selected = ctx.params.get("cl_delineation_samples") or []
    if not selected:
        ctx.notify("No samples selected for Chloride Delineation.", "warning", "cl_delineation")
        return ctx

    units = ctx.params.get("cl_delineation_units", "mg/L")
    profile_col = PROFILE_TYPE_MAP.get(units)
    if profile_col is None:
        ctx.notify(f"Unsupported chloride units: {units!r}", "error", "cl_delineation")
        return ctx

    soil = ctx.frames["soil_df_averaged"]
    if profile_col not in soil.columns:
        ctx.notify(f"No data available for '{units}' chloride.", "warning", "cl_delineation")
        return ctx

    # Reference line value comes from the shared "Chloride guideline (mg/kg)"
    # input on the Configure page (default 100).
    reference = ctx.params.get("chloride_guideline")
    x_max = ctx.params.get("cl_delineation_x_max")
    y_max = ctx.params.get("cl_delineation_y_max")

    for i in range(0, len(selected), BOREHOLES_PER_PLOT):
        batch = selected[i:i + BOREHOLES_PER_PLOT]
        max_depth = pd.to_numeric(
            soil.loc[soil["sample_id"].astype(str).isin([str(s) for s in batch]), "z"],
            errors="coerce",
        ).max()

        # Reference line spans the full plotted depth range at the reference
        # value. Only drawn when a positive reference was supplied.
        reference_lines = None
        if pd.notna(max_depth) and reference not in (None, "", 0):
            reference_lines = [[(f"0-{max_depth}", float(reference))]]

        fig = plot_profile(
            profile_col,
            df=soil,
            samples=batch,
            reference_lines=reference_lines,
            title=f"Soil Chloride ({units})",
            x_max=x_max,
            y_max=y_max,
        )
        ctx.charts[f"cl_delineation_profile_{i // BOREHOLES_PER_PLOT + 1}"] = _fig_to_data_uri(fig)

    return ctx
