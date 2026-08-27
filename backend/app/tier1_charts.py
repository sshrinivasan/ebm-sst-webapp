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

import matplotlib
matplotlib.use("Agg")  # headless: render to buffer, never open a window
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import make_interp_spline, interp1d, PchipInterpolator
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
                 reference_color=None, x_max=None):
    xlabel = cleaned_name_to_excel_header_map.get(colname, colname)
    fig, ax = plt.subplots(figsize=(4, 6), facecolor='white')
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

        if len(x_data) > 1:
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
    ax.axhline(y=1.5, color='black', linestyle='--', linewidth=2, zorder=5)
    plt.tight_layout()
    fig.legend(loc='upper left', bbox_to_anchor=(0, 0), ncol=4, frameon=False)
    return fig


def _fig_to_data_uri(fig) -> str:
    """Serialize a matplotlib figure to a base64 PNG data URI and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def tier1_charts(ctx: Context) -> Context:
    selected = ctx.params.get("tier1_graph_samples") or []
    if not selected:
        return ctx  # nothing selected -> no chart

    soil = ctx.frames["soil_data_filtered"]

    # TODO: make parameters
    ab_tier1_chloride_ref_value = 120

    scarg = ctx.frames["scarg_guidelines_df"]
    # EC and SAR guidelines are depth-dependent (one segment per SCARG depth band).
    ab_scarg_ec_ref_lines = [(row["Depth"], float(row["EC Guideline"])) for _, row in scarg.iterrows()]
    ab_scarg_sar_ref_lines = [(row["Depth"], float(row["SAR Guideline"])) for _, row in scarg.iterrows()]

    # Chloride Tier 1 is a single flat value; express it as one segment spanning
    # the full plotted depth range so plot_profile draws it as a vertical line.
    z_sel = pd.to_numeric(
        soil.loc[soil["sample_id"].astype(str).isin([str(s) for s in selected]), "z"],
        errors="coerce",
    ).dropna()
    z_max = float(z_sel.max()) if len(z_sel) else 0.0
    ab_tier1_chloride_ref_lines = [("0-{0}".format(z_max), ab_tier1_chloride_ref_value)]

    fig_ec = plot_profile("general_inorganics_ec_ds_m", df=soil, samples=selected,
                          reference_lines=[ab_scarg_ec_ref_lines], title="EC")
    fig_sar = plot_profile("general_inorganics_sar", df=soil, samples=selected,
                           reference_lines=[ab_scarg_sar_ref_lines], title="SAR")
    fig_cl = plot_profile("soluble_ions_chloride_mg_kg", df=soil, samples=selected,
                          reference_lines=[ab_tier1_chloride_ref_lines], title="Chloride")

    ctx.charts["tier1_graph_ec"] = _fig_to_data_uri(fig_ec)
    ctx.charts["tier1_graph_sar"] = _fig_to_data_uri(fig_sar)
    ctx.charts["tier1_graph_chloride"] = _fig_to_data_uri(fig_cl)
    return ctx

    
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
         ctx.params.get("variable_graph1_boreholes") or [], "tier1_variable_graph_1"),
        (ctx.params.get("variable_graph_2"),
         ctx.params.get("variable_graph2_boreholes") or [], "tier1_variable_graph_2"),
    ]
    for _var, _boreholes, _chart_key in pairs:
        if not _var or not _boreholes:
            continue  # incomplete pair -> no chart
        _col = display_name_to_cleaned_name_map.get(_var)
        if not _col or _col not in soil_data_filtered.columns:
            ctx.notify(f"No data available for '{_var}'.", "warning", "tier1_variable_charts")
            continue
        _lines, _labels = _limiting_ref(_col, z_max, limiting_df)
        fig = plot_profile(_col, df=soil_data_filtered, samples=_boreholes,
                           reference_lines=_lines, reference_label=_labels or "Guideline",
                           reference_color="red", title=_var)
        ctx.charts[_chart_key] = _fig_to_data_uri(fig)
    return ctx
