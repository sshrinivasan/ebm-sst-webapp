import base64
import io

import matplotlib
matplotlib.use("Agg")  # headless: render to buffer, never open a window
from numpy.polynomial.polynomial import polyfit
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from .context import Context


bg_chloride_header_columns = {
    'sample_id': 'Location',
    'depth_m': 'Depth (m)',
    'z': 'Z',
    'comments': 'Comments',
    'general_inorganics_ph': 'pH',
    'general_inorganics_ec_ds_m': 'EC (dS/m)',
    'general_inorganics_sar': 'SAR',
    'general_inorganics_saturation': 'Sat (%)',
    # mg/kg
    'soluble_ions_chloride_mg_kg': 'Cl (mg/kg)',
    'soluble_ions_sulphate_mg_kg': 'SO4 (mg/kg)',
    'soluble_ions_sodium_mg_kg': 'Na (mg/kg)',
    'soluble_ions_calcium_mg_kg': 'Ca (mg/kg)',
    'soluble_ions_magnesium_mg_kg': 'Mg (mg/kg)',
    'soluble_ions_potassium_mg_kg': 'K (mg/kg)',
    'soluble_ions_carbonate_mg_kg': 'CO3 (mg/kg)',
    'soluble_ions_bicarbonate_mg_kg': 'HCO3 (mg/kg)',
    # mg/l
    'soluble_ions_chloride_mg_l': 'Cl (mg/L)',
    'soluble_ions_sulphate_mg_l': 'SO4 (mg/L)',
    'soluble_ions_sodium_mg_l': 'Na (mg/L)',
    'soluble_ions_calcium_mg_l': 'Ca (mg/L)',
    'soluble_ions_magnesium_mg_l': 'Mg (mg/L)',
    'soluble_ions_potassium_mg_l': 'K (mg/L)',
    'soluble_ions_carbonate_mg_l': 'CO3 (mg/L)',
    'soluble_ions_bicarbonate_mg_l': 'HCO3 (mg/L)',
    # meq/L
    'soluble_ions_chloride_meq_l': 'Cl (meq/L)',
    'soluble_ions_sulphate_meq_l': 'SO4 (meq/L)',
    'soluble_ions_sodium_meq_l': 'Na (meq/L)',
    'soluble_ions_calcium_meq_l': 'Ca (meq/L)',
    'soluble_ions_magnesium_meq_l': 'Mg (meq/L)',
    'soluble_ions_potassium_meq_l': 'K (meq/L)',
    'soluble_ions_carbonate_meq_l': 'CO3 (meq/L)',
    'soluble_ions_bicarbonate_meq_l': 'HCO3 (meq/L)',
 }

bg_chloride_reverse_lookup = {v: k for k, v in bg_chloride_header_columns.items()}
del bg_chloride_reverse_lookup["Location"]
del bg_chloride_reverse_lookup["Depth (m)"]
del bg_chloride_reverse_lookup["Z"]
del bg_chloride_reverse_lookup["Comments"]
del bg_chloride_reverse_lookup["pH"]
del bg_chloride_reverse_lookup["EC (dS/m)"]
del bg_chloride_reverse_lookup["SAR"]
del bg_chloride_reverse_lookup["Sat (%)"]

def bg_scatter_plot(df, x_data, y_data, x_max, y_max, x_label=None, y_label=None, trendline=True, chloride_group_ref=100):
    bg_labels = ["background", "apec background"]
    if "apec" in df.columns:
        is_bg = df["apec"].astype("string").str.strip().str.lower().isin(bg_labels).fillna(False)
    else:
        is_bg = pd.Series(False, index=df.index)
    x_data = pd.to_numeric(pd.Series(x_data, index=df.index), errors="coerce")
    y_data = pd.to_numeric(pd.Series(y_data, index=df.index), errors="coerce")
    chloride_group_data = pd.to_numeric(df["soluble_ions_chloride_mg_kg"], errors="coerce")
    chloride_group_ref = float(chloride_group_ref)
    chloride_group_ref_label = f"{chloride_group_ref:g}"

    mask1 = is_bg & (chloride_group_data <= chloride_group_ref)
    mask2 = is_bg & (chloride_group_data > chloride_group_ref)
    mask3 = ~is_bg

    fig, ax = plt.subplots(figsize=(10.5, 5.5))

    r2_texts = []
    for mask_i, color, label in [
        (mask1, "tab:blue", f"BKGD samples Cl <= {chloride_group_ref_label} mg/kg"),
        (mask2, "tab:orange", f"BKGD samples Cl > {chloride_group_ref_label} mg/kg"),
        (mask3, "tab:green", "Impact Area Samples"),
    ]:
        x = x_data[mask_i].dropna()
        y = y_data[mask_i].reindex(x.index).dropna()
        x = x.reindex(y.index)
        ax.scatter(x, y, alpha=0.7, label=label, color=color)
        if len(x) >= 2:
            b, m = polyfit(x, y, 1)
            ss_res = np.sum((y - (b + m * x)) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 0
            r2_texts.append((label, r2, color))
            if trendline:
                x_line = np.array([x.min(), x.max()])
                ax.plot(x_line, b + m * x_line, color=color, linewidth=1.5, linestyle="--", label="_nolegend_")

    ax.set_xlim(0, x_max)
    ax.set_ylim(0, y_max)
    ax.set_aspect('auto')
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, frameon=False)
    ax.grid(True, linestyle="--", linewidth=0.5)

    if trendline and r2_texts:
        for i, (lbl, r2, clr) in enumerate(r2_texts):
            ax.annotate(f"R\u00b2={r2:.3f}", xy=(1.02, 0.95 - i * 0.06),
                        xycoords='axes fraction', fontsize=9, fontweight='bold',
                        color=clr, verticalalignment='top', annotation_clip=False)

    plt.tight_layout(rect=[0, 0, 0.84, 1])
    plt.subplots_adjust(bottom=0.25, right=0.84)
    return fig

def get_bg_metric_data(soil_data_filtered, metric_label):
    if not metric_label:
        raise ValueError("Select a metric for every selected axis operation.")
    if metric_label not in bg_chloride_reverse_lookup:
        raise ValueError(f"Metric '{metric_label}' is not available for plotting.")

    metric_col = bg_chloride_reverse_lookup[metric_label]
    if metric_col not in soil_data_filtered.columns:
        raise ValueError(f"Column '{metric_col}' for metric '{metric_label}' is missing from soil_data_filtered.")

    metric_data = pd.to_numeric(soil_data_filtered[metric_col], errors="coerce")
    if metric_data.notna().sum() == 0:
        raise ValueError(f"Metric '{metric_label}' has no numeric data to plot.")

    return metric_data


def build_plot_axis(soil_data_filtered, metric_a, metric_b, operation):
    operation = operation or "A only"
    metric_a_data = get_bg_metric_data(soil_data_filtered, metric_a)

    if operation == "A only":
        return metric_a_data, metric_a

    metric_b_data = get_bg_metric_data(soil_data_filtered, metric_b)
    valid_operands = metric_a_data.notna() & metric_b_data.notna()
    if not valid_operands.any():
        raise ValueError(f"No rows have data for both '{metric_a}' and '{metric_b}'.")

    if operation == "A+B":
        return metric_a_data + metric_b_data, f"{metric_a} + {metric_b}"

    if operation == "A/B":
        valid_divisor = metric_b_data.notna() & (metric_b_data != 0)
        if not (metric_a_data.notna() & valid_divisor).any():
            raise ValueError(f"No rows have valid data for '{metric_a} / {metric_b}' with a non-zero divisor.")
        return metric_a_data / metric_b_data.replace(0, np.nan), f"{metric_a} / {metric_b}"

    if operation == "B/A":
        valid_divisor = metric_a_data.notna() & (metric_a_data != 0)
        if not (metric_b_data.notna() & valid_divisor).any():
            raise ValueError(f"No rows have valid data for '{metric_b} / {metric_a}' with a non-zero divisor.")
        return metric_b_data / metric_a_data.replace(0, np.nan), f"{metric_b} / {metric_a}"

    raise ValueError(f"Unsupported operation '{operation}'.")

bg_chloride_plottable_metrics = ["Cl", "SO4", "Na", "Ca", "Mg", "K", "CO3", "HCO3"]
def _metric_with_units(metric, units):
    if not metric:
        return metric
    metric_base = str(metric).split("(", 1)[0].strip()
    return f"{metric_base} ({units})"


def _bg_axis_name(metric_a, metric_b, operation):
    a = str(metric_a or "").split("(", 1)[0].strip()
    b = str(metric_b or "").split("(", 1)[0].strip()
    operation = operation or "A only"
    if operation == "A+B":
        return f"{a}+{b}"
    if operation == "A/B":
        return f"{a}-{b}"
    if operation == "B/A":
        return f"{b}-{a}"
    return a


def _bg_figure_name(x_args, y_args):
    return f"{_bg_axis_name(*y_args)}_{_bg_axis_name(*x_args)}.png"


def _axis_max_or_none(axis_max):
    if axis_max is None or str(axis_max).strip() == "":
        return None
    return float(axis_max)


def render_bg_scatter(df, x_metric_a, x_metric_b, x_operation, y_metric_a, y_metric_b,
                      y_operation, units, x_axis_max, y_axis_max, trendline,
                      chloride_group_ref):
    x_a = _metric_with_units(x_metric_a, units)
    x_b = _metric_with_units(x_metric_b, units)
    y_a = _metric_with_units(y_metric_a, units)
    y_b = _metric_with_units(y_metric_b, units)

    x_data, x_label = build_plot_axis(df, x_a, x_b, x_operation)
    y_data, y_label = build_plot_axis(df, y_a, y_b, y_operation)

    fig = bg_scatter_plot(
        df,
        x_data,
        y_data,
        _axis_max_or_none(x_axis_max),
        _axis_max_or_none(y_axis_max),
        x_label=x_label,
        y_label=y_label,
        trendline=bool(trendline),
        chloride_group_ref=chloride_group_ref,
    )
    return fig


def _fig_to_data_uri(fig) -> str:
    """Serialize a matplotlib figure to a base64 PNG data URI and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def bg_chloride_charts(ctx: Context) -> Context:
    """BG Chloride tab: 3 identical user-driven scatter plots (see params.py /
    manifest.py 'bg_chloride' tab). Each plot n reads its 8 axis controls
    (plot{n}_x_axis_metric1/2, plot{n}_x_operation, plot{n}_x_axis_max, and
    the Y equivalents) from ctx.params and, if configured, renders into
    ctx.charts['bg_chloride_plot_{n}']."""
    soil_data_filtered = ctx.frames["soil_data_filtered"]

    for n in (1, 2, 3):
        x_metric_a = ctx.params.get(f"plot{n}_x_axis_metric1")
        y_metric_a = ctx.params.get(f"plot{n}_y_axis_metric1")
        if not x_metric_a or not y_metric_a:
            continue  # incomplete selection -> no chart for this plot

        try:
            fig = render_bg_scatter(
                soil_data_filtered,
                x_metric_a,
                ctx.params.get(f"plot{n}_x_axis_metric2"),
                ctx.params.get(f"plot{n}_x_operation") or "A only",
                y_metric_a,
                ctx.params.get(f"plot{n}_y_axis_metric2"),
                ctx.params.get(f"plot{n}_y_operation") or "A only",
                units="mg/kg",
                x_axis_max=ctx.params.get(f"plot{n}_x_axis_max"),
                y_axis_max=ctx.params.get(f"plot{n}_y_axis_max"),
                trendline=True,
                chloride_group_ref=ctx.params.get("chloride_guideline", 100),
            )
        except ValueError as e:
            ctx.notify(str(e), "warning", "bg_chloride_charts")
            continue

        ctx.charts[f"bg_chloride_plot_{n}"] = _fig_to_data_uri(fig)


    # BG Chloride data
    bg_chloride_df = soil_data_filtered[bg_chloride_header_columns.keys()]
    bg_chloride_df_display = bg_chloride_df.rename(columns=bg_chloride_header_columns)
    ctx.frames["bg_chloride_df"] = bg_chloride_df_display
    return ctx
