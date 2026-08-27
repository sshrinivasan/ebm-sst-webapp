from .context import Context, InputValidationError
import pandas as pd
from .loader import (
    cleaned_to_excel,
    excel_header_to_cleaned_name_map,
    cleaned_name_to_excel_header_map,
)

def _excavated_replaced(comments):
    text = str(comments).lower()
    return "Yes" if ("excavated" in text or "replaced" in text) else "No"

def _lookup_limiting(ctx, param):
    # limiting_df carries cleaned (snake_case) columns, so index by the cleaned
    # param name directly.
    if param in ctx.frames["limiting_df"].columns:
        return ctx.frames["limiting_df"][param].iloc[0]
    return pd.NA

# Add the management limit and 2 other columns, one for 10x guideline, and one for exceeding management limit
def _lookup_mgmt_limit(ctx, cleaned_name):
    excel_header = cleaned_to_excel.get(cleaned_name)
    if excel_header is None or excel_header not in ctx.frames["management_limits_df"].columns:
        return pd.NA
    return ctx.frames["management_limits_df"][excel_header].iloc[0]

def _lookup_tier2(ctx, param):
    # tier2_guideline_df carries cleaned (snake_case) columns, so index by the
    # cleaned param name directly.
    if param in ctx.frames["tier2_guideline_df"].columns:
        return ctx.frames["tier2_guideline_df"][param].iloc[0]
    return pd.NA

def _lookup_tier1_bg(ctx, param):
    # tier1_bg_df (Tier 1 with background) carries Excel-header columns.
    excel_header = cleaned_to_excel.get(param)
    if excel_header is not None and excel_header in ctx.frames["tier1_bg_df"].columns:
        return ctx.frames["tier1_bg_df"][excel_header].iloc[0]
    return pd.NA

def _exceeds_mgmt(row):
    limit = row["mgmt_limit"]
    param = row["exceedance_parameter"]
    if pd.isna(limit) or param not in row.index:
        return "No"
    value = pd.to_numeric(row[param], errors="coerce")
    try:
        limit_num = float(limit)
    except (ValueError, TypeError):
        return "No"
    if pd.isna(value):
        return "No"
    return "Yes" if value > limit_num else "No"

def _exceeds_10x_guideline(row):
    limit = row["guideline_value"]
    param = row["exceedance_parameter"]
    value = pd.to_numeric(row[param], errors="coerce")
    try:
        limit_num = float(limit)
    except (ValueError, TypeError):
        return "No"

    return "Yes" if value > 10.0 * limit_num else "No"

# Mapping cleaned columns to short labels
chemical_to_label_short_map = {'general_inorganics_ph': 'pH',
 'general_inorganics_ec_ds_m': 'EC',
 'general_inorganics_sar': 'SAR',
 'soluble_ions_chloride_mg_l': 'Cl',
 'soluble_ions_sodium_mg_l': 'Na',
 'soluble_ions_chloride_mg_kg': 'Cl',
 'soluble_ions_sodium_mg_kg': 'Na',
 'soluble_ions_chloride_meq_l': 'Cl',
 'soluble_ions_sodium_meq_l': 'Na',
 'hydrocarbons_benzene_mg_kg': 'B',
 'hydrocarbons_toluene_mg_kg': 'T',
 'hydrocarbons_ethylbenzene_mg_kg': 'E',
 'hydrocarbons_xylenes_mg_kg': 'X',
 'hydrocarbons_f1_c6_c10_btex_mg_kg': 'F1',
 'hydrocarbons_f2_c10_c16_mg_kg': 'F2',
 'hydrocarbons_f3_c16_c34_mg_kg': 'F3',
 'hydrocarbons_f4_c34_c50_mg_kg': 'F4',
 'hydrocarbons_f4g_c34_mg_kg': 'F4G',
 'non_carcinogenic_pahs_acenaphthene_mg_kg': 'Acn',
 'non_carcinogenic_pahs_acenaphthylene_mg_kg': 'Acny',
 'non_carcinogenic_pahs_anthracene_mg_kg': 'Ant',
 'non_carcinogenic_pahs_fluoranthene_mg_kg': 'Flra',
 'non_carcinogenic_pahs_fluorene_mg_kg': 'Flu',
 'non_carcinogenic_pahs_naphthalene_mg_kg': 'Naph',
 'non_carcinogenic_pahs_methylnapthalene_2_mg_kg': 'Cl',
 'non_carcinogenic_pahs_phenanthrene_mg_kg': 'Phe',
 'non_carcinogenic_pahs_pyrene_mg_kg': 'Pyr',
 'carcinogenic_pahs_benzo_a_anthracene_mg_kg': 'B(a)A',
 'carcinogenic_pahs_benzo_b_j_fluoranthene_mg_kg': 'B(bj)F',
 'carcinogenic_pahs_benzo_k_fluoranthene_mg_kg': 'B(k)F',
 'carcinogenic_pahs_benzo_g_h_i_perylene_mg_kg': 'B(ghi)P',
 'carcinogenic_pahs_benzo_a_pyrene_mg_kg': 'B(a)P',
 'carcinogenic_pahs_chrysene_mg_kg': 'Chry',
 'carcinogenic_pahs_dibenz_a_h_anthracene_mg_kg': 'D(ah)A',
 'carcinogenic_pahs_indeno_1_2_3_c_d_pyrene_mg_kg': 'I(cd)P',
 'carcinogenic_pahs_carcinogenic_pahs_iacr_fine_mg_kg': 'Cl',
 'carcinogenic_pahs_carcinogenic_pahs_iacr_coarse_mg_kg': 'Cl',
 'carcinogenic_pahs_carcinogenic_pahs_tpe_mg_kg': 'Cl',
 'carcinogenic_pahs_pah_total_for_sediment_mg_kg': 'PAH SED',
 'other_organics_ethylene_glycol_mg_kg': 'EG',
 'other_organics_diethylene_glycol_mg_kg': 'DEG',
 'other_organics_triethylene_glycol_mg_kg': 'TEG',
 'other_organics_methanol_mg_kg': 'MeOH',
 'other_organics_phenol_mg_kg': 'PhOH',
 'metals_antimony_mg_kg': 'Sb',
 'metals_arsenic_inorganic_mg_kg': 'Ar',
 'metals_barium_non_barite_mg_kg': 'Ba',
 'metals_barite_barium_mg_kg': 'BaSO4',
 'metals_extractable_barium_mg_kg': 'Ba(Ext)',
 'metals_beryllium_mg_kg': 'Be',
 'metals_boron_saturated_paste_mg_l': 'B(HWS)',
 'metals_boron_hot_water_soluble_mg_kg': 'B(SP)',
 'metals_cadmium_mg_kg': 'Cd',
 'metals_chromium_hexavalent_mg_kg': 'Cr(6)',
 'metals_chromium_total_mg_kg': 'Cr(Tot)',
 'metals_cobalt_mg_kg': 'Co',
 'metals_copper_mg_kg': 'Cu',
 'metals_lead_mg_kg': 'Pb',
 'metals_manganese_mg_kg': 'Mn',
 'metals_mercury_inorganic_mg_kg': 'Hg',
 'metals_molybdenum_mg_kg': 'Mo',
 'metals_nickel_mg_kg': 'Ni',
 'metals_selenium_mg_kg': 'Se',
 'metals_silver_mg_kg': 'Ag',
 'metals_thallium_mg_kg': 'Tl',
 'metals_tin_mg_kg': 'Sn',
 'metals_uranium_mg_kg': 'U',
 'metals_vanadium_mg_kg': 'V',
 'metals_zinc_mg_kg': 'Zn'}

# Map columns to chemical names and vice versa
def chemical_group_columns_maps(ctx: Context) -> Context:
    chemical_group_map = {}
    for col in ctx.frames["soil_data_filtered"].columns:
        if col in ("general_inorganics_ph", "general_inorganics_ec_ds_m", "general_inorganics_sar"):
            chemical_group_map[col] = "Salinity"
        elif col.startswith("soluble_ions_chloride"):
            chemical_group_map[col] = "Chloride"
        elif col.startswith("soluble_ions_sodium"):
            chemical_group_map[col] = "Sodium"
        elif col.startswith("hydrocarbons_") and (
            col in (
                "hydrocarbons_benzene_mg_kg",
                "hydrocarbons_toluene_mg_kg",
                "hydrocarbons_ethylbenzene_mg_kg",
                "hydrocarbons_xylenes_mg_kg",
            )
            or col.startswith("hydrocarbons_f1_")
            or col.startswith("hydrocarbons_f2_")
            or col.startswith("hydrocarbons_f3_")
            or col.startswith("hydrocarbons_f4_")
            or col.startswith("hydrocarbons_f4g_")
        ):
            chemical_group_map[col] = "Hydrocarbons"
        elif col.startswith("non_carcinogenic_pahs_") or col.startswith("carcinogenic_pahs_"):
            chemical_group_map[col] = "PAHs"
        elif col.startswith("other_organics_"):
            chemical_group_map[col] = "Other Organics"
        elif col.startswith("metals_"):
            chemical_group_map[col] = "Metals"

    chemical_group_to_columns_map = {}
    for col, group in chemical_group_map.items():
        chemical_group_to_columns_map.setdefault(group, []).append(col)
    return chemical_group_map, chemical_group_to_columns_map

def _build_scarg_exceedances(guidelines, df):
    rows = []
    for _, row in guidelines.iterrows():
        depth_min, depth_max = (float(p) for p in str(row["Depth"]).split("-"))
        ec_guideline = float(row["EC Guideline"])
        sar_guideline = float(row["SAR Guideline"])

        # TODO: Handle the boundary case.
        for param, guideline in (
            ("general_inorganics_ec_ds_m", ec_guideline),
            ("general_inorganics_sar", sar_guideline),
        ):
            mask = (
                (df["z"] >= depth_min)
                & (df["z"] < depth_max)
                & (df[param] > guideline)
            )
            exceeded = df[mask].copy()
            exceeded["guideline_value"] = guideline
            exceeded["exceedance_parameter"] = param
            rows.append(exceeded)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

def _parse_ph_range(val):
    """Parse a pH guideline of the form '5.3-8.5' into (lower, upper)."""
    parts = str(val).strip().split("-")
    if len(parts) != 2:
        raise ValueError("Unexpected pH guideline format: {0!r}".format(val))
    return float(parts[0]), float(parts[1])

def _build_limit_exceedances(df, guideline_df, compare_cols):
    """Flag values exceeding the per-column guideline in guideline_df (pH is two-sided)."""
    # guideline_df is sliced with Excel-header columns in the loader; index it with
    # the cleaned names the rest of this function (and compare_cols) uses.
    guideline_df = guideline_df.rename(columns=excel_header_to_cleaned_name_map)
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
    
def tier1_exceedances(ctx: Context) -> Context:
    
    soil_data_filtered = ctx.frames["soil_data_filtered"]
    limiting_df = ctx.frames["limiting_df"]
    limiting_tier1_guideline_df = ctx.frames["limiting_tier1_guideline_df"]
    
    # EC and SAR exceedances using SCARG guidelines
    ab_scarg_exceedances_df = _build_scarg_exceedances(ctx.frames["scarg_guidelines_df"], ctx.frames["soil_data_filtered"]) 

    # Use the SCARG exceedances "ab_scarg_exceedances_df"
    # for EC and SAR, and using the limiting value for all others.
    exclude_cols_t1 = ["general_inorganics_ec_ds_m", "general_inorganics_sar"]
    # limiting_df has cleaned (snake_case) columns, so test membership directly.
    compare_cols_t1 = [
        c for c in soil_data_filtered.columns
        if c in limiting_df.columns and c not in exclude_cols_t1
    ]

    # Create a df of all tier1 exceedances except SCARG
    ab_tier1_only_exceedances_df = _build_limit_exceedances(
        soil_data_filtered, limiting_tier1_guideline_df, compare_cols_t1
    )

    # Combine with SCARG exeedances for EC and SAR
    ab_all_tier1_exceedances_df = pd.concat([
        ab_scarg_exceedances_df,
        ab_tier1_only_exceedances_df],
        ignore_index=True,
    )

    # Add additional columns for display
    ab_all_tier1_exceedances_df["media"] = "Soil"
    ab_all_tier1_exceedances_df["exceedance_value"] = pd.to_numeric(
        ab_all_tier1_exceedances_df.apply(lambda r: r.get(r["exceedance_parameter"]), axis=1),
        errors="coerce",
    )

    ab_all_tier1_exceedances_df["excavated_replaced"] = ab_all_tier1_exceedances_df["comments"].map(_excavated_replaced)
    ab_all_tier1_exceedances_df["label"] = ab_all_tier1_exceedances_df["exceedance_parameter"].map(
        lambda v: chemical_to_label_short_map.get(v)
    )
    # TODO: Check this pattern if a good idea
    chemical_group_map, chemical_group_to_columns_map = chemical_group_columns_maps(ctx)
    
    ab_all_tier1_exceedances_df["chemical_group"] = ab_all_tier1_exceedances_df["exceedance_parameter"].map(
        lambda v: chemical_group_map.get(v)
    )
    ab_all_tier1_exceedances_df["limiting_guideline"] = ab_all_tier1_exceedances_df["exceedance_parameter"].map(
        lambda p: _lookup_limiting(ctx, p)
    )
    ab_all_tier1_exceedances_df["tier1_bg_guideline"] = ab_all_tier1_exceedances_df["exceedance_parameter"].map(
        lambda p: _lookup_tier1_bg(ctx, p)
    )

    # EC and SAR Tier 1 guidelines are defined by SCARG and are depth-dependent, so the
    # limiting guideline for those rows is the SCARG value that governed the exceedance
    # rather than the flat value scraped from the Excel limiting-guideline row.
    _scarg_params = ["general_inorganics_ec_ds_m", "general_inorganics_sar"]
    _scarg_mask = ab_all_tier1_exceedances_df["exceedance_parameter"].isin(_scarg_params)
    ab_all_tier1_exceedances_df.loc[_scarg_mask, "limiting_guideline"] = ab_all_tier1_exceedances_df.loc[
        _scarg_mask, "guideline_value"
    ]
    ab_all_tier1_exceedances_df["tier2_guideline"] = ab_all_tier1_exceedances_df["exceedance_parameter"].map(
        lambda p: _lookup_tier2(ctx, p)
    )
    ab_all_tier1_exceedances_df["mgmt_limit"] = ab_all_tier1_exceedances_df["exceedance_parameter"].map(
        lambda p: _lookup_mgmt_limit(ctx, p)
    )
    ab_all_tier1_exceedances_df["exceeds_mgmt"] = ab_all_tier1_exceedances_df.apply(_exceeds_mgmt, axis=1)
    ab_all_tier1_exceedances_df["exceeds_10x_guideline"] = ab_all_tier1_exceedances_df.apply(_exceeds_10x_guideline, axis=1)
    tier1_exceedance_output_columns = {
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
        "guideline_value": "Tier 1 Guideline",
        "tier1_bg_guideline": "Tier 1 w BG",
        "tier2_guideline": "Tier 2 Guideline",
        "limiting_guideline": "Limiting Guideline",
        "exceeds_10x_guideline": "10X guideline",
        "mgmt_limit": "Mgmt Limit",
        "exceeds_mgmt": "Exceeds Mgmt Limit",
        "soluble_ions_chloride_mg_kg": "Chloride (mg/kg)",
        "soluble_ions_chloride_mg_l": "Chloride (mg/L)",
    }

    ab_all_tier1_exceedances_df_display = ab_all_tier1_exceedances_df[tier1_exceedance_output_columns.keys()].rename(columns=tier1_exceedance_output_columns)
    ab_all_tier1_exceedances_df_display["Parameter"] = ab_all_tier1_exceedances_df_display["Parameter"].map(
        lambda v: cleaned_name_to_excel_header_map.get(v, v)
    )
    ab_all_tier1_exceedances_df_display["Date"] = pd.to_datetime(
        ab_all_tier1_exceedances_df_display["Date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    ab_all_tier1_exceedances_df_display = ab_all_tier1_exceedances_df_display.fillna("-")
    
    # Add tier 1 exceedances to the frame
    ctx.frames["tier1_exceedances_df"] = ab_all_tier1_exceedances_df
    ctx.frames["tier1_exceedances_display_df"] = ab_all_tier1_exceedances_df_display
    ctx.frames["scarg_exceedances_df"] = ab_scarg_exceedances_df
    return ctx



