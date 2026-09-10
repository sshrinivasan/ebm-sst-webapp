"""SST Charts — site-specific chart seeding and generation.

The SST Charts tab is split into three page sub-tabs: SST Chloride, SST Sodium
and SST SAR. Only the SST Chloride sub-tab is implemented so far; it exposes two
input tables (schema-driven, see params.py / the frontend's `sst_charts` block):

  - Additional Guidelines   (Label / Depth Interval / Guideline)
  - Chloride Plot Config    (Subarea / Excluded Boreholes / Additional
                            Reference Lines), whose rows are seeded from a
                            file-derived default list of valid subareas.

For the Chloride Plot Config table, each row's "Excluded Boreholes" multiselect
only offers the boreholes whose ``soil_data_filtered.subarea`` matches the row's
Subarea, and "Additional Reference Lines" offers the Labels entered in the
Additional Guidelines table (resolved client-side from the params).
"""
from __future__ import annotations

import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .context import Context
from .tier1_charts import plot_profile

# Plot-config table columns, in the exact order the frontend renders them.
PLOT_CONFIG_COLUMNS = ["Subarea", "Excluded Boreholes", "Additional Reference Lines"]


def _fig_to_data_uri(fig) -> str:
    """Serialize a matplotlib figure to a base64 PNG data URI and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def _slugify(name: str) -> str:
    """Turn a subarea name into a safe, unique key suffix (lowercase, no spaces)."""
    return "".join(ch if ch.isalnum() else "_" for ch in str(name).strip().lower()).strip("_")


def build_subarea_borehole_map(soil_data_filtered: pd.DataFrame) -> dict[str, list[str]]:
    """Map each valid subarea -> sorted list of its borehole (sample) ids.

    Straight from the ``subarea`` / ``sample_id`` columns of the cleaned soil
    table. Used to restrict each plot-config row's "Excluded Boreholes"
    multiselect to boreholes that actually belong to that subarea.
    """
    out: dict[str, list[str]] = {}
    subareas = soil_data_filtered["subarea"].astype(str).str.strip()
    for subarea, group in soil_data_filtered.groupby(subareas):
        if not subarea or str(subarea).strip().lower() in ("", "nan", "none"):
            continue
        out[subarea] = sorted(str(s) for s in group["sample_id"].dropna().unique())
    return out


def build_plot_config_default(soil_data_filtered: pd.DataFrame) -> dict:
    """File-derived default for the Chloride Plot Config input table.

    One row per valid subarea present in the soil table, with an empty
    ``Excluded Boreholes`` list and an empty ``Additional Reference Lines`` list.
    Returned as a JSON-safe ``{columns, rows}`` so the upload endpoint can drop
    it into ``ctx.options`` and the frontend can pre-fill the table control
    (same pattern as borehole_sa_df).
    """
    subarea_map = build_subarea_borehole_map(soil_data_filtered)
    return {
        "columns": PLOT_CONFIG_COLUMNS,
        "rows": [
            {"subarea": s, "excluded_boreholes": [], "additional_reference_lines": []}
            for s in sorted(subarea_map)
        ],
    }


def seed_sst_chloride(ctx: Context) -> Context:
    """Seed the SST Chloride inputs + file-derived options on the Context.

    Produces:
      additional_guidelines_df  - Label / Depth Interval / Guideline rows the
                                  user entered on the subtab.
      chloride_plot_config      - Subarea / Excluded Boreholes / Additional
                                  Reference Lines, with the two list columns
                                  normalized to real lists.
      options.sst_subarea_boreholes / options.chloride_plot_config_default
                                - file-derived selector seed (also set on
                                  upload; refreshed here so runs stay fresh).
    """
    soil_data_filtered = ctx.frames["soil_data_filtered"]

    # Table 1 — Additional Guidelines (Label / Depth Interval / Guideline).
    # Explicit columns so downstream code (render_sst_profile_set) never hits a
    # KeyError when the user left the table empty (pd.DataFrame([]) has none).
    additional_rows = ctx.params.get("chloride_additional_guidelines") or []
    additional_guidelines_df = pd.DataFrame(
        additional_rows, columns=["Label", "Depth Interval", "Guideline"]
    )
    ctx.frames["additional_guidelines_df"] = additional_guidelines_df

    # Per-subarea borehole map for the Excluded Boreholes multiselect (only
    # boreholes whose soil_data_filtered.subarea matches the row's Subarea).
    # Seeded here (after a run) and on upload (see main.py).
    ctx.options["sst_subarea_boreholes"] = build_subarea_borehole_map(soil_data_filtered)

    # Table 2 — Chloride Plot Config. The frontend multiselects send the
    # Excluded Boreholes / Additional Reference Lines cells as lists (already
    # JSON-safe); normalize a comma-separated string just in case.
    config_rows = ctx.params.get("chloride_plot_config") or []
    plot_config_records = []
    for _row in config_rows:
        subarea = str(_row.get("subarea") or "").strip()
        if not subarea:
            continue  # skip blank rows
        excluded = _row.get("excluded_boreholes") or []
        if isinstance(excluded, str):
            excluded = [s.strip() for s in excluded.split(",") if s.strip()]
        ref_lines = _row.get("additional_reference_lines") or []
        if isinstance(ref_lines, str):
            ref_lines = [s.strip() for s in ref_lines.split(",") if s.strip()]
        plot_config_records.append({
            "Subarea": subarea,
            "Excluded Boreholes": list(excluded),
            "Additional Reference Lines": list(ref_lines),
        })

    chloride_plot_config = pd.DataFrame(plot_config_records, columns=PLOT_CONFIG_COLUMNS)
    ctx.frames["chloride_plot_config"] = chloride_plot_config

    # Keep the file-derived default available as an option so the frontend can
    # re-seed the table on every run (not just on upload).
    ctx.options["chloride_plot_config_default"] = build_plot_config_default(soil_data_filtered)

    return ctx


def render_sst_profile_set(
    plot_config,
    additional_guidelines,
    column,
    df,
    valid_subareas,
    config_label,
    save_prefix=None,
    save_name=None,
    sst_guidelines=None,
    sst_guideline_column=None,
    sst_units="",
    fallback_guidelines=None,
    x_max=None,
):
    """Render one vertical-profile figure per subarea row in ``plot_config``.

    Returns ``{chart_key: plt.Figure}``. Each subarea's figure plots the
    selected bores (minus exclusions) against the column, with:
      - SST guideline reference lines (per subarea / depth) when provided,
      - the user's Additional Guidelines (Label / Depth Interval / Guideline),
      - a fallback guideline from ``fallback_guidelines`` when neither apply.
    """
    valid_subareas = set(valid_subareas)
    if "Label" in additional_guidelines.columns:
        valid_ref_subareas = set(additional_guidelines["Label"].dropna().unique())
    else:
        valid_ref_subareas = set()

    figs = {}
    for _, row in plot_config.iterrows():
        subarea = row["Subarea"]
        if not subarea or str(subarea).strip() == "":
            continue

        all_samples = sorted(df.loc[df["subarea"] == subarea, "sample_id"].unique().tolist())
        # seed_sst_chloride stores these cells as real lists; fall back to
        # comma-string parsing only when a caller passes a legacy string.
        exclude_raw = row.get("Excluded Boreholes") or []
        exclude = (
            [s.strip() for s in str(exclude_raw).split(",") if s.strip()]
            if isinstance(exclude_raw, str)
            else [str(s).strip() for s in exclude_raw if str(s).strip()]
        )
        samples = [s for s in all_samples if s not in exclude]

        if not samples:
            print(f"Skipping '{subarea}': no boreholes after exclusions.")
            continue

        ref_names_raw = row.get("Additional Reference Lines") or []
        ref_names = (
            [s.strip() for s in str(ref_names_raw).split(",") if s.strip()]
            if isinstance(ref_names_raw, str)
            else [str(s).strip() for s in ref_names_raw if str(s).strip()]
        )
        valid = additional_guidelines[
            additional_guidelines["Label"].isin(ref_names)
            & additional_guidelines["Depth Interval"].notna()
            & (additional_guidelines["Depth Interval"] != "")
            & additional_guidelines["Guideline"].notna()
            & (additional_guidelines["Guideline"] != "")
        ]
        ref_lines = []
        ref_labels = []

        if sst_guidelines is not None and sst_guideline_column:
            sst_rows = sst_guidelines[
                sst_guidelines["Subarea"].astype(str).str.strip() == str(subarea).strip()
            ]
            for _, r in sst_rows.iterrows():
                depth_range = str(r.get("Depth Range", "")).strip()
                raw_value = r.get(sst_guideline_column)
                if not depth_range or "-" not in depth_range or raw_value in (None, ""):
                    continue
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                ref_lines.append([(depth_range, value)])
                ref_labels.append(
                    f"{value:g} {sst_units}".strip()
                )

        if not ref_lines and fallback_guidelines is not None and column in fallback_guidelines.columns:
            try:
                fallback_value = float(fallback_guidelines[column].iloc[0])
            except (TypeError, ValueError):
                fallback_value = None
            if fallback_value is not None and fallback_value == fallback_value:
                sample_depths = df.loc[df["sample_id"].isin(samples), "z"]
                sample_depths = pd.to_numeric(sample_depths, errors="coerce").dropna()
                if not sample_depths.empty:
                    ref_lines.append([(f"0-{sample_depths.max():g}", fallback_value)])
                    ref_labels.append(f"{fallback_value:g} {sst_units}".strip())

        for _, r in valid.iterrows():
            ref_lines.append([(r["Depth Interval"], float(r["Guideline"]))])
            ref_labels.append(str(r["Label"]))

        fig = plot_profile(column, df=df, samples=samples,
                           reference_lines=ref_lines or None,
                           reference_label=ref_labels or "Guideline",
                           title=subarea, x_max=x_max)

        key = f"sst_cl_profile_{config_label.lower()}_{_slugify(subarea)}"
        figs[key] = fig

    return figs


def sst_chloride_charts(ctx: Context) -> Context:
    """Generate the SST Chloride vertical-profile charts per subarea.

    Reads the seeded frames/params from the Context (set by seed_sst_chloride)
    plus the file-derived SST chloride guidelines (module-level for now), and
    pushes each subarea figure into ``ctx.charts``.
    """
    soil_data_filtered = ctx.frames["soil_data_filtered"]
    plot_config = ctx.frames["chloride_plot_config"]
    additional_guidelines = ctx.frames["additional_guidelines_df"]
    ab_unique_subareas = ctx.options.get("sst_subarea_boreholes", {})
    limiting_df = ctx.frames.get("limiting_df")
    sst_cl_x_axis_max = ctx.params.get("sst_cl_x_axis_max")
    # File-derived SST Chloride guidelines (Subarea / Depth Range / Cl Guideline),
    # read from the workbook by the loader's read_sst_guidelines step.
    sst_cl_guide_default_df = ctx.frames.get("sst_cl_guide_default_df")
    if sst_cl_guide_default_df is None:
        ctx.notify("No SST Chloride guideline block found in the workbook.", "warning", "sst_chloride_charts")
        sst_cl_guide_default_df = pd.DataFrame(columns=["Subarea", "Depth Range", "Cl Guideline"])

    figs = render_sst_profile_set(
        plot_config=plot_config,
        additional_guidelines=additional_guidelines,
        column="soluble_ions_chloride_mg_kg",
        df=soil_data_filtered,
        valid_subareas=ab_unique_subareas,
        config_label="Chloride",
        save_prefix="SST_CHLORIDE",
        save_name=lambda subarea: f"{subarea}.png",
        sst_guidelines=sst_cl_guide_default_df,
        sst_guideline_column="Cl Guideline",
        sst_units="mg/kg",
        fallback_guidelines=limiting_df,
        x_max=sst_cl_x_axis_max,
    )
    for key, fig in figs.items():
        ctx.charts[key] = _fig_to_data_uri(fig)
    return ctx