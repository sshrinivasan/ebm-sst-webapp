"""Tier 1 graphs — plots for user-selected samples.

The samples to plot come from the ``tier1_graph_samples`` multiselect, which is
sourced from ``soil_data_filtered['sample_id']`` (see loader.py / params.py).

Each rendered figure is pushed into ``ctx.charts[<var>]`` as a PNG data URI; the
frontend renders it on the tab whose CHARTS entry has the matching ``var``
(see manifest.py). To add more charts, declare another CHARTS entry and set the
matching ``ctx.charts`` key here.
"""
from __future__ import annotations

import base64
import io
import re

import matplotlib
matplotlib.use("Agg")  # headless: render to buffer, never open a window
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import PchipInterpolator
from .loader import cleaned_name_to_excel_header_map, display_name_to_cleaned_name_map
from .context import Context
import pandas as pd

variable_graph_options = [
    'pH',
    'EC (dS/m)',
    'SAR',
    'Saturation (%)',
    'Chloride (mg/L)',
    'Sulphate (mg/L)',
    'Sodium (mg/L)',
    'Calcium (mg/L)',
    'Magnesium (mg/L)',
    'Potassium (mg/L)',
    'Carbonate (mg/L)',
    'Bicarbonate (mg/L)',
    'Chloride (mg/kg)',
    'Sulphate (mg/kg)',
    'Sodium (mg/kg)',
    'Calcium (mg/kg)',
    'Magnesium (mg/kg)',
    'Potassium (mg/kg)',
    'Carbonate (mg/kg)',
    'Bicarbonate (mg/kg)',
    'Chloride (meq/L)',
    'Sulphate (meq/L)',
    'Sodium (meq/L)',
    'Calcium (meq/L)',
    'Magnesium (meq/L)',
    'Potassium (meq/L)',
    'Carbonate (meq/L)',
    'Bicarbonate (meq/L)',
    'Anions Total (meq/L)',
    'Cations Total (meq/L)',
    'Ionic Balance (%)',
    'Sand (%)',
    'Silt (%)',
    'Clay (%)',
    'Soil Texture',
    '75 Micron Sieve (%) ret.',
    'Fine/Coarse',
    'Moisture (%)',
    'Benzene (mg/kg)',
    'Toluene (mg/kg)',
    'Ethylbenzene (mg/kg)',
    'Xylenes (mg/kg)',
    'F1 (C6-C10) - BTEX (mg/kg)',
    'F2 (C10-C16) (mg/kg)',
    'F3 (C16-C34) (mg/kg)',
    'F4 (C34-C50) (mg/kg)',
    'F4G (C34+) (mg/kg)',
    'Acenaphthene (mg/kg)',
    'Acenaphthylene (mg/kg)',
    'Anthracene (mg/kg)',
    'Fluoranthene (mg/kg)',
    'Fluorene (mg/kg)',
    'Naphthalene (mg/kg)',
    'Methylnapthalene (2-) (mg/kg)',
    'Phenanthrene (mg/kg)',
    'Pyrene (mg/kg)',
    'Benzo[a]anthracene (mg/kg)',
    'Benzo[b+j]fluoranthene (mg/kg)',
    'Benzo[k]fluoranthene (mg/kg)',
    'Benzo[g,h,i]perylene (mg/kg)',
    'Benzo[a]pyrene (mg/kg)',
    'Chrysene (mg/kg)',
    'Dibenz[a,h]anthracene (mg/kg)',
    'Indeno[1,2,3-c,d]pyrene (mg/kg)',
    'IACR (Fine) (mg/kg)',
    'IACR (Coarse) (mg/kg)',
    'TPE (mg/kg)',
    'PAH Total (for sediment)* (mg/kg)',
    'Ethylene glycol (mg/kg)',
    'Diethylene glycol (mg/kg)',
    'Triethylene glycol (mg/kg)',
    'Methanol (mg/kg)',
    'Phenol (mg/kg)',
    'Antimony (mg/kg)',
    'Arsenic (inorganic) (mg/kg)',
    'Barium (non-barite) (mg/kg)',
    'Barite-barium (mg/kg)',
    'Extractable Barium (mg/kg)',
    'Beryllium (mg/kg)',
    'Boron (saturated paste) (mg/L)',
    'Boron  (hot water soluble) (mg/kg)',
    'Cadmium (mg/kg)',
    'Chromium (hexavalent) (mg/kg)',
    'Chromium (total) (mg/kg)',
    'Cobalt (mg/kg)',
    'Copper (mg/kg)',
    'Lead (mg/kg)',
    'Manganese (mg/kg)',
    'Mercury (inorganic) (mg/kg)',
    'Molybdenum (mg/kg)',
    'Nickel (mg/kg)',
    'Selenium (mg/kg)',
    'Silver (mg/kg)',
    'Thallium (mg/kg)',
    'Tin (mg/kg)',
    'Uranium (mg/kg)',
    'Vanadium (mg/kg)',
    'Zinc (mg/kg)',
]

def plot_profile(colname, df, samples, reference_lines=None, title=None, reference_label="Guideline",
                 reference_color=None, x_max=None, y_max=None, xlabel=None, depth_line=1.5,
                 depth_line_label=None, min_points_for_spline=1, ax=None, legend_inside=True,
                 figsize=(4, 7.5)):
    """Render one vertical depth profile (a single plot in a panel).

    Plots ``colname`` vs depth (z) for each sample in ``samples``, with optional
    reference lines, a horizontal depth line, and x/y axis limits. When ``ax`` is
    provided the profile is drawn into that existing axes (for multi-panel
    composition); otherwise a new figure is created and returned.

    Every profile renders on a FIXED canvas (serialize with ``tight=False``) with
    the legend drawn INSIDE a reserved bottom strip, so all profile charts export
    at the identical pixel size regardless of how many samples (and thus legend
    rows) the chart has. ``legend_inside=False`` keeps the old behavior: the
    legend is anchored below the figure and the canvas is tight-cropped to
    include it.

    ``figsize`` (default (4, 7.5)) sets the figure size in inches: the axes
    occupies the top 80% (4x6, matching the Tier 1 profile size) and the bottom
    20% is the legend strip.
    """
    xlabel = xlabel or cleaned_name_to_excel_header_map.get(colname, colname)
    own_figure = ax is None
    if own_figure:
        fig, ax = plt.subplots(figsize=figsize, facecolor='white')
        if legend_inside:
            # Reserve the bottom 20% of the fixed canvas for the legend so it
            # stays INSIDE the canvas (tight=False renders don't crop to the
            # drawn content, so a below-figure legend would be clipped).
            fig.subplots_adjust(bottom=0.20)
    else:
        fig = ax.figure
    ax.set_facecolor('white')

    for sample in samples:
        sample_data = df.loc[
            df["sample_id"] == sample,
            ["z", colname],
        ].apply(pd.to_numeric, errors="coerce").dropna()
        
        sample_data = (
            sample_data
            .groupby("z", as_index=False)[colname]
            .mean()
            .sort_values("z")
        )
        x_data = sample_data["z"].to_numpy()
        y_data = sample_data[colname].to_numpy()

        if len(x_data) > min_points_for_spline:
            xnew = np.linspace(x_data.min(), x_data.max(), num=200, endpoint=True)
            cspline = PchipInterpolator(x_data, y_data)
            interp_plot = ax.plot(cspline(xnew), xnew, '-', label=sample)
            ax.plot(y_data, x_data, 'o', color=interp_plot[0].get_color())
        elif len(x_data) > 0:
            ax.plot(y_data, x_data, 's', label=sample)

    if reference_lines:
        ref_colors = ["red", "blue", "green", "orange", "purple", "brown"]
        # Single "Guideline" legend entry covering all reference lines
        ref_labels = reference_label if isinstance(reference_label, (list, tuple)) else None
        ref_label_used = False
        for ref_idx, single_ref in enumerate(reference_lines):
            c = reference_color if reference_color else ref_colors[ref_idx % len(ref_colors)]
            group_label_used = False
            for depth_range, x_val in single_ref:
                if ref_labels is not None:
                    lbl = None if group_label_used else (
                        ref_labels[ref_idx] if ref_idx < len(ref_labels) else None)
                else:
                    lbl = None if ref_label_used else reference_label
                group_label_used = True
                parts = depth_range.split("-")
                y1, y2 = float(parts[0]), float(parts[1])
                ax.plot(
                    [x_val, x_val], [y1, y2],
                    color=c, linewidth=2, linestyle="--",
                    label=lbl,
                )
                ref_label_used = True
            for i in range(len(single_ref) - 1):
                _, x_curr = single_ref[i]
                _, x_next = single_ref[i + 1]
                y_end = float(single_ref[i][0].split("-")[1])
                y_start = float(single_ref[i + 1][0].split("-")[0])
                if y_end == y_start:
                    ax.plot([x_curr, x_next], [y_end, y_start], color=c, linewidth=2, linestyle="--")

    # Set the y-limits in data coordinates BEFORE inverting the axis; calling
    # set_ylim([0, y_max]) after invert_yaxis() resets the axis direction and
    # flips the depth profile.
    if y_max not in (None, "") and float(y_max) > 0:
        ax.set_ylim([0, float(y_max)])
    else:
        ax.set_ylim(bottom=0)
    ax.invert_yaxis()
    if title:
        fig.suptitle(title, fontsize=12, fontweight='bold', y=0.982)
    ax.xaxis.set_label_position('top')
    ax.xaxis.tick_top()
    ax.set_xlabel(xlabel, labelpad=12)
    ax.set_ylabel("Depth (mbgs)")
    ax.grid(which='major', color='#DDDDDD', linewidth=0.8)
    ax.grid(which='minor', color='#DDDDDD', linestyle=':', linewidth=0.8)
    ax.minorticks_on()
    ax.set_xlim([0, float(x_max) if x_max not in (None, "") and float(x_max) > 0 else None])
    if depth_line is not None:
        ax.axhline(y=depth_line, color='black', linestyle='--', linewidth=2, zorder=5,
                   label=depth_line_label)
    if own_figure:
        if legend_inside:
            # Keep the axes above the reserved bottom strip and anchor the
            # legend's top just below the axes so it reads like the Tier 1
            # profiles (legend directly under the plot, never clipped).
            fig.tight_layout(rect=[0, 0.20, 1, 1])
            fig.legend(loc='upper left', bbox_to_anchor=(0, 0.20), ncol=4, frameon=False)
        else:
            plt.tight_layout()
            fig.legend(loc='upper left', bbox_to_anchor=(0, 0), ncol=4, frameon=False)
    return fig


def _fig_to_data_uri(fig, tight: bool = False) -> str:
    """Serialize a matplotlib figure to a base64 PNG data URI and close it.

    ``tight`` (default False) keeps a FIXED canvas (figure size x dpi) so every
    profile chart exports at the identical pixel size regardless of series/legend
    content. Set ``tight=True`` to crop the canvas to the drawn content instead.
    """
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight" if tight else None)
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def _sanitize_filename(name: str) -> str:
    """Replace characters that aren't allowed in filenames with '_'."""
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def _store_figure(fig, ctx: Context, chart_key: str, zip_path: str | None = None) -> None:
    """Store a figure for the app (``ctx.charts``) and, when ``zip_path`` is
    given, for the figures ZIP (``ctx.exports['figure_files']``) at 150 dpi /
    tight bounding box / white background per the export spec. The export PNG is
    saved BEFORE ``_fig_to_data_uri`` closes the figure."""
    if zip_path:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
        buf.seek(0)
        ctx.exports.setdefault("figure_files", {})[zip_path] = buf.getvalue()
    ctx.charts[chart_key] = _fig_to_data_uri(fig)


def tier1_charts(ctx: Context) -> Context:
    selected = ctx.params.get("tier1_graph_samples") or []
    if not selected:
        return ctx  # nothing selected -> no chart

    soil = ctx.frames["soil_data_filtered"]

    # TODO: make parameters
    ab_tier1_chloride_ref_value = 120

    scarg = ctx.frames["scarg_guidelines_df"]
    # EC and SAR guidelines are depth-dependent (one segment per SCARG depth
    # band). Reference lines always use the plain "top-bottom" interval so the
    # plotter's split("-") parsing stays safe even for default-labelled rows
    # (e.g. "subsoil 1.5-6.0 (default)").
    ab_scarg_ec_ref_lines = []
    ab_scarg_sar_ref_lines = []
    for _, row in scarg.iterrows():
        _bounds = _scarg_depth_bounds(row["Depth"])
        if _bounds is None:
            continue
        _ref_depth = "{0:g}-{1:g}".format(_bounds[0], _bounds[1])
        ab_scarg_ec_ref_lines.append((_ref_depth, float(row["EC Guideline"])))
        ab_scarg_sar_ref_lines.append((_ref_depth, float(row["SAR Guideline"])))

    # Chloride Tier 1 is a single flat value; express it as one segment spanning
    # the full plotted depth range so plot_profile draws it as a vertical line.
    z_sel = pd.to_numeric(
        soil.loc[soil["sample_id"].astype(str).isin([str(s) for s in selected]), "z"],
        errors="coerce",
    ).dropna()
    z_max = float(z_sel.max()) if len(z_sel) else 0.0
    ab_tier1_chloride_ref_lines = [("0-{0}".format(z_max), ab_tier1_chloride_ref_value)]

    fig_ec = plot_profile("general_inorganics_ec_ds_m", df=soil, samples=selected,
                          reference_lines=[ab_scarg_ec_ref_lines], title="EC",
                          x_max=ctx.params.get("tier1_ec_x_max"), y_max=ctx.params.get("tier1_ec_y_max"))
    fig_sar = plot_profile("general_inorganics_sar", df=soil, samples=selected,
                           reference_lines=[ab_scarg_sar_ref_lines], title="SAR",
                           x_max=ctx.params.get("tier1_sar_x_max"), y_max=ctx.params.get("tier1_sar_y_max"))
    fig_cl = plot_profile("soluble_ions_chloride_mg_kg", df=soil, samples=selected,
                          reference_lines=[ab_tier1_chloride_ref_lines], title="Chloride",
                          x_max=ctx.params.get("tier1_cl_x_max"), y_max=ctx.params.get("tier1_cl_y_max"))

    _store_figure(fig_ec, ctx, "tier1_graph_ec", "TIER1_GRAPHS/t1_ec.png")
    _store_figure(fig_sar, ctx, "tier1_graph_sar", "TIER1_GRAPHS/t1_sar.png")
    _store_figure(fig_cl, ctx, "tier1_graph_chloride", "TIER1_GRAPHS/t1_cl.png")
    return ctx

    
def _scarg_depth_bounds(text):
    """(top, bottom) numeric bounds of a SCARG Depth value (plain or labelled)."""
    numbers = re.findall(r"\d+(?:\.\d+)?", str(text))
    if len(numbers) >= 2:
        try:
            return float(numbers[0]), float(numbers[1])
        except ValueError:
            pass
    return None


def _limiting_ref(colname, z_max, limiting_df):
    """Build full-depth reference lines/labels from limiting_df (pH has two bounds)."""
    if colname not in limiting_df.columns:
        return None, None
    raw = str(limiting_df[colname].iloc[0]).strip()
    if raw.lower() in ("", "nan", "none", "hide"):
        return None, None

    depth_range = "0-{0:g}".format(z_max if pd.notna(z_max) and z_max > 0 else 99)

    _unit = ""
    _display = cleaned_name_to_excel_header_map.get(colname, colname)
    if "(" in _display and ")" in _display:
        _unit = " " + _display[_display.rfind("(") + 1:_display.rfind(")")]

    values = []
    for part in raw.split("-"):
        try:
            values.append(float(part))
        except ValueError:
            return None, None

    lines = [[(depth_range, v)] for v in values]
    labels = ["{0:g}{1}".format(v, _unit) for v in values]
    return lines, labels

def tier1_variable_charts(ctx: Context) -> Context:
    """User-driven profile plots: two (parameter, boreholes) pairs from the
    Variable Graphs sub-tab. Each pair renders into ``ctx.charts`` under its
    ``tier1_variable_graph_<n>`` key (see manifest.CHARTS / the frontend)."""
    soil_data_filtered = ctx.frames["soil_data_filtered"]
    z_max = pd.to_numeric(soil_data_filtered["z"], errors="coerce").max()
    limiting_df = ctx.frames["limiting_df"]

    pairs = [
        (ctx.params.get("variable_graph_1"),
         ctx.params.get("variable_graph1_boreholes") or [], "tier1_variable_graph_1",
         "variable_graph1_x_max", "variable_graph1_y_max"),
        (ctx.params.get("variable_graph_2"),
         ctx.params.get("variable_graph2_boreholes") or [], "tier1_variable_graph_2",
         "variable_graph2_x_max", "variable_graph2_y_max"),
        (ctx.params.get("variable_graph_3"),
         ctx.params.get("variable_graph3_boreholes") or [], "tier1_variable_graph_3",
         "variable_graph3_x_max", "variable_graph3_y_max"),
    ]
    for _var, _boreholes, _chart_key, _xmax_key, _ymax_key in pairs:
        if not _var or not _boreholes:
            continue  # incomplete pair -> no chart
        _col = display_name_to_cleaned_name_map.get(_var)
        if not _col or _col not in soil_data_filtered.columns:
            ctx.notify(f"No data available for '{_var}'.", "warning", "tier1_variable_charts")
            continue
        _lines, _labels = _limiting_ref(_col, z_max, limiting_df)
        fig = plot_profile(_col, df=soil_data_filtered, samples=_boreholes,
                           reference_lines=_lines, reference_label=_labels or "Guideline",
                           reference_color="red", title=_var,
                           x_max=ctx.params.get(_xmax_key), y_max=ctx.params.get(_ymax_key))
        # ZIP file named after the parameter's display name with illegal
        # filename characters replaced by "_" (e.g. "Sulphate (mg_L).png").
        _store_figure(fig, ctx, _chart_key, f"TIER1_GRAPHS/{_sanitize_filename(_var)}.png")
    return ctx
