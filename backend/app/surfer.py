from .context import Context, InputValidationError
import pandas as pd
from .tier1_exceedances import chemical_group_columns_maps, chemical_to_label_short_map
from .loader import display_name_to_cleaned_name_map

surfer_figure_groups = {
    "Tier 1 Salinity": ["Salinity"],
    "Site-Specific Metals": ["Metals"],
    "Site-Specific Organics": ['Hydrocarbons', 'PAHs', 'Other Organics'],
    "Site-Specific Salinity": ['Salinity', 'Chloride', 'Sodium'],
    "All Site-Specific Exceedances": ['Salinity', 'Chloride', 'Sodium', 'Hydrocarbons', 'PAHs', 'Other Organics', 'Metals']
}
surfer_output_headers = {
    "sample_id": "Borehole ID", #A
    "northing": "Northing", #B
    "easting": "Easting", #C
    "borehole_age": "Recent SampleID Type", #D
    "borehole_type": "Historical Sample ID type and WC", #E
    "user_defined_f": "All Sample ID type", #F
    "user_defined_g": "Removed/Damaged ColG", #G

    # Salinity
    "tier_1_salinity_category_depth_1": "Tier 1 S1 Salinity", #H
    "tier_1_salinity_depth_1": "LABEL S1 Salinity", #I
    "tier_1_salinity_category_depth_2": "Tier 1 S2 Salinity", #H
    "tier_1_salinity_depth_2": "LABEL S2 Salinity", #I
    "tier_1_salinity_category_depth_3": "Tier 1 S3 Salinity", #H
    "tier_1_salinity_depth_3": "LABEL S3 Salinity", #I
    "tier_1_salinity_category_depth_4": "Tier 1 S4 Salinity", #H
    "tier_1_salinity_depth_4": "LABEL S4 Salinity", #I

    # Metals
    "site_specific_metals_category_depth_1": "Site-specific S1 Metals",
    "site_specific_metals_depth_1": "LABEL S1 Metals", 
    "site_specific_metals_category_depth_2": "Site-specific S2 Metals",
    "site_specific_metals_depth_2": "LABEL S2 Metals", 
    "site_specific_metals_category_depth_3": "Site-specific S3 Metals",
    "site_specific_metals_depth_3": "LABEL S3 Metals", 
    "site_specific_metals_category_depth_4": "Site-specific S4 Metals",
    "site_specific_metals_depth_4": "LABEL S4 Metals", 

    # Organics
    "site_specific_organics_category_depth_1": "Site-specific S1 Organics",
    "site_specific_organics_depth_1": "LABEL S1 Organics",
    "site_specific_organics_category_depth_2": "Site-specific S2 Organics",
    "site_specific_organics_depth_2": "LABEL S2 Organics",
    "site_specific_organics_category_depth_3": "Site-specific S3 Organics",
    "site_specific_organics_depth_3": "LABEL S3 Organics",
    "site_specific_organics_category_depth_4": "Site-specific S4 Organics",
    "site_specific_organics_depth_4": "LABEL S4 Organics",

    # SST Salinity
    "site_specific_salinity_category_depth_1": "Site-specific S1 Salinity",
    "site_specific_salinity_depth_1": "LABEL S1 SST Salinity",
    "site_specific_salinity_category_depth_2": "Site-specific S2 Salinity",
    "site_specific_salinity_depth_2": "LABEL S2 SST Salinity",
    "site_specific_salinity_category_depth_3": "Site-specific S3 Salinity",
    "site_specific_salinity_depth_3": "LABEL S3 SST Salinity",
    "site_specific_salinity_category_depth_4": "Site-specific S4 Salinity",
    "site_specific_salinity_depth_4": "LABEL S4 SST Salinity",

    # All exceedances
    "all_site_specific_exceedances_category_depth_1": "All Site-specific exc. S1 Residuals",
    "all_site_specific_exceedances_depth_1": "LABEL S1  Residuals",
    "all_site_specific_exceedances_category_depth_2": "All Site-specific exc. S2 Residuals",
    "all_site_specific_exceedances_depth_2": "LABEL S2  Residuals",
    "all_site_specific_exceedances_category_depth_3": "All Site-specific exc. S3 Residuals",
    "all_site_specific_exceedances_depth_3": "LABEL S3  Residuals",
    "all_site_specific_exceedances_category_depth_4": "All Site-specific exc. S4 Residuals",
    "all_site_specific_exceedances_depth_4": "LABEL S4  Residuals",

    # Parameter
    "surfer_parameter_depth_1": "Max Conc. Slice 1",
    "surfer_parameter_depth_2": "Max Conc. Slice 2",
    "surfer_parameter_depth_3": "Max Conc. Slice 3",
    "surfer_parameter_depth_4": "Max Conc. Slice 4",
    "surfer_parameter_depth_5": "Max Conc. Slice 5",
    "surfer_parameter_depth_6": "Max Conc. Slice 6",
    "surfer_parameter_depth_7": "Max Conc. Slice 7",
    "surfer_parameter_depth_8": "Max Conc. Slice 8",
}

# Given a category like "Salinity", see if we have an exceedane for a specific borehole
def get_exceedances_for_borehole(chemical_group_to_columns_map, category, exceedance_df, borehole_id, depth=None):
    columns = chemical_group_to_columns_map.get(category, [])
    if depth is not None:
        exceedance_df = exceedance_df[exceedance_df["z"] <= depth]
    bh_rows = exceedance_df[exceedance_df["sample_id"] == borehole_id]
    found = []
    for col in columns:
        if (bh_rows["exceedance_parameter"] == col).any():
            found.append(col)
    return found


# Check if data is available. True if available
def check_data_availability(chemical_group_to_columns_map, analytical_df, category, borehole_id):
    columns = [
        c for c in chemical_group_to_columns_map.get(category, [])
        if c in analytical_df.columns
    ]
    if not columns:
        return False

    bh_rows = analytical_df[analytical_df["sample_id"] == borehole_id]
    if bh_rows.empty or bh_rows[columns].isna().all().all():
        return False

    return True

# ab_all_exceedances_df = Tier 1 exceedances
# ab_site_specific_exceedances_df_display = SS exceedances
# Tier 1 Salinity categories:
# 1 = All samples pass Tier 1
# 2 = Any sample fails Tier 1 and Tier 1 w BG
# 3 = Any sample fails Tier 1 but passes Tier 1 w BG
# 4 = All samples have No Data
def get_borehole_exceedance_category_salinity(
    borehole_id,
    chemical_categories,
    chemical_group_to_columns_map,
    analytical_df=None,
    tier1_exceedance_df=None,
    tier1_bg_df=None,
    all_exceedance_df=None,
):
    if isinstance(chemical_categories, str):
        chemical_categories = [chemical_categories]

    columns = []
    for chemical_category in chemical_categories:
        columns.extend(chemical_group_to_columns_map.get(chemical_category, []))
    columns = list(dict.fromkeys(columns))

    available_columns = [c for c in columns if c in analytical_df.columns]
    bh_analytical_rows = analytical_df[analytical_df["sample_id"] == borehole_id]

    # All samples have No Data
    if not available_columns or bh_analytical_rows.empty or bh_analytical_rows[available_columns].isna().all().all():
        return 4

    # Check if there is a Tier 1 exceedance for this borehole
    tier1_bh = tier1_exceedance_df[
        (tier1_exceedance_df["sample_id"] == borehole_id)
        & (tier1_exceedance_df["exceedance_parameter"].isin(columns))
    ]
    tier1_hit = not tier1_bh.empty

    tier1_bg = tier1_bg_df  # already cleaned (snake_case) columns
    tier1_bg_hit = False
    for _, row in tier1_bh.iterrows():
        param = row["exceedance_parameter"]
        bg = tier1_bg[param].iloc[0] if param in tier1_bg.columns else None
        value = pd.to_numeric(row.get("exceedance_value"), errors="coerce")
        if pd.isna(bg) or pd.isna(value):
            tier1_bg_hit = True
            break
        try:
            if isinstance(bg, str) and "-" in bg:
                lo, hi = [float(x.strip()) for x in bg.split("-", 1)]
                if value < lo or value > hi:
                    tier1_bg_hit = True
                    break
            elif value > float(bg):
                tier1_bg_hit = True
                break
        except (ValueError, TypeError):
            tier1_bg_hit = True
            break

    # all samples pass T1
    if not tier1_hit:
        return 1

    # Fails T1 and Tier 1 w BG
    if tier1_bg_hit:
        return 2

    # FAILS T1, PASSES T1 with BG
    return 3
   
# Categories:
# 1 = All samples pass Tier 1
# 2 = Any sample fails the limiting SRG (still in site-specific exceedances)
# 3 = Any sample fails Tier 1 but passes Tier 1 w BG
# 4 = All samples have No Data
# 6 = Any sample fails Tier 1 and Tier 1 w BG but passes the limiting SRG
def get_borehole_exceedance_category_non_salinity(
    borehole_id,
    chemical_categories,
    chemical_group_to_columns_map,
    analytical_df=None,
    tier1_exceedance_df=None,
    tier1_bg_df=None,
    all_exceedance_df=None,
):
    if isinstance(chemical_categories, str):
        chemical_categories = [chemical_categories]

    columns = []
    for chemical_category in chemical_categories:
        columns.extend(chemical_group_to_columns_map.get(chemical_category, []))
    columns = list(dict.fromkeys(columns))

    available_columns = [c for c in columns if c in analytical_df.columns]
    bh_analytical_rows = analytical_df[analytical_df["sample_id"] == borehole_id]

    # 4: No Data
    if not available_columns or bh_analytical_rows.empty or bh_analytical_rows[available_columns].isna().all().all():
        return 4

    # 1: All samples pass Tier 1
    tier1_bh = tier1_exceedance_df[
        (tier1_exceedance_df["sample_id"] == borehole_id)
        & (tier1_exceedance_df["exceedance_parameter"].isin(columns))
    ]
    if tier1_bh.empty:
        return 1

    # 2: Any sample fails the limiting SRG
    all_bh = all_exceedance_df[
        (all_exceedance_df["sample_id"] == borehole_id)
        & (all_exceedance_df["exceedance_parameter"].isin(columns))
    ]
    if not all_bh.empty:
        return 2

    # Fails Tier 1 but passes limiting SRG: check against Tier 1 w BG
    tier1_bg = tier1_bg_df  # already cleaned (snake_case) columns
    tier1_bg_hit = False
    for _, row in tier1_bh.iterrows():
        param = row["exceedance_parameter"]
        bg = tier1_bg[param].iloc[0] if param in tier1_bg.columns else None
        value = pd.to_numeric(row.get("exceedance_value"), errors="coerce")
        if pd.isna(bg) or pd.isna(value):
            tier1_bg_hit = True
            break
        try:
            if isinstance(bg, str) and "-" in bg:
                lo, hi = [float(x.strip()) for x in bg.split("-", 1)]
                if value < lo or value > hi:
                    tier1_bg_hit = True
                    break
            elif value > float(bg):
                tier1_bg_hit = True
                break
        except (ValueError, TypeError):
            tier1_bg_hit = True
            break

    # 6: Fails Tier 1 and Tier 1 w BG but passes limiting SRG
    if tier1_bg_hit:
        return 6

    # 3: Fails Tier 1 but passes Tier 1 w BG
    return 3



def surfer_routine_output(ctx: Context) -> Context:
    soil_data_filtered = ctx.frames["soil_data_filtered"]
    chemical_group_map, chemical_group_to_columns_map = chemical_group_columns_maps(ctx)

    # Make the Surfer inputs available for the body of this routine.
    # Table params -> DataFrame frames (columns as declared in params.py).
    ctx.frames["surfer_bh_classification"] = pd.DataFrame(
        ctx.params.get("surfer_bh_classification") or []
    )
    ctx.frames["surfer_parameter_group_depths"] = pd.DataFrame(
        ctx.params.get("surfer_parameter_group_depths") or []
    )
    ctx.frames["surfer_standard_figure_depths"] = pd.DataFrame(
        ctx.params.get("surfer_standard_figure_depths") or []
    )

    # Scalar params (kept in ctx.params; surfaced here for convenience).
    bh_cutoff_date = ctx.params.get("bh_cutoff_date") or ""
    surfer_parameter_group = ctx.params.get("surfer_parameter_group") or ""
    # Whether depth-interval bounds are inclusive (Surfer tab toggles).
    surfer_include_left = bool(ctx.params.get("surfer_include_left", True))
    surfer_include_right = bool(ctx.params.get("surfer_include_right", True))

    # Frames the Surfer routine consumes (all already produced earlier in the
    # pipeline, and all carrying cleaned snake_case columns).
    surfer_bh_classification = ctx.frames["surfer_bh_classification"]
    surfer_parameter_depths = ctx.frames["surfer_parameter_group_depths"]
    surfer_chemical_depths = ctx.frames["surfer_standard_figure_depths"]
    tier1_exceedance_df = ctx.frames["tier1_exceedances_df"]
    site_specific_exceedance_df = ctx.frames["site_specific_tier1_exceedances_df"]
    tier1_bg_df = ctx.frames["tier1_bg_df"]

    surfer_parameter_col = display_name_to_cleaned_name_map.get(surfer_parameter_group, surfer_parameter_group)
    surfer_parameter_depth_cols = list(surfer_parameter_depths.columns)[:8]
    surfer_chemical_depth_cols = [c for c in surfer_chemical_depths.columns if c != "Chemical Group"][:4]


    def _safe_key(value):
        return str(value).strip().lower().replace("-", " ").replace("/", " ").replace(" ", "_")


    def _depth_interval_mask(df, depth_value):
        if pd.isna(depth_value) or str(depth_value).strip() == "":
            return None
        lower, upper = [float(x.strip()) for x in str(depth_value).split("-", 1)]
        depth_values = pd.to_numeric(df["z"], errors="coerce")
        left_mask = depth_values >= lower if surfer_include_left else depth_values > lower
        right_mask = depth_values <= upper if surfer_include_right else depth_values < upper
        return left_mask & right_mask


    surfer_output_rows = []

    for sample_id, group in soil_data_filtered.groupby('sample_id'):
        row_data = {}
        row_data["sample_id"] = sample_id

        # ---- Northing and Easting
        northing = group["x"].iloc[0]
        easting = group["y"].iloc[0]
        row_data["northing"] = northing
        row_data["easting"] = easting

        # ---- Borehole age
        sample_date = pd.to_datetime(group["date"].iloc[0])
        if pd.to_datetime(bh_cutoff_date) > sample_date:
            row_data["borehole_age"] = "1"
        else:
            row_data["borehole_age"] = "2"

        # ---- Borehole type
        borehole_type = None
        for modifier, classification in zip(
            surfer_bh_classification['Modifier'],
            surfer_bh_classification['Surfer Classification'],
        ):
            if str(sample_id).startswith(modifier):
                borehole_type = classification
        if not borehole_type:
            borehole_type = "-"
        row_data["borehole_type"] = borehole_type

        # ---- User defined column G: whether replaced, excavated etc. Check wih Michelle
        row_data["user_defined_f"] = "TODO"
        row_data["user_defined_g"] = "TODO"

        # Chemical Groups
        for _, chemical_depth_row in surfer_chemical_depths.iterrows():
            figure_group = chemical_depth_row.get("Chemical Group")
            chemical_categories = surfer_figure_groups.get(figure_group, [])
            combined_columns = []
            for chemical_category in chemical_categories:
                combined_columns.extend(chemical_group_to_columns_map.get(chemical_category, []))

            for i in range(4):
                key = f"{_safe_key(figure_group)}_depth_{i + 1}"
                category_key = f"{_safe_key(figure_group)}_category_depth_{i + 1}"
                if i >= len(surfer_chemical_depth_cols):
                    row_data[key] = "-"
                    row_data[category_key] = "-"
                    continue

                depth_value = chemical_depth_row.get(surfer_chemical_depth_cols[i])
                
                # Select either Tier 1 or site-specific exceedances dataframe
                exceedance_source_df = tier1_exceedance_df if figure_group == "Tier 1 Salinity" else site_specific_exceedance_df
                
                # Depth masks
                depth_mask = _depth_interval_mask(exceedance_source_df, depth_value)
                tier1_depth_mask = _depth_interval_mask(tier1_exceedance_df, depth_value)
                all_depth_mask = _depth_interval_mask(site_specific_exceedance_df, depth_value)
                analytical_depth_mask = _depth_interval_mask(soil_data_filtered, depth_value)
                
                if depth_mask is None:
                    row_data[key] = "-"
                    row_data[category_key] = "-"
                    continue
                
                # Get the exceedance category number for this chemical group
                # TODO: Salinity uses a different numbering scheme, make a special case
                depth_exceedance_df = exceedance_source_df[depth_mask]
                
                if figure_group == "Tier 1 Salinity":
                    row_data[category_key] = get_borehole_exceedance_category_salinity(
                        sample_id,
                        chemical_categories,
                        chemical_group_to_columns_map,
                        analytical_df=soil_data_filtered[analytical_depth_mask],
                        tier1_exceedance_df=tier1_exceedance_df[tier1_depth_mask],
                        tier1_bg_df=tier1_bg_df,
                        all_exceedance_df=site_specific_exceedance_df[all_depth_mask],
                    )
                else:
                    # TODO: do this
                    row_data[category_key] = get_borehole_exceedance_category_non_salinity(
                        sample_id,
                        chemical_categories,
                        chemical_group_to_columns_map,
                        analytical_df=soil_data_filtered[analytical_depth_mask],
                        tier1_exceedance_df=tier1_exceedance_df[tier1_depth_mask],
                        tier1_bg_df=tier1_bg_df,
                        all_exceedance_df=site_specific_exceedance_df[all_depth_mask],
                    )

                found = []
                for chemical_category in chemical_categories:
                    found.extend(get_exceedances_for_borehole(
                        chemical_group_to_columns_map, chemical_category,
                        depth_exceedance_df, sample_id,
                    ))

                found = [col for col in combined_columns if col in set(found)]
                labels = list(dict.fromkeys(chemical_to_label_short_map.get(col, col) for col in found))
                row_data[key] = ", ".join(labels) if labels else "-"

        # ---- Selected Surfer parameter max values by depth interval
        # Cols AV to BC
        depth_numeric = pd.to_numeric(group["z"], errors="coerce")
        parameter_values = pd.to_numeric(group[surfer_parameter_col], errors="coerce") if surfer_parameter_col in group.columns else pd.Series(index=group.index, dtype="float64")

        for i in range(8):
            key = f"surfer_parameter_depth_{i + 1}"
            if i >= len(surfer_parameter_depth_cols):
                row_data[key] = "-"
                continue

            depth_value = surfer_parameter_depths[surfer_parameter_depth_cols[i]].iloc[0]
            if pd.isna(depth_value) or str(depth_value).strip() == "":
                row_data[key] = "-"
                continue

            lower, upper = [float(x.strip()) for x in str(depth_value).split("-", 1)]
            left_mask = depth_numeric >= lower if surfer_include_left else depth_numeric > lower
            right_mask = depth_numeric <= upper if surfer_include_right else depth_numeric < upper
            mask = left_mask & right_mask
            max_value = parameter_values[mask].max()
            row_data[key] = "-" if pd.isna(max_value) else max_value

        surfer_output_rows.append(row_data)

    surfer_output_df = pd.DataFrame(surfer_output_rows)
    # Keep the compiled Surfer input frame on the context for display /
    # export (pipelines serialize ctx.frames; writes to the working dir are
    # avoided for the containerized app).
    ctx.frames["surfer_output"] = surfer_output_df
    surfer_output_df_display = surfer_output_df.rename(columns=surfer_output_headers)
    surfer_output_df_display = surfer_output_df_display.where(pd.notna(surfer_output_df_display), "")
    surfer_output_df_display = surfer_output_df_display.replace("-", "")
    ctx.frames["surfer_output_display"] = surfer_output_df_display
    return ctx
