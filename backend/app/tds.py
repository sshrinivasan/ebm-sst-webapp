from .context import Context, InputValidationError
import pandas as pd

# Create a reverse mapping dictionary where the key is the cleaned database name, and the value is the display name
tds_header_columns = {
    'sample_id': "Location",
    'depth_m': "Depth (m)",
    'z': "Z",
    'comments': "Comments",
    'general_inorganics_ph': "pH",
    'general_inorganics_ec_ds_m': "EC",
    'general_inorganics_sar': "SAR",
    'general_inorganics_saturation': "Sat (%)",
    'soluble_ions_chloride_mg_kg': "Cl (mg/kg)",
    'soluble_ions_sulphate_mg_kg': "SO4 (mg/kg)",
    'soluble_ions_carbonate_mg_kg': "CO3 (mg/kg)",
    'soluble_ions_bicarbonate_mg_kg': "HCO3 (mg/kg)",
}

# SCARG rating thresholds. Defined once here and reused by the categorization
# cells below and by the background statistics / appendix workflow.

# Topsoil EC (dS/m)
ec_top_bins = [-float("inf"), 2, 4, 8, float("inf")]
ec_top_labels = ["Good", "Fair", "Poor", "Unsuitable"]

# Subsoil EC (dS/m)
ec_sub_bins = [-float("inf"), 3, 5, 10, float("inf")]
ec_sub_labels = ["Good", "Fair", "Poor", "Unsuitable"]

def _resolve_depth_window(ctx: Context) -> tuple[float | None, float | None]:
    """Return (upper_limit, lower_limit) for the TDS window from current params."""
    p = ctx.params
    water_table_depth = pd.to_numeric(p.get("input_water_table_depth"), errors="coerce")
    upper_limit = pd.to_numeric(p.get("upper_depth_limit"), errors="coerce")
    lower_limit = pd.to_numeric(p.get("lower_depth_limit"), errors="coerce")

    has_water_table_depth = pd.notna(water_table_depth) and water_table_depth > 0
    has_depth_range = pd.notna(upper_limit) and pd.notna(lower_limit) and lower_limit > upper_limit

    if p.get("use_custom_wt_depths"):
        if not has_depth_range:
            raise InputValidationError(
                "Custom depth limits are enabled, but the upper and lower depth limits "
                "are not a valid range. Enter an upper and a lower depth limit "
                "(the lower limit must be greater than the upper), or turn off the "
                "custom depth option to use the water table depth."
            )
        return upper_limit, lower_limit
    if has_water_table_depth:
        return max(water_table_depth - 2, 1), min(water_table_depth + 2, 6)
    return None, None

def tds_analysis(ctx: Context) -> Context:
    soil_data_filtered = ctx.frames["soil_data_filtered"]
    background_apec_labels = ["Background", "APEC Background", "BKGD"]
    background_df = soil_data_filtered[
        soil_data_filtered["apec"].isin(background_apec_labels)]
    
    tds_df_all = background_df[tds_header_columns.keys()]
    # List of unique sample_ids to include for TDS analysis (background only).
    tds_unique_samples = tds_df_all["sample_id"].unique()
    # Seed the frontend multiselect options from the computed background samples.
    ctx.options["tds_unique_samples"] = [str(s) for s in tds_unique_samples]
    selected = ctx.params.get("tds_bg_samples") or list(map(str, tds_unique_samples))
    tds_df = tds_df_all[tds_df_all["sample_id"].isin(selected)].copy()

    z_values = pd.to_numeric(tds_df["z"], errors="coerce")
    
    upper_limit, lower_limit = _resolve_depth_window(ctx)
    tds_df = tds_df[z_values.between(upper_limit, lower_limit, inclusive="both")].copy()

    bins = [-float("inf"), 20, 50, 70, 90, 120, 130, float("inf")]
    labels = [
        "Below range",
        "Potentially coarse by sieve",
        "Likely fine",
        "Very likely fine",
        "Possibly fine or coarse",
        "Very likely coarse",
        "Above range",
    ]
    tds_df["texture_by_sat_pc"] = pd.cut(
        tds_df["general_inorganics_saturation"],
        bins=bins,
        labels=labels,
        right=False,  # left-inclusive/exclusive right
        include_lowest=True,
    )
    tds_df_display = tds_df.rename(columns=tds_header_columns).copy()
    tds_df_display = tds_df_display.rename(columns={"texture_by_sat_pc": "Texture"})

    for column in tds_df_display.columns.difference(["Location", "Comments", "Texture"]):
        converted_column = pd.to_numeric(tds_df_display[column], errors="coerce")
        non_missing_values = tds_df_display[column].notna()
        if converted_column[non_missing_values].notna().all():
            tds_df_display[column] = converted_column
    # tds_df_display = tds_df_display.where(pd.notnull(tds_df_display), "-")
    # tds_df_display = tds_df_display.replace({"None": "-", "nan": "-"})


    # TDS Grouping and averaging
    tds_group_columns = {
    'sample_id': "Location",
    'depth_m': "Depth (m)",
    #'z': "Z",
    'soluble_ions_chloride_mg_kg': "Chloride",
    'soluble_ions_sulphate_mg_kg': "Sulphate",
    'soluble_ions_carbonate_mg_kg': "Carbonate",
    'soluble_ions_bicarbonate_mg_kg': "Bicarbonate",
    'general_inorganics_saturation': "Saturation",
}

    avg_cols = tds_df.groupby("sample_id", as_index=False).agg(
        {
            "soluble_ions_sulphate_mg_kg": "mean",
            "soluble_ions_carbonate_mg_kg": lambda x: pd.to_numeric(
                x, errors="coerce"
            ).mean(),
            "soluble_ions_bicarbonate_mg_kg": lambda x: pd.to_numeric(
                x, errors="coerce"
            ).mean(),
        }
    )

    # Rename columns as requested
    columns_map = {
        "soluble_ions_sulphate_mg_kg": "Average Sulphate",
        "soluble_ions_carbonate_mg_kg": "Average Carbonate",
        "soluble_ions_bicarbonate_mg_kg": "Average Bicarbonate",
    }

    avg_cols = avg_cols.rename(columns=columns_map)
    tds_grouped = pd.merge(tds_df[tds_group_columns.keys()], avg_cols, on="sample_id", how="left")
    tds_grouped_display = tds_grouped.rename(columns=tds_group_columns)
    tds_grouped_display = tds_grouped_display.round(2)

        # Create a mask that flags the first row of each group (grouped by 'Location')
    mask = ~tds_grouped_display["Location"].duplicated(keep="first")

    # Identify columns that start with "Average"
    avg_cols = [col for col in tds_grouped_display.columns if col.startswith("Average")]

    # Create a copy to avoid modifying original
    tds_grouped_display_clean = tds_grouped_display.copy()
    numeric_cols = tds_grouped_display_clean.columns.difference(["Location"])
    tds_grouped_display_clean[numeric_cols] = tds_grouped_display_clean[numeric_cols].apply(lambda col: pd.to_numeric(col.mask(col.eq("-")), errors="coerce"))

    tds_grouped_display_clean.loc[~mask, "Location"] = ""
    tds_grouped_display_clean.loc[~mask, avg_cols] = float("nan")

    # Overwrite the original DataFrame with the cleaned one
    tds_grouped_display = tds_grouped_display_clean

    # Append a final row with the average of every column except the first two (Location, Depth)
    average_row = {col: None for col in tds_grouped_display.columns}
    average_row[tds_grouped_display.columns[0]] = "AVERAGE"
    for col in tds_grouped_display.columns[2:]:
        average_row[col] = round(pd.to_numeric(tds_grouped_display[col], errors="coerce").mean(), 2)

    tds_grouped_display = pd.concat(
        [tds_grouped_display, pd.DataFrame([average_row])],
        ignore_index=True,
    )

    # Outputs
    ctx.frames["tds_raw_data_table"] = tds_df
    ctx.frames["tds_data_table"] = tds_df_display
    ctx.frames["tds_grouped_data"] = tds_grouped_display

    return ctx


def _parse_depth_range(depth_text):
    text = str(depth_text).strip().replace("–", "-").replace(">", "").replace("<", "")
    parts = [p for p in text.split("-") if p.strip() != ""]
    try:
        if len(parts) >= 2:
            return float(parts[0]), float(parts[1])
        if len(parts) == 1:
            return float(parts[0]), float("inf")
    except ValueError:
        pass
    return None, None


def _guideline_to_category(guideline_value, soil_type):
    if str(soil_type).strip().lower().startswith("top"):
        bins, labels = ec_top_bins, ec_top_labels
    else:
        bins, labels = ec_sub_bins, ec_sub_labels
    value = pd.to_numeric(guideline_value, errors="coerce")
    if pd.isna(value):
        return None
    for edge, label in zip(bins[1:], labels):
        if value <= edge:
            return label
    return labels[-1]

def tds_tests(ctx: Context) -> Context:
    scarg_guidelines_df = ctx.frames["scarg_guidelines_df"]
    tds_depth_ec_categories = []
    upper_limit, lower_limit = _resolve_depth_window(ctx)
    for index_label, row in scarg_guidelines_df.iterrows():
        interval_top, interval_bottom = _parse_depth_range(row["Depth"])
        if interval_top is None:
            continue
        if not ((interval_top < float(lower_limit)) and (interval_bottom > float(upper_limit))):
            continue
        soil_type = str(index_label).split()[0]
        category = _guideline_to_category(row["EC Guideline"], soil_type)
        if category is not None and category not in tds_depth_ec_categories:
            tds_depth_ec_categories.append(category)

    # TDS Tests/Practitioner notes
    tds_test_results = []
    tds_df = ctx.frames["tds_raw_data_table"]

    # All samples have chloride concentrations less than 100 mg/kg

    tds_test_results.append({"Test": "Historical data has been checked to ensure  the sulphate data is expressed in the appropriate units, Sulphate, as opposed to Sulfur, in mg/kg.",
                            "Result": "",
                            "Notes": ""
                            })



    tds_df_chloride_gt_100 = tds_df[tds_df["soluble_ions_chloride_mg_kg"] > 100]
    if not tds_df_chloride_gt_100.empty:
        tds_test_results.append({"Test": "All samples have Cl < 100 mg/kg",
                                "Result": "No",
                                "Notes": list(tds_df_chloride_gt_100["sample_id"].unique())
                                })
    else:
        tds_test_results.append({"Test": "All samples have Cl < 100 mg/kg",
                                "Result": "Yes",
                                "Notes": ""
                                })

    # EC rating categories in shallow GW
    tds_test_results.append({"Test": "EC soil rating categories for the shallow groundwater interval used to assess TDS.",
                            "Result": "",
                            "Notes": ", ".join(tds_depth_ec_categories) if tds_depth_ec_categories else ""
                            })

    # At least four separate sample locations (required for Good rating category)
    tds_unique_sample_ids = tds_df["sample_id"].nunique()

    # If "Good" is the only EC category, then 4 samples needed
    if set(tds_depth_ec_categories) == set(["Good"]):
        if tds_unique_sample_ids >= 4:
            tds_test_results.append({"Test": "Four locations required when subsoil salinity is Good",
                                    "Result": "Yes",
                                    "Notes": ""
                                    })

        else:
            tds_test_results.append({"Test": "Four locations required when subsoil salinity is Good",
                                    "Result": "No",
                                    "Notes": ""
                                    })
        # 6 samples arent needed, so that test is NA
        tds_test_results.append({"Test": "Six locations required when subsoil salinity is Fair to Unsuitable",
                                "Result": "N/A",
                                "Notes": ""
                                })
    # EC is anything other than "Good" across the depth interval
    else:
        if tds_unique_sample_ids >= 6:
            tds_test_results.append({"Test": "Six locations required when subsoil salinity is Fair to Unsuitable",
                                    "Result": "Yes",
                                    "Notes": ""
                                    })

        else:
            tds_test_results.append({"Test": "Six locations required when subsoil salinity is Fair to Unsuitable",
                                    "Result": "No",
                                    "Notes": ""
                                    })
        # 6 samples arent needed, so that test is NA
        tds_test_results.append({"Test": "Four locations required when subsoil salinity is Good",
                                "Result": "N/A",
                                "Notes": ""
                                })

    tds_test_results_df = pd.DataFrame(tds_test_results)
    ctx.frames["tds_test_results"] = tds_test_results_df
    return ctx