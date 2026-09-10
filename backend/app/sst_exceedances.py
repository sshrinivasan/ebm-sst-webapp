from .context import Context
import pandas as pd
from .tier1_exceedances import _lookup_mgmt_limit, _exceeds_mgmt, _exceeds_10x_guideline, chemical_to_label_short_map, chemical_group_columns_maps
from .loader import cleaned_name_to_excel_header_map

sst_exceedance_output_columns = {
    "media": "Media",
    "sample_id": "Sample ID",
    "depth_m": "Depth (m)",
    "date": "Date",
    "subarea": "Subarea",
    "apec": "APEC",
    "excavated_replaced": "Excavated/Replaced",
    "exceedance_parameter": "Parameter",
    "label": "Label",
    "chemical_group": "Chemical Group",
    "exceedance_value": "Value",
    "tier1_guideline": "Tier 1 Guideline",
    "tier1_bg": "Tier 1 w BG",
    "tier2_guideline": "Tier 2 Guideline",
    "limiting_guideline": "Limiting Guideline",
    "exceeds_10x_guideline": "10X guideline",
    "mgmt_limit": "Mgmt Limit",
    "exceeds_mgmt": "Exceeds Mgmt Limit",
    "soluble_ions_chloride_mg_kg": "Chloride (mg/kg)",
    "soluble_ions_chloride_mg_l": "Chloride (mg/L)",
}

ab_rz_guideline_df = pd.DataFrame({
    "subarea": pd.Series(dtype="string"),
    "depth": pd.Series(dtype="string"),
    "chloride_guideline": pd.Series(dtype="string"),
})

# Will be an input parameter in the future. For now, hardcoded to a few sample IDs for testing.
# TODO: Make this a user input parameter in the frontend (multiselect) and validate against the available sample IDs.
NPP_APPLIED_SAMPLES = ['BH25-01', 'BH25-02', 'BH25-03']


def _excavated_replaced(comments):
    text = str(comments).lower()
    return "Yes" if ("excavated" in text or "replaced" in text) else "No"

def _to_float_or_none(val):
    if val is None:
        return None
    if isinstance(val, str) and val.strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _lookup_limiting(ctx, param):
    if param in ctx.frames["limiting_df"].columns:
        return ctx.frames["limiting_df"][param].iloc[0]
    return pd.NA

def _lookup_tier2(ctx, param):
    if param in ctx.frames["tier2_guideline_df"].columns:
        return ctx.frames["tier2_guideline_df"][param].iloc[0]
    return pd.NA

def _build_sst_chloride_exceedances(guidelines, scarg_df, df, npp_samples):
    exceedance_rows = []
    cl_removed = scarg_df.copy()

    for _, guide_row in guidelines.iterrows():
        subarea = str(guide_row["Subarea"]).strip()
        depth_parts = guide_row["Depth Range"].split("-")
        depth_min = float(depth_parts[0])
        depth_max = float(depth_parts[1])
        cl_guideline = float(guide_row["Cl Guideline"])

        # Chloride exceedances for this specific subarea and depth
        mask = (
            (df["subarea"].astype(str).str.strip() == subarea)
            & (df["z"] >= depth_min)
            & (df["z"] <= depth_max)
            & (df["soluble_ions_chloride_mg_kg"] > cl_guideline)
        )
        exceeded = df[mask].copy()
        exceeded["guideline_value"] = cl_guideline
        exceeded["exceedance_parameter"] = "soluble_ions_chloride_mg_kg"
        exceedance_rows.append(exceeded)

        # Remove EC exceedances at this subarea+depth since SST Chloride replaces them
        remove_mask = (
            (cl_removed["subarea"].astype(str).str.strip() == subarea)
            & (cl_removed["z"] >= depth_min)
            & (cl_removed["z"] <= depth_max)
            & (cl_removed["exceedance_parameter"] == "general_inorganics_ec_ds_m")
        )
        cl_removed = cl_removed[~remove_mask].reset_index(drop=True)

    # Remove all EC and SAR exceedances between 0-1.5 for samples where NPP is applied
    if npp_samples:
        remove_all_mask = (
            cl_removed["sample_id"].astype(str).str.strip().isin(
                [str(s).strip() for s in npp_samples]
            )
            & (cl_removed["z"] >= 0.0)
            & (cl_removed["z"] <= 1.5)
        )
        cl_removed = cl_removed[~remove_all_mask].reset_index(drop=True)

    return exceedance_rows, cl_removed

def _build_sst_na_sar_exceedances(guidelines, scarg_df, df):
    na_rows = []
    sar_rows = []
    sar_removed = scarg_df.copy()

    for _, guide_row in guidelines.iterrows():
        subarea = str(guide_row["Subarea"]).strip()
        depth_parts = guide_row["Depth Range"].split("-")
        depth_min = float(depth_parts[0])
        depth_max = float(depth_parts[1])

        na_guideline = _to_float_or_none(guide_row["Na Guideline"])
        sar_guideline = _to_float_or_none(guide_row["SAR Guideline"])

        base_mask = (
            (df["subarea"].astype(str).str.strip() == subarea)
            & (df["z"] >= depth_min)
            & (df["z"] <= depth_max)
        )

        # Na exceedances: values ABOVE the guideline (skip if no guideline provided)
        if na_guideline is not None:
            na_exceeded = df[base_mask & (df["soluble_ions_sodium_mg_kg"] > na_guideline)].copy()
            na_exceeded["guideline_value"] = na_guideline
            na_exceeded["exceedance_parameter"] = "soluble_ions_sodium_mg_kg"
            na_rows.append(na_exceeded)

        # SAR exceedances: values ABOVE the guideline (skip if no guideline provided)
        if sar_guideline is not None:
            sar_exceeded = df[base_mask & (df["general_inorganics_sar"] > sar_guideline)].copy()
            sar_exceeded["guideline_value"] = sar_guideline
            sar_exceeded["exceedance_parameter"] = "general_inorganics_sar"
            sar_rows.append(sar_exceeded)

            # SST SAR replaces Tier 1 SCARG SAR at this subarea+depth range
            remove_sar_mask = (
                (sar_removed["subarea"].astype(str).str.strip() == subarea)
                & (sar_removed["z"] >= depth_min)
                & (sar_removed["z"] <= depth_max)
                & (sar_removed["exceedance_parameter"] == "general_inorganics_sar")
            )
            sar_removed = sar_removed[~remove_sar_mask].reset_index(drop=True)

    na_df = pd.concat(na_rows, ignore_index=True) if na_rows else pd.DataFrame()
    sar_df = pd.concat(sar_rows, ignore_index=True) if sar_rows else pd.DataFrame()
    return na_df, sar_df, sar_removed

def _build_rz_exceedances(guidelines, df):
    rows = []
    for _, guide_row in guidelines.iterrows():
        subarea = str(guide_row["subarea"]).strip()
        depth_parts = guide_row["depth"].split("-")
        depth_min = float(depth_parts[0])
        depth_max = float(depth_parts[1])
        rz_cl_guideline = float(guide_row["chloride_guideline"])

        # RZ Cl exceedances: values ABOVE the guideline
        rz_cl_mask = (
            (df["subarea"].astype(str).str.strip() == subarea)
            & (df["z"] >= depth_min)
            & (df["z"] <= depth_max)
            & (df["soluble_ions_chloride_mg_kg"] > rz_cl_guideline)
        )
        rz_cl_exceeded = df[rz_cl_mask].copy()
        rz_cl_exceeded["guideline_value"] = rz_cl_guideline
        rz_cl_exceeded["exceedance_parameter"] = "soluble_ions_chloride_mg_kg"
        rows.append(rz_cl_exceeded)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

def _parse_ph_range(val):
    """Parse a pH guideline of the form '5.3-8.5' into (lower, upper)."""
    parts = str(val).strip().split("-")
    if len(parts) != 2:
        raise ValueError("Unexpected pH guideline format: {0!r}".format(val))
    return float(parts[0]), float(parts[1])


def _build_limit_exceedances(df, guideline_df, compare_cols):
    """Flag values exceeding the per-column guideline in guideline_df (pH is two-sided)."""
    ph_lower_bound, ph_upper_bound = _parse_ph_range(guideline_df["general_inorganics_ph"].iloc[0])

    rows = []
    for col in compare_cols:
        numeric_col = pd.to_numeric(df[col], errors="coerce")

        # pH has both an upper and lower bound; flag values outside the limiting range
        if col == "general_inorganics_ph":
            mask = numeric_col.notna() & ((numeric_col < ph_lower_bound) | (numeric_col > ph_upper_bound))
            exceeded = df[mask].copy()
            exceeded["exceedance_parameter"] = col
            exceeded["guideline_value"] = "{0}-{1}".format(ph_lower_bound, ph_upper_bound)
            rows.append(exceeded)
            continue

        limit_val = guideline_df[col].iloc[0]
        try:
            limit_val = float(limit_val)
        except (ValueError, TypeError):
            continue

        mask = numeric_col > limit_val
        exceeded = df[mask].copy()
        exceeded["exceedance_parameter"] = col
        exceeded["guideline_value"] = limit_val
        rows.append(exceeded)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

def sst_exceedances(ctx: Context) -> Context:
    soil_data_filtered = ctx.frames["soil_data_filtered"]

    # File-derived SST Chloride guidelines (Subarea / Depth Range / Cl Guideline),
    # read from the workbook by the loader's read_sst_guidelines step.
    sst_cl_guide_default_df = ctx.frames.get("sst_cl_guide_default_df")
    if sst_cl_guide_default_df is None:
        ctx.notify("No SST Chloride guideline block found in the workbook.", "warning", "sst_exceedances")
        sst_cl_guide_default_df = pd.DataFrame(columns=["Subarea", "Depth Range", "Cl Guideline"])

    # File-derived SST Na/SAR guidelines (Subarea / Depth Range / Na Guideline /
    # SAR Guideline), read from the workbook by the loader's read_sst_guidelines step.
    sst_na_sar_guide_default_df = ctx.frames.get("sst_na_sar_guide_default_df")
    if sst_na_sar_guide_default_df is None:
        ctx.notify("No SST Na/SAR guideline block found in the workbook.", "warning", "sst_exceedances")
        sst_na_sar_guide_default_df = pd.DataFrame(columns=["Subarea", "Depth Range", "Na Guideline", "SAR Guideline"])

    # SST Chloride exceedances: build a list of rows and a modified SCARG df with EC exceedances removed
    ab_chloride_exceedance_rows, ab_scarg_exceedances_df_cl_removed = _build_sst_chloride_exceedances(
        sst_cl_guide_default_df,
        ctx.frames["scarg_exceedances_df"],
        soil_data_filtered,
        NPP_APPLIED_SAMPLES
    )
    ab_chloride_exceedances_df = pd.concat(ab_chloride_exceedance_rows, ignore_index=True) if ab_chloride_exceedance_rows else pd.DataFrame()

    # SST Na and SAR exceedances: build a list of rows and a modified SCARG df with SAR exceedances removed
    ab_na_exceedances_df, ab_sar_exceedances_df, ab_scarg_exceedances_df_sar_removed = _build_sst_na_sar_exceedances(
        sst_na_sar_guide_default_df,
        ab_scarg_exceedances_df_cl_removed,
        ctx.frames["soil_data_filtered"]
    )

    # RZ exceedances
    ab_rz_exceedances_df = _build_rz_exceedances(ab_rz_guideline_df, ctx.frames["soil_data_filtered"])

    ### --- Tier 2 ----
    limiting_df = ctx.frames["limiting_df"]
    # Skip the column we have already handled, as well as Chloride mg/l, that has no exeedances (but has a limiting value, which is why we manually exclude)
    exclude_cols_t2 = ["soluble_ions_chloride_mg_kg", "soluble_ions_chloride_mg_l", "general_inorganics_ec_ds_m", "general_inorganics_sar", "soluble_ions_sodium_mg_kg"]
    compare_cols = [c for c in ctx.frames["soil_data_filtered"].columns if c in limiting_df.columns and c not in exclude_cols_t2]

    ab_tier1_exceedances_df = _build_limit_exceedances(soil_data_filtered, limiting_df, compare_cols)
    ### end --- Tier 2 ----
    
    # Concat al exceedances tables into a single df for output
    ab_all_exceedances_df = pd.concat([
        ab_scarg_exceedances_df_sar_removed, # SCARG exceedances
        ab_chloride_exceedances_df,  # SST Chloride
        ab_na_exceedances_df, # SST Na
        ab_sar_exceedances_df, # SST SAR
        ab_rz_exceedances_df, # SST Root Zone
        ab_tier1_exceedances_df # limiting guideline for all else
        ],
        ignore_index=True,
    )

    # Add additional columns for display
    chemical_group_map, _ = chemical_group_columns_maps(ctx)
    ab_all_exceedances_df["mgmt_limit"] = (
        ab_all_exceedances_df["exceedance_parameter"].map(lambda p: _lookup_mgmt_limit(ctx, p))
    )

    ab_all_exceedances_df["exceeds_mgmt"] = ab_all_exceedances_df.apply(_exceeds_mgmt, axis=1)
    ab_all_exceedances_df["exceeds_10x_guideline"] = ab_all_exceedances_df.apply(_exceeds_10x_guideline, axis=1)
    ab_all_exceedances_df["exceedance_value"] = pd.to_numeric(
        ab_all_exceedances_df.apply(lambda r: r.get(r["exceedance_parameter"]), axis=1),
        errors="coerce",
    )
    ab_all_exceedances_df["media"] = "Soil"

    ab_all_exceedances_df["excavated_replaced"] = ab_all_exceedances_df["comments"].map(_excavated_replaced)
    ab_all_exceedances_df["label"] = ab_all_exceedances_df["exceedance_parameter"].map(
        lambda v: chemical_to_label_short_map.get(v)
    )
    ab_all_exceedances_df["chemical_group"] = ab_all_exceedances_df["exceedance_parameter"].map(
        lambda v: chemical_group_map.get(v)
    )

    # Get relevant values from Tier 1 exceedances df
    ab_all_tier1_exceedances_df = ctx.frames["tier1_exceedances_df"]
    _key = ["sample_id", "z", "exceedance_parameter"]

    _tier1_lookup = ab_all_tier1_exceedances_df[_key + ["guideline_value", "tier1_bg_guideline"]].drop_duplicates(subset=_key)
    assert _tier1_lookup.duplicated(subset=_key).sum() == 0, "Non-unique keys in tier1 lookup"

    existing_tier1_cols = [
        col for col in ["tier1_guideline", "tier1_bg", "tier1_bg_x", "tier1_bg_y"]
        if col in ab_all_exceedances_df.columns
    ]
    ab_all_exceedances_df = ab_all_exceedances_df.drop(columns=existing_tier1_cols)

    ab_all_exceedances_df = ab_all_exceedances_df.merge(
        _tier1_lookup.rename(columns={"guideline_value": "tier1_guideline", "tier1_bg_guideline": "tier1_bg"}),
        on=_key,
        how="left",
    )

    ab_all_exceedances_df["limiting_guideline"] = ab_all_exceedances_df["exceedance_parameter"].map(lambda p: _lookup_limiting(ctx, p))

    # EC/SAR (SCARG) and Cl/Na (SST) guidelines vary by depth and subarea, so the limiting
    # guideline for those rows is the value that actually governed the exceedance rather
    # than the flat value scraped from the Excel limiting-guideline row.
    _row_specific_params = [
        "general_inorganics_ec_ds_m",
        "general_inorganics_sar",
        "soluble_ions_chloride_mg_kg",
        "soluble_ions_chloride_mg_l",
        "soluble_ions_sodium_mg_kg",
    ]

    # First make the flat limiting values numeric (float) up front. Any
    # non-numeric entry — e.g. the pH "5.3-8.5" range string — becomes NaN. Doing
    # this before the assignment below guarantees the column is float64, so the
    # per-row override lands in a matching dtype (avoids pandas' object->float
    # LossySetitemError).
    ab_all_exceedances_df["limiting_guideline"] = pd.to_numeric(
        ab_all_exceedances_df["limiting_guideline"], errors="coerce"
    )

    # For those params the governing guideline was recorded per-row in
    # "guideline_value" when the exceedance was built (it depends on the row's
    # subarea/depth), so overwrite the flat limiting value with it (also coerced
    # to numeric) for just those rows.
    row_specific = ab_all_exceedances_df["exceedance_parameter"].isin(_row_specific_params)
    ab_all_exceedances_df.loc[row_specific, "limiting_guideline"] = pd.to_numeric(
        ab_all_exceedances_df.loc[row_specific, "guideline_value"], errors="coerce"
    )

    ab_all_exceedances_df["tier2_guideline"] = ab_all_exceedances_df["exceedance_parameter"].map(lambda p: _lookup_tier2(ctx, p))
        
    ab_all_exceedances_df_display = ab_all_exceedances_df[sst_exceedance_output_columns.keys()].rename(columns=sst_exceedance_output_columns)
    ab_all_exceedances_df_display["Parameter"] = ab_all_exceedances_df_display["Parameter"].map(
        lambda v: cleaned_name_to_excel_header_map.get(v, v)
    )
    ab_all_exceedances_df_display["Date"] = pd.to_datetime(
        ab_all_exceedances_df_display["Date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    ab_all_exceedances_df_display = ab_all_exceedances_df_display.fillna("-")

    # Output
    ctx.frames["all_exceedances_df"] = ab_all_exceedances_df
    ctx.frames["all_exceedances_display_df"] = ab_all_exceedances_df_display
    print("SST exceedances complete. Total rows: {0}".format(len(ab_all_exceedances_df)))
    print(len(ab_all_exceedances_df_display.columns))
    print(ab_all_exceedances_df_display.columns)
    return ctx

