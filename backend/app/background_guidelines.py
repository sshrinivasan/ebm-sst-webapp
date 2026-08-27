"""Background & Guidelines — compute SCARG EC/SAR guidelines (notebook cells 64-79).

Ported near-verbatim from the notebook. The background statistics + outlier
passes and the guideline extraction are unchanged; only the Hex inputs
(site_specific/sst flags) and the shared bins are threaded in from the Context.

Produces (ctx.frames): scarg_guidelines_df, scarg_rating_guideline_summary_df,
ec_report_data_display_df_hex, sar_report_data_display_df_hex,
ec_report_data_display_df, sar_report_data_display_df.
Produces (ctx.exports, for later Excel export): ec_report_dict, sar_report_dict,
background_appendix_sheet_dfs.
"""
from __future__ import annotations

import pandas as pd

from .context import Context
from .ec_sar_rating import EC_TOP_BINS, EC_SUB_BINS, SAR_BINS, RATING_LABELS


# Given a category such as "Good" in a set of bins with labels, return the highest value of that bin
# For example:
#   ec_top_bins = [-float("inf"), 2, 4, 8, float("inf")]
#   ec_top_labels = ["Good", "Fair", "Poor", "Unsuitable"]
# Then given "Good", return 2. Given "Poor", return 8
def get_category_max_value(category, bins, labels):
    try:
        idx = labels.index(category)
        return bins[idx + 1]
    except (ValueError, IndexError):
        return None


appendix_columns = {
    "sample_id": "Sample ID",
    "depth_m": "Depth",
    "general_inorganics_ph": "pH",
    "general_inorganics_ec_ds_m": "EC", 
    "general_inorganics_sar": "SAR", 
    "general_inorganics_saturation": "Sat", 
    "soluble_ions_chloride_mg_kg": "Cl", 
    "soluble_ions_sulphate_mg_kg": "Sulph", 
    "soluble_ions_sodium_mg_kg": "Na", 
    "soluble_ions_calcium_mg_kg": "Ca",
    "soluble_ions_magnesium_mg_kg": "Mg",
    "soluble_ions_potassium_mg_kg": "K" 
}

# Hack to get a special row for units in the Excel output
appendix_unit_headers = pd.DataFrame([[None, "m", 
    None, "dS/m", None, 
    "%", "mg/kg","mg/kg", "mg/kg", 
    "mg/kg", "mg/kg", "mg/kg"]],
    columns=appendix_columns.keys()
)


# EC statistics
def ec_stats(ec_values, soil_type, ec_top_bins, ec_top_labels, ec_sub_bins, ec_sub_labels,
             max_values=None):
    """max_values: optional separate series used only for the reported Maximum.
    Supply the un-averaged (per-result) values where ec_values has been averaged
    across duplicates; leave as None to take the max of ec_values itself."""

    # Get mean, max, 95th pecentile and stddev for EC
    ec_mean_val = ec_values.mean()
    ec_pct95_val = ec_values.quantile(0.95)
    ec_max_val = (max_values if max_values is not None and not max_values.empty else ec_values).max()
    ec_stddev_val = ec_values.std()

    # Now we have mean, 95th percentile, and max values for EC
    # Categorize the 95th percentile, and get the max value in that category range from the reference table
    if soil_type == "Topsoil":
        ec_cat = pd.cut([ec_pct95_val], ec_top_bins, labels=ec_top_labels)[0]
        ec_mean_cat = pd.cut([ec_mean_val], ec_top_bins, labels=ec_top_labels)[0]
    elif soil_type == "Subsoil":
        ec_cat = pd.cut([ec_pct95_val], ec_sub_bins, labels=ec_sub_labels)[0]
        ec_mean_cat = pd.cut([ec_mean_val], ec_sub_bins, labels=ec_sub_labels)[0]
    else:
        print("Error: cannot file soil category")            
    # ec_cat is the category of the 956th percentile value for that depth
    # Now that we know the category, the EC guideline for this depth is the max value of that category in the refernce table
    if ec_cat != "Unsuitable":
        if soil_type == "Topsoil":
            ec_guideline = get_category_max_value(ec_cat, ec_top_bins, ec_top_labels)
        elif soil_type == "Subsoil":
            ec_guideline = get_category_max_value(ec_cat, ec_sub_bins, ec_sub_labels)
        else:
            print ("ERROR: Cannot find soil type")

    else:
        # Guideline stays on the max of the values the stats were computed from
        # (the averaged series), not the separately-reported raw Maximum.
        ec_guideline = ec_values.max()

    # 2 category jump
    two_category_jump = "No"
    if ec_mean_cat == "Good" and ec_cat == "Poor":
        two_category_jump = "Yes"
    if ec_mean_cat == "Fair" and ec_cat == "Unsuitable":
        two_category_jump = "Yes"

    return (ec_mean_val, ec_pct95_val, ec_max_val, ec_stddev_val, ec_cat, ec_mean_cat, ec_guideline, two_category_jump)


def sar_stats(sar_values, soil_type, sar_top_bins, sar_top_labels, sar_sub_bins, sar_sub_labels,
              max_values=None):
    """max_values: optional separate series used only for the reported Maximum.
    Supply the un-averaged (per-result) values where sar_values has been averaged
    across duplicates; leave as None to take the max of sar_values itself."""

    # Get mean, max, 95th pecentile and stddev for SAR
    sar_mean_val = sar_values.mean()
    sar_pct95_val = sar_values.quantile(0.95)
    sar_max_val = (max_values if max_values is not None and not max_values.empty else sar_values).max()
    sar_stddev_val = sar_values.std()

    # Now we have mean, 95th percentile, and max values for SAR
    # Categorize the 95th percentile, and get the max value in that category range from the reference table
    if soil_type == "Topsoil":
        sar_cat = pd.cut([sar_pct95_val], sar_top_bins, labels=sar_top_labels)[0]
    elif soil_type == "Subsoil":
        sar_cat = pd.cut([sar_pct95_val], sar_sub_bins, labels=sar_sub_labels)[0]
    else:
        print("Error: cannot file soil category")            
    # sar_cat is the category of the 95th percentile value for that depth
    # Now that we know the category, the SAR guideline for this depth is the max value of that category in the refernce table
    if sar_cat != "Unsuitable":
        sar_guideline = get_category_max_value(sar_cat, sar_top_bins, sar_top_labels)
    else:
        # Guideline stays on the max of the values the stats were computed from
        # (the averaged series), not the separately-reported raw Maximum.
        sar_guideline = sar_values.max()
    
    return (
        sar_mean_val,
        sar_pct95_val,
        sar_max_val,
        sar_stddev_val,
        sar_cat,
        sar_guideline
    )


def make_hex_display_ready_df(df):
    display_df = df.copy()
    display_df.columns = display_df.columns.astype(str)
    display_df = display_df.where(pd.notna(display_df), "")
    return display_df.astype(str)


def compute_scarg_guidelines(ctx: Context) -> Context:
    """Background statistics, ratings, and EC/SAR guideline extraction."""
    soil_data_filtered = ctx.frames["soil_data_filtered"]
    topsoil_depths_validated = ctx.frames["topsoil_depths_validated"]
    sst_flag = bool(ctx.params.get("sst_flag", True))

    ec_top_bins, ec_top_labels = EC_TOP_BINS, RATING_LABELS
    ec_sub_bins, ec_sub_labels = EC_SUB_BINS, RATING_LABELS
    sar_top_bins, sar_top_labels = SAR_BINS, RATING_LABELS
    sar_sub_bins, sar_sub_labels = SAR_BINS, RATING_LABELS

    ec_report_dict = {}
    ec_report_dict["Statistical Parameter"] = ["n (count)", "Mean", "95th Percentile", "Maximum", "Standard Deviation", "Outlier", "Rating Category", "Guideline"]

    sar_report_dict = {}
    sar_report_dict["Statistical Parameter"] = ["n (count)", "Mean", "95th Percentile", "Maximum", "Standard Deviation", "Rating Category", "Guideline"]

    # variable to store appendix sheets for Excel file
    background_appendix_sheet_dfs = {}


    def round_guideline(value):
        """Round numeric guidelines to 2 dp; pass anything non-numeric through."""
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return value

    # For each depth interval specified by the user, cretae a dataframe containing all the data within that depth range
    for idx, row in topsoil_depths_validated.iterrows():
        # try to convert and handle float errors in top/bottom for robustness
        try:
            top = float(row["top"])
            bottom = float(row["bottom"])
            soil_type = row["type"]
        except (KeyError, ValueError, TypeError):
            # skip row if top/bottom is missing or invalid
            continue
    
        # Sheet name
        excel_sheetname = "{0}-{1}".format(top, bottom)
        # Summary report column name
        ec_report_column_name = "{0} {1}-{2}".format(soil_type, top, bottom)
        sar_report_column_name = "{0} {1}-{2}".format(soil_type, top, bottom)

        # Filter soil_data_filtered for z within top-bottom (inclusive) and comments in Background list
        # Special case for topsoil vs subsoil
        if str(soil_type).strip() == "Topsoil":
            depth_mask = (soil_data_filtered["z"] > top) & (soil_data_filtered["z"] < bottom)
        else:
            depth_mask = (soil_data_filtered["z"] >= top) & (soil_data_filtered["z"] <= bottom)

        filtered_by_depth_df = soil_data_filtered[
            depth_mask &
            (soil_data_filtered["apec"].isin(["Background", "APEC Background"]))
        ]
        filtered_by_depth_df = filtered_by_depth_df.sort_values("z", kind="mergesort").reset_index(drop=True)
        # filtered_by_depth_df is a sub-dataframe at each depth range    
        # Drop missing values to avoid errors in mean/percentile calculations
        ec_values = filtered_by_depth_df["general_inorganics_ec_ds_m"].dropna()
        sar_values = filtered_by_depth_df["general_inorganics_sar"].dropna()
        sat_values = filtered_by_depth_df["general_inorganics_saturation"].dropna()
        sat_mean_val = sat_values.mean()

        if not ec_values.empty and not sar_values.empty:
            # ----- EC Stuff
            (ec_mean_val, ec_pct95_val, ec_max_val, ec_stddev_val, ec_cat, ec_mean_cat, ec_guideline, two_category_jump) = ec_stats(
                ec_values, soil_type, ec_top_bins, ec_top_labels, ec_sub_bins, ec_sub_labels)

            # ----- SAR Stuff
            (sar_mean_val, sar_pct95_val, sar_max_val, sar_stddev_val, sar_cat, sar_guideline) = sar_stats(
                sar_values, soil_type, sar_top_bins, sar_top_labels, sar_sub_bins, sar_sub_labels
            )

            # Table in Appendix E
            appendix_df = filtered_by_depth_df[appendix_columns.keys()]
            # Drop rows from appendix_df where EC or SAR are null
            appendix_df = appendix_df.dropna(
                subset=["general_inorganics_ec_ds_m", "general_inorganics_sar"]
            )
            # ----> Add summary rows
    
            # Outlier detection
            final_outliers = 'N/A'
            outlier_calc = ec_mean_val + 2 * ec_stddev_val

            # Special outlier for analysis for 1-1.5 depth only if SST
            # Print out to sheet without outliers for interval 1-1.5        
            if (top == 1.0) and (bottom == 1.5):
                # Average duplicate rows in this interval only
                numeric_columns = [
                    col for col in filtered_by_depth_df.select_dtypes(include="number").columns
                    if col != "sample_id"
                ]
                non_numeric_columns = [
                    col for col in filtered_by_depth_df.columns
                    if col not in numeric_columns and col != "sample_id"
                ]
                def format_aggregated_z(z_values):
                    z_values = pd.to_numeric(z_values, errors="coerce").dropna().drop_duplicates().sort_values()
                    return ", ".join(f"{z:g}" for z in z_values)

                aggregation = {col: "mean" for col in numeric_columns}
                aggregation.update({col: "first" for col in non_numeric_columns})
                aggregation["depth_m"] = lambda depths: format_aggregated_z(filtered_by_depth_df.loc[depths.index, "z"])
                filtered_by_depth_averaged_df = (
                    filtered_by_depth_df
                    .groupby("sample_id", as_index=False)
                    .agg(aggregation)
                )
                filtered_by_depth_averaged_df = filtered_by_depth_averaged_df[filtered_by_depth_df.columns]
                filtered_by_depth_averaged_df = filtered_by_depth_averaged_df.sort_values("z", kind="mergesort").reset_index(drop=True)
                outlier_source_df = filtered_by_depth_averaged_df

                ec_values = outlier_source_df["general_inorganics_ec_ds_m"].dropna()
                sar_values = outlier_source_df["general_inorganics_sar"].dropna()
                sat_values = outlier_source_df["general_inorganics_saturation"].dropna()
                sat_mean_val = sat_values.mean()

                # Reported Maximum uses the un-averaged results; every other statistic
                # (and the outlier threshold) stays on the per-sample averages.
                ec_values_raw = filtered_by_depth_df["general_inorganics_ec_ds_m"].dropna()
                sar_values_raw = filtered_by_depth_df["general_inorganics_sar"].dropna()

                (ec_mean_val, ec_pct95_val, ec_max_val, ec_stddev_val, ec_cat, ec_mean_cat, ec_guideline, two_category_jump) = ec_stats(
                    ec_values, soil_type, ec_top_bins, ec_top_labels, ec_sub_bins, ec_sub_labels,
                    max_values=ec_values_raw)
                (sar_mean_val, sar_pct95_val, sar_max_val, sar_stddev_val, sar_cat, sar_guideline) = sar_stats(
                    sar_values, soil_type, sar_top_bins, sar_top_labels, sar_sub_bins, sar_sub_labels,
                    max_values=sar_values_raw
                )
                outlier_calc = ec_mean_val + 2 * ec_stddev_val
                # Outlier detection stays on the averaged max
                ec_avg_max_val = ec_values.max()
                appendix_df = outlier_source_df[appendix_columns.keys()]
                appendix_df = appendix_df.dropna(
                    subset=["general_inorganics_ec_ds_m", "general_inorganics_sar"]
                )
            
                appendix_df_outlier_0 = outlier_source_df[appendix_columns.keys()]
                # Drop rows from appendix_df where EC or SAR are null
                appendix_df_outlier_0 = appendix_df_outlier_0.dropna(
                    subset=["general_inorganics_ec_ds_m", "general_inorganics_sar"]
                )

                # Find how many outliers lie above the outlier_calc threshold
                num_ec_outliers = len(appendix_df_outlier_0[appendix_df_outlier_0["general_inorganics_ec_ds_m"] > outlier_calc])
                ec_outliers_df = appendix_df_outlier_0[appendix_df_outlier_0["general_inorganics_ec_ds_m"] > outlier_calc]

                summary_rows = [
                    [None, None, None, None, None, None, None, None, None, None, None, None],
                    [None, None, "n(count)", len(appendix_df_outlier_0), len(appendix_df_outlier_0), None, None, None, None, None, None, None],
                    [None, None, "Mean", ec_mean_val.round(2), sar_mean_val.round(2), sat_mean_val.round(2), None, None, None, None, None, None],
                    [None, None, "95th Percentile", ec_pct95_val.round(2), sar_pct95_val.round(2), None, None, None, None, None, None, None],
                    [None, None, "Maximum", round(ec_max_val, 2), round(sar_max_val, 2), None, None, None, None, None, None, None],
                    [None, None, "Standard Deviation", round(ec_stddev_val, 2), round(sar_stddev_val, 2), None, None, None, None, None, None, None],

                    [None, None, "Outlier Calculation",outlier_calc.round(2), None, None, None, None, None, None, None, None],
                    [None, None, "Outliers (Count)", num_ec_outliers, None, None, None, None, None, None, None, None],

                    [None, None, "Two Category Jump (Yes/No)", two_category_jump, None, None, None, None, None, None, None, None],
                    [None, None, "Rating Category", ec_cat, sar_cat, None, None, None, None, None, None, None],
                    [None, None, "Guideline", ec_guideline, sar_guideline, None, None, None, None, None, None, None]
                ]
            
                # Convert summary_rows (list of lists) to a DataFrame with columns matching appendix_df
                summary_rows_df = pd.DataFrame(summary_rows, columns=appendix_df_outlier_0.columns)

                # Append rows and reindex            
                appendix_df_outlier_0_display = pd.concat([appendix_df_outlier_0, summary_rows_df], ignore_index=True)
                appendix_df_outlier_0_display = pd.concat([
                    appendix_df_outlier_0_display[:0],
                    appendix_unit_headers,
                    appendix_df_outlier_0_display[0:]
                ], ignore_index=True)
            
                # Append the outliers for reference
                # Add a blank row and some headers for pretty printing in the Excel file
                outlier_header_rows = [
                    [None, None, None, None, None, None, None, None, None, None, None, None],
                    ["OUTLIERS", None, None, None, None, None, None, None, None, None, None, None],
                    [None, None, None, None, None, None, None, None, None, None, None, None],
                ]
                outlier_header_df = pd.DataFrame(outlier_header_rows, columns=appendix_df_outlier_0.columns)

                appendix_df_outlier_0_display = pd.concat([appendix_df_outlier_0_display, outlier_header_df], ignore_index=True)
                appendix_df_outlier_0_display = pd.concat([appendix_df_outlier_0_display, ec_outliers_df], ignore_index=True)

                # Rename columns to human readable ones
                appendix_df_outlier_0_display.rename(columns=appendix_columns, inplace=True)
                # appendix_df_outlier_0_display.to_excel(writer, sheet_name="1.0-1.5 Pre-Outlier", index=False)
                background_appendix_sheet_dfs["1.0-1.5 Pre-Outlier"] = appendix_df_outlier_0_display

                # Remove the outlier, if max val is greater than the outlier cutoff
                # only do this for the 1-1.5 interval if SST is enabled
                if (ec_avg_max_val > outlier_calc) and sst_flag == True:
                    print ("Found Outlier, removing value 1")
                    print("Outlier {0} Max {1}".format(outlier_calc, ec_avg_max_val))

                    # Drop rows with EC greater than the cutoff
                    filtered_by_depth_df_outlier_1 = outlier_source_df[outlier_source_df["general_inorganics_ec_ds_m"] < outlier_calc]
                    filtered_by_depth_df_outlier_1 = filtered_by_depth_df_outlier_1.sort_values("z", kind="mergesort").reset_index(drop=True)

                    # Restrict the un-averaged results to the samples that survived the removal
                    _surviving_samples_1 = filtered_by_depth_df_outlier_1["sample_id"]
                    _raw_outlier1_df = filtered_by_depth_df[
                        filtered_by_depth_df["sample_id"].isin(_surviving_samples_1)
                    ]

                    # Redo the calculation once one outlier has been removed
                    ec_values_outlier1_removed = filtered_by_depth_df_outlier_1["general_inorganics_ec_ds_m"].dropna()
                    (ec_mean_val, ec_pct95_val, ec_max_val, ec_stddev_val, ec_cat, ec_mean_cat, ec_guideline, two_category_jump) = ec_stats(
                        ec_values_outlier1_removed, soil_type, ec_top_bins, ec_top_labels, ec_sub_bins, ec_sub_labels,
                        max_values=_raw_outlier1_df["general_inorganics_ec_ds_m"].dropna())

                    sar_values_outlier1_removed = filtered_by_depth_df_outlier_1["general_inorganics_sar"].dropna()
                    (sar_mean_val, sar_pct95_val, sar_max_val, sar_stddev_val, sar_cat, sar_guideline) = sar_stats(
                        sar_values_outlier1_removed, soil_type, sar_top_bins, sar_top_labels, sar_sub_bins, sar_sub_labels,
                        max_values=_raw_outlier1_df["general_inorganics_sar"].dropna())
                
                    sat_values_outlier1_removed = filtered_by_depth_df_outlier_1["general_inorganics_saturation"].dropna()
                    sat_mean_val = sat_values_outlier1_removed.mean()

                    # Outlier after removing the max val once
                    outlier_calc = ec_mean_val + 2 * ec_stddev_val
                    ec_avg_max_val = ec_values_outlier1_removed.max()

                    num_ec_outliers = len(filtered_by_depth_df_outlier_1[filtered_by_depth_df_outlier_1["general_inorganics_ec_ds_m"] > outlier_calc])
                    ec_outliers_df = filtered_by_depth_df_outlier_1[filtered_by_depth_df_outlier_1["general_inorganics_ec_ds_m"] > outlier_calc]
                    ec_outliers_df = ec_outliers_df[appendix_columns.keys()]

                    # Print out to sheet for outlier 1
                    appendix_df_outlier_1 = filtered_by_depth_df_outlier_1[appendix_columns.keys()]
                    # Drop rows from appendix_df where EC or SAR are null
                    appendix_df_outlier_1 = appendix_df_outlier_1.dropna(
                        subset=["general_inorganics_ec_ds_m", "general_inorganics_sar"]
                    )
                    summary_rows = [
                        [None, None, None, None, None, None, None, None, None, None, None, None],
                        [None, None, "n(count)", len(appendix_df_outlier_1), len(appendix_df_outlier_1), None, None, None, None, None, None, None],
                        [None, None, "Mean", ec_mean_val.round(2), sar_mean_val.round(2), sat_mean_val.round(2), None, None, None, None, None, None],
                        [None, None, "95th Percentile", ec_pct95_val.round(2), sar_pct95_val.round(2), None, None, None, None, None, None, None],
                        [None, None, "Maximum", round(ec_max_val, 2), round(sar_max_val, 2), None, None, None, None, None, None, None],
                        [None, None, "Standard Deviation", round(ec_stddev_val, 2), round(sar_stddev_val, 2), None, None, None, None, None, None, None],

                        [None, None, "Outlier Calculation", outlier_calc.round(2), None, None, None, None, None, None, None, None],
                        [None, None, "Outliers (Count)", num_ec_outliers, None, None, None, None, None, None, None, None],

                        [None, None, "Two Category Jump (Yes/No)", two_category_jump, None, None, None, None, None, None, None, None],
                        [None, None, "Rating Category", ec_cat, sar_cat, None, None, None, None, None, None, None],
                        [None, None, "Guideline", ec_guideline, sar_guideline, None, None, None, None, None, None, None]
                    ]
                    # Convert summary_rows (list of lists) to a DataFrame with columns matching appendix_df
                    summary_rows_df = pd.DataFrame(summary_rows, columns=appendix_df.columns)

                    # Append summary stats rows
                    appendix_df_outlier_1_display = pd.concat([appendix_df_outlier_1, summary_rows_df], ignore_index=True)
                    # Append units in the second row below the headers
                    appendix_df_outlier_1_display = pd.concat([
                        appendix_df_outlier_1_display[:0],
                        appendix_unit_headers,
                        appendix_df_outlier_1_display[0:]
                    ], ignore_index=True)                


                    # Append the outliers for reference
                    # Add a blank row and some headers for pretty printing in the Excel file
                    outlier_header_rows = [
                        [None, None, None, None, None, None, None, None, None, None, None, None],
                        ["OUTLIERS", None, None, None, None, None, None, None, None, None, None, None],
                        [None, None, None, None, None, None, None, None, None, None, None, None],
                    ]
                    outlier_header_df = pd.DataFrame(outlier_header_rows, columns=appendix_df_outlier_1.columns)
                    appendix_df_outlier_1_display = pd.concat([appendix_df_outlier_1_display, outlier_header_df], ignore_index=True)
                    appendix_df_outlier_1_display = pd.concat([appendix_df_outlier_1_display, ec_outliers_df], ignore_index=True)

                    # Update headers to human readable
                    appendix_df_outlier_1_display.rename(columns=appendix_columns, inplace=True)
                    # appendix_df_outlier_1_display.to_excel(writer, sheet_name="1.0-1.5 Outlier 1", index=False)
                    background_appendix_sheet_dfs["1.0-1.5 Outlier 1"] = appendix_df_outlier_1_display

                    if ec_avg_max_val > outlier_calc:
                        print ("Found Outlier, removing value 2")
                        print("Outlier {0} Max {1}".format(outlier_calc, ec_avg_max_val))

                        filtered_by_depth_df_outlier_2 = filtered_by_depth_df_outlier_1[filtered_by_depth_df_outlier_1["general_inorganics_ec_ds_m"] < outlier_calc]
                        filtered_by_depth_df_outlier_2 = filtered_by_depth_df_outlier_2.sort_values("z", kind="mergesort").reset_index(drop=True)

                        # Restrict the un-averaged results to the samples that survived both removals
                        _surviving_samples_2 = filtered_by_depth_df_outlier_2["sample_id"]
                        _raw_outlier2_df = filtered_by_depth_df[
                            filtered_by_depth_df["sample_id"].isin(_surviving_samples_2)
                        ]

                        # Redo the calculation
                        ec_values_outlier2_removed = filtered_by_depth_df_outlier_2["general_inorganics_ec_ds_m"].dropna()
                        (ec_mean_val, ec_pct95_val, ec_max_val, ec_stddev_val, ec_cat, ec_mean_cat, ec_guideline, two_category_jump) = ec_stats(
                            ec_values_outlier2_removed, soil_type, ec_top_bins, ec_top_labels, ec_sub_bins, ec_sub_labels,
                            max_values=_raw_outlier2_df["general_inorganics_ec_ds_m"].dropna())
                    
                        sar_values_outlier2_removed = filtered_by_depth_df_outlier_2["general_inorganics_sar"].dropna()
                        (sar_mean_val, sar_pct95_val, sar_max_val, sar_stddev_val, sar_cat, sar_guideline) = sar_stats(
                            sar_values_outlier2_removed, soil_type, sar_top_bins, sar_top_labels, sar_sub_bins, sar_sub_labels,
                            max_values=_raw_outlier2_df["general_inorganics_sar"].dropna())
                    
                        sat_values_outlier2_removed = filtered_by_depth_df_outlier_2["general_inorganics_saturation"].dropna()
                        sat_mean_val = sat_values_outlier2_removed.mean()

                        # Outlier calcualtion after two removals
                        outlier_calc = ec_mean_val + 2 * ec_stddev_val

                        num_ec_outliers = len(filtered_by_depth_df_outlier_2[filtered_by_depth_df_outlier_2["general_inorganics_ec_ds_m"] > outlier_calc])
                        ec_outliers_df = filtered_by_depth_df_outlier_2[filtered_by_depth_df_outlier_2["general_inorganics_ec_ds_m"] > outlier_calc]
                        ec_outliers_df = ec_outliers_df[appendix_columns.keys()]

                        # Print out to sheet for outlier 1
                        appendix_df_outlier_2 = filtered_by_depth_df_outlier_2[appendix_columns.keys()]
                        # Drop rows from appendix_df where EC or SAR are null
                        appendix_df_outlier_2 = appendix_df_outlier_2.dropna(
                            subset=["general_inorganics_ec_ds_m", "general_inorganics_sar"]
                        )
                        summary_rows = [
                            [None, None, None, None, None, None, None, None, None, None, None, None],
                            [None, None, "n(count)", len(appendix_df_outlier_2), len(appendix_df_outlier_2), None, None, None, None, None, None, None],
                            [None, None, "Mean", ec_mean_val.round(2), sar_mean_val.round(2), sat_mean_val.round(2), None, None, None, None, None, None],
                            [None, None, "95th Percentile", ec_pct95_val.round(2), sar_pct95_val.round(2), None, None, None, None, None, None, None],
                            [None, None, "Maximum", round(ec_max_val, 2), round(sar_max_val, 2), None, None, None, None, None, None, None],
                            [None, None, "Standard Deviation", round(ec_stddev_val, 2), round(sar_stddev_val, 2), None, None, None, None, None, None, None],

                            [None, None, "Outlier Calculation", outlier_calc.round(2), None, None, None, None, None, None, None, None],
                            [None, None, "Outliers (Count)", num_ec_outliers, None, None, None, None, None, None, None, None],

                            [None, None, "Two Category Jump (Yes/No)", two_category_jump, None, None, None, None, None, None, None, None],
                            [None, None, "Rating Category", ec_cat, sar_cat, None, None, None, None, None, None, None],
                            [None, None, "Guideline", ec_guideline, sar_guideline, None, None, None, None, None, None, None]
                        ]
                        # Convert summary_rows (list of lists) to a DataFrame with columns matching appendix_df
                        summary_rows_df = pd.DataFrame(summary_rows, columns=appendix_df_outlier_2.columns)

                        # Append summary stats
                        appendix_df_outlier_2_display = pd.concat([appendix_df_outlier_2, summary_rows_df], ignore_index=True)
                        # Append units in second row
                        appendix_df_outlier_2_display = pd.concat([
                            appendix_df_outlier_2_display[:0],
                            appendix_unit_headers,
                            appendix_df_outlier_2_display[0:]
                        ], ignore_index=True)
                    
                        # Append the outliers for reference
                        # Add a blank row and some headers for pretty printing in the Excel file
                        outlier_header_rows = [
                            [None, None, None, None, None, None, None, None, None, None, None, None],
                            ["OUTLIERS", None, None, None, None, None, None, None, None, None, None, None],
                            [None, None, None, None, None, None, None, None, None, None, None, None],
                        ]
                        outlier_header_df = pd.DataFrame(outlier_header_rows, columns=appendix_df_outlier_2.columns)
                        appendix_df_outlier_2_display = pd.concat([appendix_df_outlier_2_display, outlier_header_df], ignore_index=True)
                        appendix_df_outlier_2_display = pd.concat([appendix_df_outlier_2_display, ec_outliers_df], ignore_index=True)

                        # Update headers to human readable
                        appendix_df_outlier_2_display.rename(columns=appendix_columns, inplace=True)
                        # appendix_df_outlier_2_display.to_excel(writer, sheet_name="1.0-1.5 Outlier 2", index=False)
                        background_appendix_sheet_dfs["1.0-1.5 Outlier 2"] = appendix_df_outlier_2_display


                    else: # Outlier 2
                        final_outliers = "0"
                else: # Outlier 1
                    final_outliers = "0"
        
            # end if top=1 and bottom=1.5  
            else:
                # For all other depths, print out summary stats
                num_ec_outliers = len(appendix_df[appendix_df["general_inorganics_ec_ds_m"] > outlier_calc])
                summary_rows = [
                    [None, None, None, None, None, None, None, None, None, None, None, None],
                    [None, None, "n(count)", len(appendix_df), len(appendix_df), None, None, None, None, None, None, None],
                    [None, None, "Mean", ec_mean_val.round(2), sar_mean_val.round(2), sat_mean_val.round(2), None, None, None, None, None, None],
                    [None, None, "95th Percentile", ec_pct95_val.round(2), sar_pct95_val.round(2), None, None, None, None, None, None, None],
                    [None, None, "Maximum", round(ec_max_val, 2), round(sar_max_val, 2), None, None, None, None, None, None, None],
                    [None, None, "Standard Deviation", round(ec_stddev_val, 2), round(sar_stddev_val, 2), None, None, None, None, None, None, None],

                    [None, None, "Outlier Calculation", outlier_calc.round(2), None, None, None, None, None, None, None, None],
                    [None, None, "Outliers (Count)", num_ec_outliers, None, None, None, None, None, None, None, None],

                    [None, None, "Two Category Jump (Yes/No)", two_category_jump, None, None, None, None, None, None, None, None],
                    [None, None, "Rating Category", ec_cat, sar_cat, None, None, None, None, None, None, None],
                    [None, None, "Guideline", ec_guideline, sar_guideline, None, None, None, None, None, None, None]
                ]
                # Convert summary_rows (list of lists) to a DataFrame with columns matching appendix_df
                summary_rows_df = pd.DataFrame(summary_rows, columns=appendix_df.columns)

                # Append rows and reindex
                appendix_df_display = pd.concat([appendix_df, summary_rows_df], ignore_index=True)
                appendix_df_display = pd.concat([
                    appendix_df_display[:0],
                    appendix_unit_headers,
                    appendix_df_display[0:]
                ], ignore_index=True)

                appendix_df_display.rename(columns=appendix_columns, inplace=True)
                # appendix_df_display.to_excel(writer, sheet_name=excel_sheetname, index=False)
                background_appendix_sheet_dfs[excel_sheetname] = appendix_df_display
            
            # ------ Report tables -------
            ec_report_dict[ec_report_column_name] = [
                len(appendix_df), 
                ec_mean_val.round(2), 
                ec_pct95_val.round(2), 
                round(ec_max_val, 2), 
                round(ec_stddev_val, 2),
                outlier_calc.round(2),
                ec_cat,
                round_guideline(ec_guideline)
            ]
            sar_report_dict[sar_report_column_name] = [
                len(appendix_df), 
                sar_mean_val.round(2), 
                sar_pct95_val.round(2), 
                round(sar_max_val, 2), 
                round(sar_stddev_val, 2),
                sar_cat,
                round_guideline(sar_guideline)
            ]

    # Create EC and SAR summary report dataframes
    ec_report_data_display_df = pd.DataFrame(ec_report_dict)
    sar_report_data_display_df = pd.DataFrame(sar_report_dict)

    ec_report_data_display_df_hex = make_hex_display_ready_df(ec_report_data_display_df)
    sar_report_data_display_df_hex = make_hex_display_ready_df(sar_report_data_display_df)

    rating_guideline_rows = []

    for col in ec_report_data_display_df_hex.columns[1:]:
        parts = str(col).split(maxsplit=1)
        guideline_interval = parts[0] if parts else ""
        depth = parts[1] if len(parts) > 1 else ""

        ec_lookup = ec_report_data_display_df_hex.set_index("Statistical Parameter")[col]
        sar_lookup = sar_report_data_display_df_hex.set_index("Statistical Parameter")[col]

        rating_guideline_rows.append({
            "Depth": depth,
            "Guideline Interval": guideline_interval,
            "EC Rating": ec_lookup.get("Rating Category", ""),
            "SAR Rating": sar_lookup.get("Rating Category", ""),
            "EC Guideline": ec_lookup.get("Guideline", ""),
            "SAR Guideline": sar_lookup.get("Guideline", ""),
        })

    scarg_rating_guideline_summary_df = pd.DataFrame(rating_guideline_rows)

    # Assume the guideline value comes from the last row (typically how these report tables are structured)
    ec_guideline_row = ec_report_data_display_df.iloc[-1]
    sar_guideline_row = sar_report_data_display_df.iloc[-1]

    columns_to_use = ec_report_data_display_df.columns[1:]

    scarg_guidelines_df = pd.DataFrame({
        "EC Guideline": ec_guideline_row[columns_to_use].values,
        "SAR Guideline": sar_guideline_row[columns_to_use].values
        }, 
        index=columns_to_use
    )

    scarg_guidelines_df.index.name = None
    scarg_guidelines_df["Depth"] = (
        scarg_guidelines_df.index.astype(str).str.split().str[1]
    )
    scarg_guidelines_df = scarg_guidelines_df[["Depth", "EC Guideline", "SAR Guideline"]]

    ctx.frames["ec_report_data_display_df"] = ec_report_data_display_df
    ctx.frames["sar_report_data_display_df"] = sar_report_data_display_df
    ctx.frames["ec_report_data_display_df_hex"] = ec_report_data_display_df_hex
    ctx.frames["sar_report_data_display_df_hex"] = sar_report_data_display_df_hex
    ctx.frames["scarg_rating_guideline_summary_df"] = scarg_rating_guideline_summary_df
    ctx.frames["scarg_guidelines_df"] = scarg_guidelines_df
    ctx.exports["ec_report_dict"] = ec_report_dict
    ctx.exports["sar_report_dict"] = sar_report_dict
    ctx.exports["background_appendix_sheet_dfs"] = background_appendix_sheet_dfs
    return ctx
