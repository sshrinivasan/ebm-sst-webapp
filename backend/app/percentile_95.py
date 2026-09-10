from .context import Context, InputValidationError
import base64
import io
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import PchipInterpolator
import numpy as np

percentile_headers = {
    'sample_id': 'Location',
    'depth_m': 'Depth (m)',
    'z': 'Z',
    'comments': 'Comments',
    'general_inorganics_ph': 'pH',
    'general_inorganics_ec_ds_m': 'EC (dS/m)',
    'general_inorganics_sar': 'SAR',
    'general_inorganics_saturation': 'Sat (%)',
    'soluble_ions_chloride_mg_kg': 'Cl (mg/kg)',
    'soluble_ions_sulphate_mg_kg': 'SO4 (mg/kg)',
    'soluble_ions_sodium_mg_kg': 'Na (mg/kg)',
    'soluble_ions_calcium_mg_kg': 'Ca (mg/kg)',
    'soluble_ions_magnesium_mg_kg': 'Mg (mg/kg)',
    'soluble_ions_potassium_mg_kg': 'K (mg/kg)',
 }

def _build_borehole_sa_df(soil_data_filtered: pd.DataFrame) -> pd.DataFrame:
    """Derive the default Subarea -> Boreholes mapping from the soil table."""
    if "subarea" in soil_data_filtered.columns:
        has_subareas = soil_data_filtered["subarea"].notna() & (
            soil_data_filtered["subarea"].astype(str).str.strip() != ""
        )
        has_subareas = bool(has_subareas.any())
    else:
        has_subareas = False

    if has_subareas:
        return (
            soil_data_filtered
            .dropna(subset=["subarea", "sample_id"])
            .assign(subarea=lambda df: df["subarea"].astype(str).str.strip())
            .query("subarea != ''")
            .groupby("subarea")["sample_id"]
            .apply(lambda values: ", ".join(sorted(values.astype(str).str.strip().dropna().unique())))
            .reset_index()
            .rename(columns={"subarea": "Subarea", "sample_id": "Boreholes"})
        )
    return pd.DataFrame(columns=["Subarea", "Boreholes"])


def _assignments_from_params(assignments) -> pd.DataFrame:
    """Convert the frontend's subarea_assignments param into a Subarea/Boreholes df.

    Validates that no borehole is assigned to more than one subarea (no overlap).
    """
    rows = []
    seen: set[str] = set()
    for item in assignments or []:
        subarea = str(item.get("subarea") or "").strip()
        boreholes = item.get("boreholes") or []
        if not subarea:
            continue
        cleaned = [str(b).strip() for b in boreholes if str(b).strip()]
        for b in cleaned:
            if b in seen:
                raise InputValidationError(
                    f"Borehole '{b}' is assigned to more than one subarea. "
                    "Each borehole can belong to only one subarea."
                )
            seen.add(b)
        rows.append({"Subarea": subarea, "Boreholes": ", ".join(sorted(cleaned))})
    return pd.DataFrame(rows, columns=["Subarea", "Boreholes"])


def _slugify(name: str) -> str:
    """Turn a subarea name into a safe, unique key suffix (lowercase, no spaces)."""
    return "".join(ch if ch.isalnum() else "_" for ch in str(name).strip().lower()).strip("_")


def _fig_to_data_uri(fig) -> str:
    """Serialize a matplotlib figure to a base64 PNG data URI and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")

def build_subarea_chloride_results(groups_with_subarea, chloride_reference_value):
    plt.ioff()

    # Group by 'subarea'
    grouped = groups_with_subarea.groupby("subarea")

    # Iterate over each subarea and select rows where soluble_ions_chloride_mg_kg > chloride_reference_value
    subsoil_mass_results_dict = {}
    vertical_mass_results_dict = {}
    stats_1_15_dict = {}
    outliers_1_15_dict = {}
    chloride_profile_dict = {}

    subarea_1_15_stats_headers = {
        "sample_id": "Location",
        "depth_m": "Interval",
        "z": "Depth",
        "soluble_ions_chloride_mg_kg": "Cl (mg/kg)",
        "general_inorganics_ec_ds_m": "EC (ds/m)",
        "general_inorganics_sar": "SAR"
    }
    group_df_display_headers = {
        "sample_id": "Location",
        "depth_m": "Depth (mbgs)",
        "z": "Z",
        "soluble_ions_chloride_mg_kg": "Cl (mg/kg)"
    }
    vertical_mass_display_headers = {
        "z_bin_split": "Depth Interval (mbgs)",
        "soluble_ions_chloride_mg_kg": "Avg Chloride (mg/kg)",
        "vertical_mass": "Vertical Mass (%)"
    }

    for subarea, group_df in grouped:
        group_df = group_df.copy()
        group_df["z"] = pd.to_numeric(group_df["z"], errors="coerce")
        group_df["soluble_ions_chloride_mg_kg"] = pd.to_numeric(group_df["soluble_ions_chloride_mg_kg"], errors="coerce")
        group_df["general_inorganics_ec_ds_m"] = pd.to_numeric(group_df["general_inorganics_ec_ds_m"], errors="coerce")
        group_df["general_inorganics_sar"] = pd.to_numeric(group_df["general_inorganics_sar"], errors="coerce")

        subsoil_mass_results_dict[subarea] = pd.DataFrame(columns=list(group_df_display_headers.values()))
        vertical_mass_results_dict[subarea] = pd.DataFrame(columns=list(vertical_mass_display_headers.values()))
        stats_1_15_dict[subarea] = pd.DataFrame(columns=list(subarea_1_15_stats_headers.values()))
        outliers_1_15_dict[subarea] = pd.DataFrame(columns=["Location", "Interval"])
        chloride_profile_dict[subarea] = None

        exceed_rows = group_df[
            (group_df["soluble_ions_chloride_mg_kg"] > chloride_reference_value)
            & group_df["z"].notna()
        ]
        if not exceed_rows.empty:
            # Get max z where Cl > 100 in each subarea
            max_z = exceed_rows["z"].max()
            # Bin group_df into equal intervals from 0 to int(max_z + 1)
            bins = np.linspace(0, int(max_z + 1), num=int(max_z + 1) + 1)

            # Remove samples where "z" is missing or more than the max_z interval
            group_df = group_df[group_df["z"].notna() & (group_df["z"] <= int(max_z + 1))]
            group_df = group_df.sort_values("z")

            # Bin them with 1 m increments, ignoring 0-1 m and including boundary depths in both adjacent bins.
            z_bin_rows = []
            for left, right in zip(bins[:-1], bins[1:]):
                if left == 0:
                    continue
                bin_df = group_df[(group_df["z"] >= left) & (group_df["z"] <= right)].copy()
                if not bin_df.empty:
                    bin_df["z_bin"] = f"{left:g} to {right:g}"
                    z_bin_rows.append(bin_df)

            # Average of each depth increment (1-2, 2-3 etc)
            if z_bin_rows:
                group_df_binned = pd.concat(z_bin_rows, ignore_index=True)
                chloride_bin_avg = group_df_binned.groupby("z_bin", sort=False)[["soluble_ions_chloride_mg_kg"]].mean()
            else:
                group_df_binned = pd.DataFrame(columns=list(group_df.columns) + ["z_bin"])
                chloride_bin_avg = pd.DataFrame(columns=["soluble_ions_chloride_mg_kg"])
                chloride_bin_avg.index.name = "z_bin"

            # Subsoil only: drop the 0-1 m interval, matching the binning above
            group_df_display = group_df.loc[
                group_df["z"] >= 1.0,
                ["sample_id", "depth_m", "z", "soluble_ions_chloride_mg_kg"],
            ]
            group_df_display = group_df_display.rename(columns=group_df_display_headers)

            # ---- First display table per subarea
            subsoil_mass_results_dict[subarea] = group_df_display

            # Get the data for the 1-1.5 interval
            group_df_1_1_5 = group_df[(group_df["z"] > 1.0) & (group_df["z"] < 1.5)]
            group_df_1_1_5 = group_df_1_1_5[["sample_id", "z", "depth_m", "soluble_ions_chloride_mg_kg", "general_inorganics_ec_ds_m", "general_inorganics_sar"]]

            if not group_df_1_1_5.empty:

                # Split depth_m by '-' to find outliers. depth_m can be numeric for point samples
                # or a string interval like "1-1.5".
                group_df_1_1_5_split = group_df_1_1_5.copy()
                depth_values = group_df_1_1_5_split["depth_m"].astype(str).str.strip()
                depth_split = depth_values.str.split("-", n=1, expand=True)

                group_df_1_1_5_split["depth_low"] = pd.to_numeric(depth_split[0], errors="coerce")
                # Assign depth_high as NaN if depth_split has only one column
                group_df_1_1_5_split["depth_high"] = pd.to_numeric(depth_split[1], errors="coerce") if depth_split.shape[1] > 1 else np.nan

                # Store the outliers
                group_df_1_1_5_outliers = group_df_1_1_5_split[
                    (pd.to_numeric(group_df_1_1_5_split['depth_low'], errors='coerce') < 1) |
                    (group_df_1_1_5_split['depth_high'].notnull() & (pd.to_numeric(group_df_1_1_5_split['depth_high'], errors='coerce') > 1.5))
                ]

                outliers_1_15_dict[subarea] = group_df_1_1_5_outliers[["sample_id", "depth_m"]].rename(columns=subarea_1_15_stats_headers)

                # Remove rows with depth_low < 1 or depth_high > 1.5 (check depth_high only if not None)
                group_df_1_1_5_split = group_df_1_1_5_split[
                    (pd.to_numeric(group_df_1_1_5_split['depth_low'], errors='coerce') >= 1) &
                    (
                        group_df_1_1_5_split['depth_high'].notnull() & (pd.to_numeric(group_df_1_1_5_split['depth_high'], errors='coerce') <= 1.5)
                        | group_df_1_1_5_split['depth_high'].isnull()
                    )
                ]

                # Add statistics as new rows to end of dataframe
                stats_rows = [
                    ["All Samples", None, "95th Percentile", round(group_df_1_1_5['soluble_ions_chloride_mg_kg'].quantile(0.95), 2), None, round(group_df_1_1_5['general_inorganics_sar'].quantile(0.95), 2)],
                    ["All Samples", None, "Average", None, round(group_df_1_1_5['general_inorganics_ec_ds_m'].mean(), 2), None],
                    ["Outliers removed", None, "95th Percentile", round(group_df_1_1_5_split['soluble_ions_chloride_mg_kg'].quantile(0.95), 2), None, round(group_df_1_1_5_split['general_inorganics_sar'].quantile(0.95), 2)],
                    ["Outliers removed", None, "Average", None, round(group_df_1_1_5_split['general_inorganics_ec_ds_m'].mean(), 2), None]
                ]

                # Append stats rows to group_df_1_1_5. Make sure you specofy "columns" parameters otherwise concat
                # appends extra new columns if you forget to specify columns parameter
                group_df_1_1_5 = pd.concat([group_df_1_1_5, pd.DataFrame(stats_rows, columns=group_df_1_1_5.columns)], ignore_index=True)

                group_df_1_1_5 = group_df_1_1_5.fillna("-")

                group_df_1_1_5 = group_df_1_1_5.rename(columns=subarea_1_15_stats_headers)

            # group_df_1_15 is empty
            else:
                # Build an empty dataframe with the right keys
                group_df_1_1_5 = pd.DataFrame(columns=subarea_1_15_stats_headers.keys())
                outliers_1_15_dict[subarea] = pd.DataFrame(columns=[["sample_id", "depth_m"]]).rename(columns=subarea_1_15_stats_headers)

            # Create a dataframe for the veritcal mass and average data
            vertical_mass = pd.DataFrame({
                "z_bin": chloride_bin_avg.index.tolist(),
                "soluble_ions_chloride_mg_kg": chloride_bin_avg['soluble_ions_chloride_mg_kg'].tolist(),
            })
            vertical_mass["vertical_mass"] = vertical_mass["soluble_ions_chloride_mg_kg"] * 100.0 / vertical_mass["soluble_ions_chloride_mg_kg"].sum()

            # Remove rows with NaN or None in any field
            vertical_mass = vertical_mass.dropna()

            # Formatting for display
            vertical_mass["z_bin_split"] = vertical_mass["z_bin"].astype(str)

            vertical_mass_display = vertical_mass[["z_bin_split", "soluble_ions_chloride_mg_kg", "vertical_mass"]].copy()
            # Create stats line for vertical_mass and add it to the dataframe
            vertical_mass_stats = ["Sum", round(vertical_mass["soluble_ions_chloride_mg_kg"].sum(), 2), round(vertical_mass["vertical_mass"].sum(), 2)]
            vertical_mass_display = pd.concat([vertical_mass_display, pd.DataFrame([vertical_mass_stats], columns=vertical_mass_display.columns)], ignore_index=True)
            vertical_mass_display = vertical_mass_display.round(2)

            vertical_mass_display = vertical_mass_display.rename(columns=vertical_mass_display_headers)

            vertical_mass_results_dict[subarea] = vertical_mass_display
            stats_1_15_dict[subarea] = group_df_1_1_5

            # --- See if this can be replaced by plot_profile
            # Chloride profile
            profile_type_map = {
                "Chloride (mg/kg)": "soluble_ions_chloride_mg_kg",
            }

            fig, ax = plt.subplots(figsize=(4, 6))

            subarea_chloride_samples = group_df["sample_id"].unique()
            for idx, (profile_type, colname) in enumerate(profile_type_map.items()):
                for sample in subarea_chloride_samples:
                    sample_data = group_df.loc[
                        group_df["sample_id"] == sample,
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

                    if len(x_data) > 2:
                        xnew = np.linspace(x_data.min(), x_data.max(), num=200, endpoint=True)

                        # Plot and interpolate the data
                        cspline = PchipInterpolator(x_data, y_data)
                        interp_plot = ax.plot(cspline(xnew), xnew, '-', label=sample)
                        ax.plot(y_data, x_data, 'o', color=interp_plot[0].get_color())
                    elif len(x_data) > 0:
                        ax.plot(y_data, x_data, 's', label=sample)

            ax.invert_yaxis()
            ax.set_ylim(group_df["z"].max(), 0)
            ax.axhline(y=1.5, linestyle="--", color="black", label="1.5 m")
            ax.axvline(x=chloride_reference_value, linestyle="--", color="red", label=f"{chloride_reference_value} mg/kg")
            ax.xaxis.set_label_position('top')
            # TODO: Why percent here?
            ax.set_xlabel("{0}".format(profile_type))
            ax.set_ylabel("Depth (mbgs)")
            ax.grid(which='major', color='#DDDDDD', linewidth=0.8)
            # Minor grid as well
            ax.grid(which='minor', color='#DDDDDD', linestyle=':', linewidth=0.8)
            ax.minorticks_on()
            # ax.set_xlim([0, None])
            plt.tight_layout()
            fig.legend(loc='upper left', bbox_to_anchor=(0, 0), ncol=4, frameon=False)
            # plt.show()

            # fig = plot_profile("soluble_ions_chloride_mg_kg", df=group_df, samples=subarea_chloride_samples)
            chloride_profile_dict[subarea] = fig

    return (
        subsoil_mass_results_dict,
        vertical_mass_results_dict,
        stats_1_15_dict,
        outliers_1_15_dict,
        chloride_profile_dict,
    )

def ninetyfifth_percentile(ctx: Context) -> Context:

    # TODO: Figure out whether this is needed
    run_subarea_workflow = True

    soil_data_filtered = ctx.frames["soil_data_filtered"]
    default_df = _build_borehole_sa_df(soil_data_filtered)

    # Use the user's subarea assignments when provided; otherwise fall back to
    # the auto-derived mapping from the workbook's subarea column.
    assignments = ctx.params.get("subarea_assignments")
    if assignments:
        borehole_sa_df = _assignments_from_params(assignments)
    else:
        borehole_sa_df = default_df

    # Expose the mapping to the frontend so the SubareaAssigner can be
    # pre-filled. Also keep it on the frame for the pipeline's serialization.
    ctx.frames["borehole_sa_df"] = borehole_sa_df
    ctx.options["borehole_sa_df"] = {
        "columns": list(borehole_sa_df.columns),
        "rows": borehole_sa_df.to_dict(orient="records"),
    }
    
    borehole_assignment_rows = []
    for _, row in borehole_sa_df.iterrows():
        subarea = str(row.get("Subarea", "")).strip()
        boreholes = str(row.get("Boreholes", "")).split(",")
        for borehole in boreholes:
            borehole = borehole.strip()
            if subarea and borehole:
                borehole_assignment_rows.append({"sample_id": borehole, "subarea": subarea})


    borehole_assignment_df = pd.DataFrame(borehole_assignment_rows, columns=["sample_id", "subarea"])
    groups_with_subarea = soil_data_filtered.merge(
        borehole_assignment_df,
        how="inner",
        on="sample_id",
        suffixes=("", "_from_assignment"),
    )
    groups_with_subarea["subarea"] = groups_with_subarea["subarea_from_assignment"]
    groups_with_subarea = groups_with_subarea.drop(columns=["subarea_from_assignment"])
    # Create a reverse mapping dictionary where the key is the cleaned database name, and the value is the display name
    groups_with_subarea_display = groups_with_subarea[percentile_headers.keys()]
    groups_with_subarea_display = groups_with_subarea_display.rename(columns=percentile_headers)

    ctx.frames["percentile_95_subarea_data"] = groups_with_subarea_display

    (
        subsoil_mass_results_dict,
        vertical_mass_results_dict,
        stats_1_15_dict,
        outliers_1_15_dict,
        chloride_profile_dict,
    ) = build_subarea_chloride_results(groups_with_subarea, ctx.params["chloride_guideline"])

    # Check that all the keys are the same
    if not (subsoil_mass_results_dict.keys() == vertical_mass_results_dict.keys() == stats_1_15_dict.keys() == outliers_1_15_dict.keys()):
        err_msg = (
            "Key mismatch detected among dictionaries:\n"
            f"subsoil_mass_results_dict.keys(): {set(subsoil_mass_results_dict.keys())}\n"
            f"vertical_mass_results_dict.keys(): {set(vertical_mass_results_dict.keys())}\n"
            f"stats_1_15_dict.keys(): {set(stats_1_15_dict.keys())}\n"
            f"outliers_1_15_dict.keys(): {set(outliers_1_15_dict.keys())}"

        )
        raise ValueError(err_msg)

    selectable_subareas = list(subsoil_mass_results_dict.keys())

    _empty_subsoil_mass_df = pd.DataFrame(columns=["Location", "Depth (mbgs)", "Z", "Cl (mg/kg)"])
    _empty_vertical_mass_df = pd.DataFrame(columns=["Depth Interval (mbgs)", "Avg Chloride (mg/kg)", "Vertical Mass (%)"])
    _empty_stats_df = pd.DataFrame(columns=["Location", "Interval", "Depth", "Cl (mg/kg)", "EC (ds/m)", "SAR"])
    _empty_outliers_df = pd.DataFrame(columns=["Location", "Interval"])

    # Map slug -> display name so the frontend can label subarea tabs correctly
    # (the slug is used in output keys; the display name is what the user entered).
    ctx.options["p95_subareas"] = {
        _slugify(subarea): subarea for subarea in selectable_subareas
    }

    for subarea in selectable_subareas:
        selected_subsoil_mass_df = subsoil_mass_results_dict.get(subarea, _empty_subsoil_mass_df).round(2)
        selected_vertical_mass_df = vertical_mass_results_dict.get(subarea, _empty_vertical_mass_df).round(2)
        selected_stats_df = stats_1_15_dict.get(subarea, _empty_stats_df).round(2)
        outliers_df = outliers_1_15_dict.get(subarea, _empty_outliers_df).round(2)
        chloride_profile = chloride_profile_dict.get(subarea, None)

        # Distinguish per-subarea outputs with a slugified key prefix.
        key = _slugify(subarea)
        ctx.frames[f"p95_subsoil_mass_{key}"] = selected_subsoil_mass_df
        ctx.frames[f"p95_vertical_mass_{key}"] = selected_vertical_mass_df
        ctx.frames[f"p95_stats_{key}"] = selected_stats_df
        ctx.frames[f"p95_outliers_{key}"] = outliers_df
        if chloride_profile is not None:
            ctx.charts[f"p95_chloride_profile_{key}"] = _fig_to_data_uri(chloride_profile)

    return ctx