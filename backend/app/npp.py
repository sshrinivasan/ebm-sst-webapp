"""NPP (Naturally Present Parameters) sample-selection workflow.

Given the cleaned soil table, produce:
  - the NPP-eligible subset (samples with sulphate data) for display
  - two multiselect option lists for the UI:
      unique_bg_sample_ids     -> Background-flagged samples with sulphate data
      unique_all_sample_ids    -> every sample id with sulphate data
  - the final `npp_samples` list = background selection + near-APEC selection,
    which downstream workflows (e.g. SST exceedances) use to suppress EC/SAR
    exceedances in the 0-1.5 m zone.

A sample cannot be selected as both an NPP background sample and an NPP
near-APEC sample — overlapping selections raise an InputValidationError that
surfaces in the webapp as a user-facing error.
"""
from __future__ import annotations

from collections import OrderedDict

import base64
import io
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import PchipInterpolator
from .context import Context, InputValidationError

# Background APEC labels (same set used by the TDS workflow).
background_apec_labels = ["Background", "APEC Background", "BKGD"]

# Columns surfaced in the NPP selected-data table (cleaned snake_case names).
npp_columns = [
    "sample_id", "depth_m", "z", "apec", "general_inorganics_ph",
    "general_inorganics_ec_ds_m", "general_inorganics_sar",
    "general_inorganics_saturation",
    "soluble_ions_carbonate_mg_l", "soluble_ions_bicarbonate_mg_l",
    "soluble_ions_chloride_mg_kg", "soluble_ions_sulphate_mg_kg",
    "soluble_ions_sodium_mg_kg", "soluble_ions_calcium_mg_kg",
    "soluble_ions_magnesium_mg_kg", "soluble_ions_potassium_mg_kg",
    "soluble_ions_carbonate_mg_kg", "soluble_ions_bicarbonate_mg_kg",
]

def _fig_to_data_uri(fig) -> str:
    """Serialize a matplotlib figure to a base64 PNG data URI and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def render_npp_profile(df, samples) -> plt.Figure:
    """Render the NPP vertical profile (Sulphate vs depth) and return the figure."""
    profile_type_map = {
        "Sulphate": "soluble_ions_sulphate_mg_kg",
        # "Chloride": "soluble_ions_chloride_mg_kg",
    }

    fig, ax = plt.subplots(figsize=(4, 6))

    for _idx, (profile_type, colname) in enumerate(profile_type_map.items()):
        for sample in samples:
            sample_data = df.loc[
                df["sample_id"] == sample, ["z", colname]
            ].apply(pd.to_numeric, errors="coerce").dropna()
            x_data = sample_data["z"].to_numpy()
            y_data = sample_data[colname].to_numpy()

            if len(x_data) > 1:
                # Sort x_data and rearrange y_data accordingly
                sorted_indices = np.argsort(x_data)
                x_data_sorted = np.array(x_data)[sorted_indices]
                y_data_sorted = np.array(y_data)[sorted_indices]

                xnew = np.linspace(x_data.min(), x_data.max(), num=200, endpoint=True)

                # Plot and interpolate the data
                cspline = PchipInterpolator(x_data_sorted, y_data_sorted)
                interp_plot = ax.plot(cspline(xnew), xnew, '-', label=sample)
                ax.plot(y_data, x_data, 'o', color=interp_plot[0].get_color())
            else:
                ax.plot(y_data, x_data, 's', label=sample)

    ax.invert_yaxis()
    ax.set_ylim(top=0)
    ax.axhline(y=1.0, linestyle="--", color="black", label="1.0 m")
    ax.xaxis.set_label_position('top')
    ax.set_xlabel("{0} (mg/kg)".format(profile_type))
    ax.set_ylabel("Depth (mbgs)")
    ax.grid(which='major', color='#DDDDDD', linewidth=0.8)
    # Minor grid as well
    ax.grid(which='minor', color='#DDDDDD', linestyle=':', linewidth=0.8)
    ax.minorticks_on()
    ax.set_xlim([0, None])
    plt.tight_layout()
    fig.legend(loc='upper left', bbox_to_anchor=(0, 0), ncol=4, frameon=False)
    return fig


def seed_npp_options(ctx: Context) -> Context:
    """Seed the NPP multiselect option lists (available at upload, before any run).

    Mirrors how percentile_95 seeds borehole_sa_df: called from the upload
    endpoint so the frontend selectors are populated immediately.
    """
    soil_data_filtered = ctx.frames["soil_data_filtered"]

    # Source all samples (not just Background-flagged ones) so the near-APEC NPP
    # selector can resolve. The background/near-APEC split is applied later via
    # the two selectors.
    npp_sulphate_notnull_df = soil_data_filtered[
        soil_data_filtered["soluble_ions_sulphate_mg_kg"].notnull()
    ]

    # Background selector: only Background-flagged samples that have sulphate data.
    unique_bg_sample_ids = (
        npp_sulphate_notnull_df.loc[
            npp_sulphate_notnull_df["apec"].isin(background_apec_labels), "sample_id"
        ]
        .dropna()
        .unique()
        .tolist()
    )
    unique_all_sample_ids = soil_data_filtered["sample_id"].dropna().unique().tolist()

    ctx.options["unique_bg_sample_ids"] = [str(s) for s in unique_bg_sample_ids]
    ctx.options["unique_all_sample_ids"] = [str(s) for s in unique_all_sample_ids]
    return ctx


def npp_analysis(ctx: Context) -> Context:
    ctx = seed_npp_options(ctx)
    soil_data_filtered = ctx.frames["soil_data_filtered"]

    npp_sulphate_notnull_df = soil_data_filtered[
        soil_data_filtered["soluble_ions_sulphate_mg_kg"].notnull()
    ].round(2)
    filtered_npp_df = npp_sulphate_notnull_df.loc[:, npp_columns]

    unique_bg_sample_ids = ctx.options["unique_bg_sample_ids"]
    unique_all_sample_ids = ctx.options["unique_all_sample_ids"]

    # Resolve the user's selections. Background defaults to all background
    # samples; near-APEC stays EMPTY until the user picks samples (so the
    # default run never overlaps).
    npp_bg_samples = ctx.params.get("npp_bg_samples") or unique_bg_sample_ids
    npp_near_apec_samples = ctx.params.get("npp_near_apec_samples") or []

    # Combine the background and near-APEC NPP selections into a single sample list.
    # A borehole must be classified as one or the other, never both, so overlap is
    # an input error.
    _npp_bg_selected = [str(s).strip() for s in npp_bg_samples if str(s).strip()]
    _npp_near_apec_selected = [str(s).strip() for s in npp_near_apec_samples if str(s).strip()]

    _npp_overlap = [s for s in _npp_bg_selected if s in set(_npp_near_apec_selected)]
    if _npp_overlap:
        raise InputValidationError(
            "A sample cannot be selected as both an NPP background sample and an "
            "NPP near-APEC sample. Overlapping samples: "
            + ", ".join(sorted(set(_npp_overlap)))
        )

    npp_samples = list(OrderedDict.fromkeys(_npp_bg_selected + _npp_near_apec_selected))

    # Expose inputs + intermediate frames on the Context so downstream workflows
    # (e.g. npp_sulphate_tests) can reuse them.
    ctx.options["npp_bg_samples"] = _npp_bg_selected
    ctx.options["npp_near_apec_samples"] = _npp_near_apec_selected
    ctx.options["npp_samples"] = npp_samples
    ctx.frames["filtered_npp_df"] = filtered_npp_df

    ctx.frames["npp_selected_data"] = _build_npp_display_df(filtered_npp_df, npp_samples)
    
    # Profile graphs: render the Sulphate vertical profile for the selected
    # samples and store it as a PNG data URI, matching the chart pattern used by
    # percentile_95 (ctx.charts[name] -> data URI).
    npp_profile_fig = render_npp_profile(filtered_npp_df, npp_samples)
    ctx.charts["npp_profile"] = _fig_to_data_uri(npp_profile_fig)

    return ctx


def _build_npp_display_df(filtered_npp_df: pd.DataFrame, npp_samples: list[str]) -> pd.DataFrame:
    """Display table restricted to the selected NPP samples (user's selection).

    The display shows the rows that belong to the chosen background + near-APEC
    samples: the two multiselects are interpreted as a selection filter for the
    NPP dataset shown to the user.
    """
    from .loader import cleaned_name_to_excel_header_map

    selected = filtered_npp_df[
        filtered_npp_df["sample_id"].astype(str).str.strip().isin(set(npp_samples))
    ]
    display = selected.rename(columns=cleaned_name_to_excel_header_map)
    return display.where(pd.notna(display), "")


def npp_sulphate_tests(ctx: Context) -> Context:
    # Read the resolved NPP selections + filtered frame from the Context (set by
    # npp_analysis) so this step stays a ctx->ctx function.
    npp_bg_samples = ctx.options["npp_bg_samples"]
    npp_near_apec_samples = ctx.options["npp_near_apec_samples"]
    npp_samples = ctx.options["npp_samples"]
    filtered_npp_df = ctx.frames["filtered_npp_df"]

    # Groundwater measurement type (Measured / Inferred), practitioner-notes
    # confirmation, and the shared water-table depth, from the params.
    gw_measurement_type = ctx.params.get("gw_measurement_type") or "Measured"
    npp_practitioner_notes = bool(ctx.params.get("npp_practitioner_notes"))
    input_water_table_depth = ctx.params.get("input_water_table_depth")

    # --------
    # NPP Sulphate profile Tests
    borehole_npp_sulphate_data = []

    # Label each borehole by which selector it came from rather than by its apec value
    _npp_bg_set = {str(s).strip() for s in (npp_bg_samples or [])}
    _npp_near_apec_set = {str(s).strip() for s in (npp_near_apec_samples or [])}

    # Loop over the boreholes selected in the background + near-APEC NPP sample selectors
    for grp in filtered_npp_df[filtered_npp_df["sample_id"].isin(npp_samples)].groupby("sample_id"):
        group_df = grp[1].copy()
        group_df["z"] = pd.to_numeric(group_df["z"], errors="coerce")
        group_df["soluble_ions_sulphate_mg_kg"] = pd.to_numeric(
            group_df["soluble_ions_sulphate_mg_kg"], errors="coerce"
        )
        group_df = group_df.dropna(subset=["z", "soluble_ions_sulphate_mg_kg"])

        if len(group_df) < 3:
            print("Skipping sample {0}, not enough samples".format(grp[0]))
            continue

        group_df_sorted = group_df.sort_values("z")

        # Test A-1
        # Shallowest depth. Should be <=0.3m
        shallowest_depth_row = group_df_sorted.iloc[0]
        shallowest_sulphate = shallowest_depth_row["soluble_ions_sulphate_mg_kg"]
        shallowest_z = shallowest_depth_row["z"]
        if shallowest_z > 0.3:
            shallowest_sulphate = "NA"

        # Next Shallowest depth. Should be < 1.0m
        next_shallowest_depth_row = group_df_sorted.iloc[1]
        next_shallowest_sulphate = next_shallowest_depth_row["soluble_ions_sulphate_mg_kg"]
        next_shallowest_z = next_shallowest_depth_row["z"]
        if next_shallowest_z > 1.0:
            next_shallowest_sulphate = "NA"

        # Identifies the maximum sulphate concentration for all samples <= 0.3 m. If no samples are <= 0.3 m, should return error
        mask_0_03 = group_df["z"] <= 0.3
        highest_sulphate_0_03_row = group_df[mask_0_03].loc[group_df[mask_0_03]["soluble_ions_sulphate_mg_kg"].idxmax()] if not group_df[mask_0_03].empty else None

        if highest_sulphate_0_03_row is not None:
            highest_sulphate_0_03_sulphate = highest_sulphate_0_03_row["soluble_ions_sulphate_mg_kg"]
        else:
            highest_sulphate_0_03_sulphate = "NA"
        # ----

        # Identifies the sulphate concentration in the shallowest sample that is >0.3 m and less than or equal to 1.0 m. If there are no samples in this range = error
        mask_0_3_to_1 = (group_df["z"] > 0.3) & (group_df["z"] <= 1.0)
        group_df_0_3_to_1_sorted = group_df[mask_0_3_to_1].sort_values("z")
        highest_sulphate_0_3_to_1_row = group_df_0_3_to_1_sorted.iloc[0] if not group_df_0_3_to_1_sorted.empty else None
        if highest_sulphate_0_3_to_1_row is not None:
            shallowest_sulphate_0_3_to_1_sulphate = highest_sulphate_0_3_to_1_row["soluble_ions_sulphate_mg_kg"]
        else:
            shallowest_sulphate_0_3_to_1_sulphate = "NA"
        
            
        # Closest to 1.0m, but should be between 1.0-1.5m
        positive_z = group_df[group_df["z"] > 1.0]
        if positive_z.empty:
            print("Skipping {0}: Cannot find sulphate data deeper than 1.0m".format(grp[0]))
            continue
        closest_one_row = positive_z.loc[(positive_z["z"] - 1).abs().idxmin()]
        closest_one_sulphate = closest_one_row["soluble_ions_sulphate_mg_kg"]
        closest_one_z = closest_one_row["z"]
        if (closest_one_z < 1.0) or (closest_one_z > 1.5):
            closest_one_sulphate = "NA"


        # Highest soluble_ions_sulphate_mg_kg where "z" is between 0 and 1.0
        mask_0_1 = (group_df["z"] > 0) & (group_df["z"] <= 1.0)
        highest_sulphate_0_1_row = group_df[mask_0_1].loc[group_df[mask_0_1]["soluble_ions_sulphate_mg_kg"].idxmax()] if not group_df[mask_0_1].empty else None
        
        if highest_sulphate_0_1_row is not None:
            highest_sulphate_0_1_sulphate = highest_sulphate_0_1_row["soluble_ions_sulphate_mg_kg"]
        else:
            highest_sulphate_0_1_sulphate = "NA"
        # ----
        
        # Highest soluble_ions_sulphate_mg_kg where "z" is between 1 and 4.5
        mask_1_45 = (group_df["z"] > 1) & (group_df["z"] < 4.5)
        highest_sulphate_1_45_row = group_df[mask_1_45].loc[group_df[mask_1_45]["soluble_ions_sulphate_mg_kg"].idxmax()] if not group_df[mask_1_45].empty else None
        
        if highest_sulphate_1_45_row is not None:
            highest_sulphate_1_45_sulphate = highest_sulphate_1_45_row["soluble_ions_sulphate_mg_kg"]
        else:
            highest_sulphate_1_45_sulphate = "NA"
        # ----

        # Minimum soluble_ions_sulphate_mg_kg where "z" is between 2.5 and 4.5
        mask_2_45 = (group_df["z"] >= 2.5) & (group_df["z"] <= 4.5)
        lowest_sulphate_2_45_row = group_df[mask_2_45].loc[group_df[mask_2_45]["soluble_ions_sulphate_mg_kg"].idxmin()] if not group_df[mask_2_45].empty else None
        
        if lowest_sulphate_2_45_row is not None:
            lowest_sulphate_2_45_sulphate = lowest_sulphate_2_45_row["soluble_ions_sulphate_mg_kg"]
        else:
            lowest_sulphate_2_45_sulphate = "NA"
        # ----

        borehole_npp_sulphate_data.append([
            grp[0],
            "Background" if str(grp[0]).strip() in _npp_bg_set
            else ("Near-APEC" if str(grp[0]).strip() in _npp_near_apec_set else ""),
            shallowest_sulphate, 
            next_shallowest_sulphate, 
            highest_sulphate_0_03_sulphate,
            shallowest_sulphate_0_3_to_1_sulphate,
            closest_one_sulphate, 
            highest_sulphate_0_1_sulphate, 
            highest_sulphate_1_45_sulphate, 
            lowest_sulphate_2_45_sulphate,
            int(((group_df["z"] >= 0) & (group_df["z"] <= 4.5)).sum())])
        
    borehole_npp_sulphate_ref = pd.DataFrame(borehole_npp_sulphate_data, 
        columns=[
            "sample_id",
            "area",
            "shallowest_sulphate",
            "next_shallowest_sulphate",
            "highest_sulphate_0_03_sulphate",
            "shallowest_sulphate_0_3_to_1_sulphate",
            "closest_one_sulphate",
            "highest_sulphate_0_1_sulphate",
            "highest_sulphate_1_45_sulphate",
            "lowest_sulphate_2_45_sulphate",
            "sample_count"
        ])

    borehole_npp_sulphate_headers = [
        "Location",
        "Profile Type",
        "Shallowest sample (<= 0.3m)",
        "Next shallowest sample (<= 1m",
        "Max near surface (<=0.3m)",
        "Shallowest sample (>0.3-1m)",
        "Mid(1-1.5m)",
        "Max(0-1m)",
        "Max(>1-4.5m)",
        "Min BL(2.5-4.5m)",
        "Sample Count(0-4.5m)"
    ]
    
    borehole_npp_sulphate_ref_display = borehole_npp_sulphate_ref.copy()
    borehole_npp_sulphate_ref_display.columns = borehole_npp_sulphate_headers

    # --------
    # NPP Test statistics
    npp_test_metrics = pd.DataFrame()

    headers = [
        "Location",
        "Profile Type",
        "Test A: Part 1 (mg/kg)", "Test A: Part 1 (%)",
        "Test A: Part 2 (mg/kg)", "Test A: Part 2 (%)",
        "Test A: Part 3 (mg/kg)", "Test A: Part 3 (%)",
        "Test B (mg/kg)", "Test B (%)",
        "Test C (mg/kg)", "Test C (%)",
    ]

    npp_test_metrics["sample_id"] = borehole_npp_sulphate_ref["sample_id"]
    npp_test_metrics["area"] = borehole_npp_sulphate_ref["area"]

    # The per-depth metric columns can carry "NA" strings (when a depth window has
    # no samples). Coerce to numeric so "NA" -> NaN and the arithmetic below stays
    # numeric (NaN propagates) instead of raising TypeError on "str" - "str".
    _metric_metric_cols = [
        "shallowest_sulphate",
        "next_shallowest_sulphate",
        "highest_sulphate_0_03_sulphate",
        "shallowest_sulphate_0_3_to_1_sulphate",
        "closest_one_sulphate",
        "highest_sulphate_0_1_sulphate",
        "highest_sulphate_1_45_sulphate",
        "lowest_sulphate_2_45_sulphate",
    ]
    _metrics = borehole_npp_sulphate_ref[_metric_metric_cols].apply(
        pd.to_numeric, errors="coerce"
    )

    npp_test_metrics["testA_1"] = (_metrics["shallowest_sulphate"] - _metrics["closest_one_sulphate"]).abs()
    npp_test_metrics["testA_1_pct"] = 100.0 * (_metrics["shallowest_sulphate"] - _metrics["closest_one_sulphate"]).abs() / _metrics["shallowest_sulphate"]

    npp_test_metrics["testA_2"] = (_metrics["next_shallowest_sulphate"] - _metrics["shallowest_sulphate"]).abs()
    npp_test_metrics["testA_2_pct"] = 100.0 * (_metrics["next_shallowest_sulphate"] - _metrics["shallowest_sulphate"]).abs() / _metrics["shallowest_sulphate"]

    npp_test_metrics["testA_3"] = (_metrics["highest_sulphate_0_03_sulphate"] - _metrics["shallowest_sulphate_0_3_to_1_sulphate"]).abs()
    npp_test_metrics["testA_3_pct"] = 100.0 * (_metrics["highest_sulphate_0_03_sulphate"] - _metrics["shallowest_sulphate_0_3_to_1_sulphate"]).abs() / _metrics["shallowest_sulphate_0_3_to_1_sulphate"]

    npp_test_metrics["testB"] = (_metrics["highest_sulphate_0_1_sulphate"] - _metrics["highest_sulphate_1_45_sulphate"]).abs()
    npp_test_metrics["testB_pct"] = 100.0 * (_metrics["highest_sulphate_0_1_sulphate"] - _metrics["highest_sulphate_1_45_sulphate"]).abs() / _metrics["highest_sulphate_0_1_sulphate"]

    npp_test_metrics["testC"] = (_metrics["lowest_sulphate_2_45_sulphate"] - _metrics["shallowest_sulphate"]).abs()
    npp_test_metrics["testC_pct"] = 100.0 * (_metrics["lowest_sulphate_2_45_sulphate"] - _metrics["shallowest_sulphate"]).abs() / _metrics["shallowest_sulphate"]

    npp_test_metrics.columns = headers
    npp_test_metrics = npp_test_metrics.round(2)

    
    # --------
    # NPP Test results (sulphate profile interprettion)
    npp_test_results = pd.DataFrame()

    npp_test_results["sample_id"] = borehole_npp_sulphate_ref["sample_id"]
    npp_test_results["area"] = borehole_npp_sulphate_ref["area"]

    # Metrics can carry the string "NA" when a depth window has no samples.
    # Coerce to numeric so those become NaN; any comparison against NaN is False -> "Fail".
    npp_metric_cols = [
        "shallowest_sulphate",
        "next_shallowest_sulphate",
        "highest_sulphate_0_03_sulphate",
        "shallowest_sulphate_0_3_to_1_sulphate",
        "closest_one_sulphate",
        "highest_sulphate_0_1_sulphate",
        "highest_sulphate_1_45_sulphate",
        "lowest_sulphate_2_45_sulphate",
    ]
    npp_metrics_numeric = borehole_npp_sulphate_ref[npp_metric_cols].apply(pd.to_numeric, errors="coerce")

    npp_test_results["TestA_1"] = (npp_metrics_numeric["shallowest_sulphate"] < npp_metrics_numeric["closest_one_sulphate"]).map(lambda x: "Pass" if x else "Fail")
    npp_test_results["TestA_2"] = (npp_metrics_numeric["next_shallowest_sulphate"] > npp_metrics_numeric["shallowest_sulphate"]).map(lambda x: "Pass" if x else "Fail")
    npp_test_results["TestA_3"] = (npp_metrics_numeric["highest_sulphate_0_03_sulphate"] < npp_metrics_numeric["shallowest_sulphate_0_3_to_1_sulphate"]).map(lambda x: "Pass" if x else "Fail")

    # npp_test_results["TestA_combined"] = Pass if both npp_test_results["TestA_1"] and npp_test_results["TestA_2"] are Pass, else Fail
    npp_test_results["TestA_combined"] = (
        (npp_test_results["TestA_1"] == "Pass")
        & (npp_test_results["TestA_2"] == "Pass")
        & (npp_test_results["TestA_3"] == "Pass")

    ).map(lambda x: "Pass" if x else "Fail")

    npp_test_results["TestB"] = (npp_metrics_numeric["highest_sulphate_1_45_sulphate"] > npp_metrics_numeric["highest_sulphate_0_1_sulphate"]).map(lambda x: "Pass" if x else "Fail")
    npp_test_results["TestC"] = (npp_metrics_numeric["shallowest_sulphate"] < npp_metrics_numeric["lowest_sulphate_2_45_sulphate"]).map(lambda x: "Pass" if x else "Fail")


    def outcome_rule(row):
        if row["TestA_combined"] == "Fail":
            return "Upwards"
        elif row["TestA_combined"] == "Pass" and row["TestB"] == "Pass" and row["TestC"] == "Pass":
            return "Definite Downward"
        else:
            return "Probable Downward"

    npp_test_results["profile_interpretation"] = npp_test_results.apply(outcome_rule, axis=1)

    # Explicit internal name -> display name mapping, so renaming is not position dependent
    npp_test_results_header_map = {
        "sample_id": "Location",
        "area": "Profile Type",
        "TestA_1": "Test A: P1",
        "TestA_2": "Test A: P2",
        "TestA_3": "Test A: P3",
        "TestA_combined": "Test A: Combined",
        "TestB": "Test B",
        "TestC": "Test C",
        "profile_interpretation": "Profile Interpretation",
    }
    npp_test_results = npp_test_results.rename(columns=npp_test_results_header_map)


    # --------
    # Site result

    # Site-level NPP suitability, evaluated across the boreholes in npp_test_results.
    #   1. Any "Upwards" profile among Near-APEC boreholes -> Fail
    #   2. Else all "Definite Downward" (all boreholes)    -> Pass
    #   3. Else water table gate: >= 2 m if Measured, >= 3 m if Inferred
    _profile_interpretations = npp_test_results["Profile Interpretation"].astype(str).str.strip()

    # Only near-APEC profiles can disqualify the site on an upward gradient
    _near_apec_interpretations = _profile_interpretations[
        npp_test_results["Profile Type"].astype(str).str.strip() == "Near-APEC"
    ]

    _water_table_threshold = {"Measured": 2.0, "Inferred": 3.0}.get(gw_measurement_type)

    # Minimum sample coverage: at least 3 Background and 1 Near-APEC borehole
    _profile_types = npp_test_results["Profile Type"].astype(str).str.strip()
    _n_background = int((_profile_types == "Background").sum())
    _n_near_apec = int((_profile_types == "Near-APEC").sum())
    _has_minimum_samples = _n_background >= 3 and _n_near_apec >= 1

    if _profile_interpretations.empty:
        # No NPP samples selected, so there is nothing to evaluate
        npp_suitable = "Incomplete"
    elif not _has_minimum_samples:
        # Insufficient coverage to interpret the site
        npp_suitable = "Incomplete"
    elif (_near_apec_interpretations == "Upwards").any():
        npp_suitable = "Fail"
    elif (_profile_interpretations == "Definite Downward").all():
        npp_suitable = "Pass"
    elif _water_table_threshold is None or input_water_table_depth is None:
        # The water table gate cannot be applied without both a measurement type and a depth
        npp_suitable = "Incomplete"
    else:
        npp_suitable = "Pass" if float(input_water_table_depth) >= _water_table_threshold else "Fail"

    # Practitioner notes must be confirmed before a result can be reported
    if not npp_practitioner_notes:
        npp_suitable = "Incomplete"

    # --------
    # Marginal boreholes justification
    marginal_results = []
    
    # List boreholes with marginal Test A Part 1

    # Find all boreholes that have failed 'Test A: P1' in npp_test_results
    test_a_p1_failed = npp_test_results[
        npp_test_results["Test A: P1"].str.strip().str.lower() == "fail"
    ]
    locations = test_a_p1_failed["Location"]

    # Marginal test boreholes (Test A: Part 1)
    marginal_testA1 = npp_test_metrics[
        npp_test_metrics["Location"].isin(locations)
        & ((npp_test_metrics["Test A: Part 1 (mg/kg)"] < 50) | (npp_test_metrics["Test A: Part 1 (%)"] < 10))
    ]
    if marginal_testA1 is not None:
        marginal_results.append({"Description": "Test A P1 Fails <=50 mg/kg or <=10%", "Locations": marginal_testA1["Location"].to_list()})
        
    # ---- List boreholes with marginal Test A Part 2
    # Find all boreholes that have failed 'Test A: P2' in npp_test_results
    test_a_p2_failed = npp_test_results[
        npp_test_results["Test A: P2"].str.strip().str.lower() == "fail"
    ]
    locations = test_a_p2_failed["Location"]

    # Marginal test boreholes (Test A: Part 2)
    marginal_testA2 = npp_test_metrics[
        npp_test_metrics["Location"].isin(locations)
        & ((npp_test_metrics["Test A: Part 2 (mg/kg)"] < 50) | (npp_test_metrics["Test A: Part 2 (%)"] < 10))
    ]
    if marginal_testA2 is not None:
        marginal_results.append({"Description": "Test A P2 Fails <=50 mg/kg or <=10%", "Locations": marginal_testA2["Location"].to_list()})

    # ---- List boreholes with marginal Test A Part 3
    # Find all boreholes that have failed 'Test A: P3' in npp_test_results
    test_a_p3_failed = npp_test_results[
        npp_test_results["Test A: P3"].str.strip().str.lower() == "fail"
    ]
    locations = test_a_p3_failed["Location"]

    # Marginal test boreholes (Test A: Part 3)
    marginal_testA3 = npp_test_metrics[
        npp_test_metrics["Location"].isin(locations)
        & ((npp_test_metrics["Test A: Part 3 (mg/kg)"] < 50) | (npp_test_metrics["Test A: Part 3 (%)"] < 10))
    ]
    if marginal_testA3 is not None:
        marginal_results.append({"Description": "Test A P3 Fails <=50 mg/kg or <=10%", "Locations": marginal_testA3["Location"].to_list()})


    # ---- List boreholes with marginal Test B
    # Find all boreholes that have failed 'Test B' in npp_test_results
    test_b_failed = npp_test_results[
        npp_test_results["Test B"].str.strip().str.lower() == "fail"
    ]
    locations = test_b_failed["Location"]

    # Marginal test boreholes (Test B)
    marginal_testB = npp_test_metrics[
        npp_test_metrics["Location"].isin(locations)
        & ((npp_test_metrics["Test B (mg/kg)"] < 100) | (npp_test_metrics["Test B (%)"] < 10))
    ]
    if marginal_testB is not None:
        marginal_results.append({"Description": "Test B Fails <=100 mg/kg or <=10%", "Locations": marginal_testB["Location"].to_list()})

    # ---- List boreholes with marginal Test C
    # Find all boreholes that have failed 'Test C' in npp_test_results
    test_c_failed = npp_test_results[
        npp_test_results["Test C"].str.strip().str.lower() == "fail"
    ]
    locations = test_c_failed["Location"]

    # Marginal test boreholes (Test C)
    marginal_testC = npp_test_metrics[
        npp_test_metrics["Location"].isin(locations)
        & ((npp_test_metrics["Test C (mg/kg)"] < 100) | (npp_test_metrics["Test C (%)"] < 10))
    ]
    if marginal_testC is not None:
        marginal_results.append({"Description": "Test C Fails <=100 mg/kg or <=10%", "Locations": marginal_testC["Location"].to_list()})

    # Sample count < 8
    marginal_sample_count_locations = borehole_npp_sulphate_ref[borehole_npp_sulphate_ref['sample_count'] < 8]['sample_id'].to_list()
    if marginal_sample_count_locations is not None:
        marginal_results.append({"Description": "Sample count < 8", "Locations": marginal_sample_count_locations})

    marginal_borehole_df = pd.DataFrame(marginal_results)
    
    # Store the results on the Context so the pipeline can serialize them.
    ctx.frames["npp_numerical_ref_info"] = borehole_npp_sulphate_ref_display
    ctx.frames["npp_test_statistics"] = npp_test_metrics
    ctx.frames["npp_test_results"] = npp_test_results
    ctx.frames["npp_marginal_results"] = marginal_borehole_df

    # Site-level suitability for the NPP banner ("Incomplete" / "Pass" / "Fail").
    ctx.options["npp_suitable"] = npp_suitable

    return ctx
