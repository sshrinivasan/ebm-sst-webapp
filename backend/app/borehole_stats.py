from __future__ import annotations
import pandas as pd
from .context import Context, InputValidationError

borehole_header_columns = {
    'sample_id': 'Location',
    'depth_m': 'Depth (m)',
    'z': 'Z',
    'comments': 'Comments',
    'apec': 'APEC',
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
borehole_char_columns = {
    'location': "Location", 
    'Ref_A': "Ref_A",
    'max_cl_0_15': "Max Cl\n(0-1.5m)\nmg/kg", 
    'max_z_0_15': "Max Cl\n(0-1.5m)\nmbgs", 
    'max_cl_1_1_15': "Max Cl\n(1-1.5m)\nmg/kg", 
    'max_ec_1_1_15': "Max EC\n(1-1.5m)", 
    'max_sar_1_1_15': "Max SAR\n(1-1.5m)", 
    'max_cl_subsoil': "Max Sub Cl\nmg/kg", 
    'max_z_subsoil': "Max Sub Cl Depth\nmbgs", 
    'max_cl_borehole': "Max Cl\nmg/kg", 
    'max_cl_borehole_z': "Max Cl depth\nmbgs", 
    'max_z_borehole_cl': "Deepest Cl\nmbgs", 
    'max_z_borehole': "Deepest Sample\nmbgs", 
    'top_impact': "Top of Impact", 
    'bottom_impact': "Bottom of Impact", 
    'total_impact_depth': "Total Impact Depth", 
    'continuous_impacts': "Continuous Impacts", 
    'shallow_vertical_closure': "Shallow Vertical Closure",
    'deep_vertical_closure': "Deep Vertical Closure"
}

def _build_borehole_stat_rows(borehole_df, chloride_delineation):
    borehole_stat_rows = []

    # Group by borehole
    groups = borehole_df[~borehole_df["soluble_ions_chloride_mg_kg"].isna()].groupby("sample_id")

    for sample_id, group in groups:

        borehole_stat_row = {}
        borehole_stat_row["location"] = sample_id
        borehole_stat_row["Ref_A"] = group["apec"].unique()[0]

        # Filter group for z between 0 and 1.5
        group_in_z_range = group[(group["z"] >= 0) & (group["z"] <= 1.5)]
        if not group_in_z_range.empty:
            # Find index of maximum soluble_ions_chloride_mg_kg in the filtered group
            idx_max = group_in_z_range["soluble_ions_chloride_mg_kg"].idxmax()
            result_row = group_in_z_range.loc[idx_max]
            borehole_stat_row["max_cl_0_15"] = result_row["soluble_ions_chloride_mg_kg"]
            borehole_stat_row["max_z_0_15"] = result_row["z"]

        # Filter group for z between 1 and 1.5
        group_in_z_range = group[(group["z"] >= 1) & (group["z"] <= 1.5)]
        if not group_in_z_range.empty:
            max_cl = group_in_z_range["soluble_ions_chloride_mg_kg"].max()
            max_ec = group_in_z_range["general_inorganics_ec_ds_m"].max()
            max_sar = group_in_z_range["general_inorganics_sar"].max()

            borehole_stat_row["max_cl_1_1_15"] = max_cl
            borehole_stat_row["max_ec_1_1_15"] = max_ec
            borehole_stat_row["max_sar_1_1_15"] = max_sar

        # Filter group for z more than 1.5
        group_in_z_range = group[(group["z"] > 1.5)]
        if not group_in_z_range.empty:
            # Find index of maximum soluble_ions_chloride_mg_kg in the filtered group
            idx_max = group_in_z_range["soluble_ions_chloride_mg_kg"].idxmax()
            result_row = group_in_z_range.loc[idx_max]
            borehole_stat_row["max_cl_subsoil"] = result_row["soluble_ions_chloride_mg_kg"]
            borehole_stat_row["max_z_subsoil"] = result_row["z"]

        # Find the row with the Max  soluble_ions_chloride_mg_kg across the borehole
        idx_max = group["soluble_ions_chloride_mg_kg"].idxmax()
        result_row = group.loc[idx_max]
        borehole_stat_row["max_cl_borehole"] = result_row["soluble_ions_chloride_mg_kg"]
        borehole_stat_row["max_cl_borehole_z"] = result_row["z"]

        # --- Vertical closure
        group_sorted = group.sort_values("z")
        shallowest_row = group_sorted.iloc[0]
        deepest_row = group_sorted.iloc[-1]

        borehole_stat_row["max_z_borehole"] = deepest_row["z"]
        borehole_stat_row["max_z_borehole_cl"] = deepest_row["soluble_ions_chloride_mg_kg"]
        # Shallow closure: clean shallowest sample, OR an exceeding shallowest sample that sits at z <= 0.5
        borehole_stat_row["shallow_vertical_closure"] = (
            "Yes"
            if (
                shallowest_row["soluble_ions_chloride_mg_kg"] <= chloride_delineation
                or shallowest_row["z"] <= 0.5
            )
            else "No"
        )
        borehole_stat_row["deep_vertical_closure"] = "Yes" if deepest_row["soluble_ions_chloride_mg_kg"] <= chloride_delineation else "No"

        # ---- Impacts
        # Find the shallowest impacted sample, then use the next shallower clean sample as the top of impact.
        # If there is no shallower sample, use 0.
        min_impact_row = group_sorted[group_sorted["soluble_ions_chloride_mg_kg"] > chloride_delineation].head(1)
        if not min_impact_row.empty:
            shallowest_impacted_index = min_impact_row.index[0]
            shallowest_impacted_position = group_sorted.index.get_loc(shallowest_impacted_index)
            if shallowest_impacted_position > 0:
                result_row = group_sorted.iloc[shallowest_impacted_position - 1]
                borehole_stat_row["top_impact"] = result_row["z"]
            else:
                borehole_stat_row["top_impact"] = 0
        else:
            borehole_stat_row["top_impact"] = "NA"

        # Find the deepest impacted sample, then use the next deeper clean sample as the bottom of impact.
        # If the deepest impacted sample is the deepest sample in the borehole, use its z.
        max_impact_row = group_sorted[group_sorted["soluble_ions_chloride_mg_kg"] > chloride_delineation].tail(1)
        if not max_impact_row.empty:
            deepest_impacted_index = max_impact_row.index[0]
            deepest_impacted_position = group_sorted.index.get_loc(deepest_impacted_index)
            if deepest_impacted_position < len(group_sorted) - 1:
                result_row = group_sorted.iloc[deepest_impacted_position + 1]
            else:
                result_row = max_impact_row.iloc[0]
            borehole_stat_row["bottom_impact"] = result_row["z"]
        else:
            borehole_stat_row["bottom_impact"] = "NA"

        # If we have both impact limits, find the diff
        if not min_impact_row.empty and not max_impact_row.empty:
            borehole_stat_row["total_impact_depth"] = round(borehole_stat_row["bottom_impact"] - borehole_stat_row["top_impact"], 2)
        else:
            borehole_stat_row["total_impact_depth"] = "NA"

        # If we have both impact limits, find the continous impact data
        if not min_impact_row.empty and not max_impact_row.empty:
            # Find any rows between borehole_stat_row["bottom_impact"] and borehole_stat_row["top_impact"] where soluble_ions_chloride_mg_kg < chloride_delineation
            continuous_impact = group[
                (group["z"] > borehole_stat_row["top_impact"]) &
                (group["z"] < borehole_stat_row["bottom_impact"]) &
                (group["soluble_ions_chloride_mg_kg"] < chloride_delineation)
            ]
            if continuous_impact.empty:
                borehole_stat_row["continuous_impacts"] = "Yes"
            else:
                borehole_stat_row["continuous_impacts"] = "No"

        borehole_stat_rows.append(borehole_stat_row)

    return borehole_stat_rows

def filter_borehole_data(ctx: Context) -> Context:
    # Get the soil data and Cl guidelines from the input context
    soil_data_filtered = ctx.frames["soil_data_filtered"]
    chloride_guideline = ctx.params.get("chloride_guideline", 100)

    # Filter only needed columns
    borehole_df = soil_data_filtered[borehole_header_columns.keys()]
    borehole_df_display = borehole_df.rename(columns=borehole_header_columns)
    
    # TODO: Maybe add this into the output manifest if still needed
    borehole_df_display = borehole_df_display.round(2)

    borehole_stat_rows = _build_borehole_stat_rows(borehole_df, chloride_guideline)
    # borehole_char_df = pd.DataFrame(borehole_stat_rows, columns=borehole_char_columns.keys()).replace(["NA", "-", "None", None], pd.NA).apply(pd.to_numeric, errors="ignore").convert_dtypes()
    borehole_char_df_display = pd.DataFrame(borehole_stat_rows, columns=borehole_char_columns.keys())
    borehole_char_df_display = borehole_char_df_display.rename(columns=borehole_char_columns)

    ctx.frames["borehole_characteristics"] = borehole_char_df_display
    ctx.frames["borehole_data"] = borehole_df_display

    return ctx




