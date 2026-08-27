"""Read and clean the Soil Analytical File.

All extraction/cleaning steps that produce the analysis-ready dataframes live
here, ported verbatim from the SST notebook's "Read soil data" section:

  load(ctx)                -> soil_df / soil_data_filtered / soil_df_keep_low_detect
                              + all guideline rows (limiting, management limits,
                              tier1-with-bg, limiting-tier1, tier2)          (cell 31/34)
  drop_duplicate_rows(ctx) -> enforce one row per (sample_id, z)            (cell 36)
  convert_units(ctx)       -> complete soluble-ion units on soil_data_filtered (cell 41)
  average_duplicates(ctx)  -> soil_df_averaged (1-1.5 m dupes averaged)     (cell 45-49)
"""
from __future__ import annotations

import re

import pandas as pd
from collections import OrderedDict

from .context import Context


def remove_signs(x):
    """int/float -> float; '<4.5' -> 4.5; '-' (or other strings) -> None."""
    if isinstance(x, (int, float)):
        return float(x)
    elif "-" in x:
        return None
    elif "<" in x:
        return float(x.strip().replace("<", ""))
    else:
        return None


def remove_signs_keep_low_detect(x):
    """Like remove_signs but keeps the '<' low-detect strings intact; numbers are
    just rounded. Used only for the final 'split table' workflow."""
    if isinstance(x, (int, float)):
        return round(float(x), 2)
    else:
        return x


def _extract_guideline_row(soil_df_full: pd.DataFrame, phrases: list[str]) -> pd.DataFrame:
    """Single guideline row whose 'Sample ID' matches one of `phrases` (last match
    wins), sliced verbatim from soil_df_full. Columns stay as the Excel headers --
    no renaming, exactly as the notebook builds each guideline df."""
    pattern = "|".join(re.escape(phrase) for phrase in phrases)
    matching_indices = soil_df_full["Sample ID"].str.contains(pattern, case=False, na=False)
    row_label = soil_df_full[matching_indices].index.tolist()[-1]
    return soil_df_full.loc[row_label:row_label]


def load(ctx: Context) -> Context:
    """Read the workbook, locate the analytical table, clean values, snake_case."""
    sheet = ctx.params.get("sheet_name") or "Soil Table"

    # Parse the workbook ONCE (columns A:DH) and reuse for every slice below and
    # in read_sst_guidelines -- avoids re-parsing the .xlsm multiple times.
    xls = pd.ExcelFile(ctx.excel_path, engine="openpyxl")
    raw_sheet = xls.parse(sheet, header=None, usecols="A:DH")
    ctx.frames["soil_sheet_raw"] = raw_sheet       # reused by read_sst_guidelines
    _sheet_names = xls.sheet_names

    # C:DH block (absolute columns 2..111); static headers assigned positionally.
    soil_df_full = raw_sheet.iloc[:, 2:112].copy()
    soil_df_full.columns = header_columns

    # Analytical table bounds: first "Sample ID" row → footer sentinel.
    row_first = (soil_df_full.iloc[:, 0] == "Sample ID").idxmax()
    footer = soil_df_full.index[
        soil_df_full["Depth (m)"].astype(str).str.contains(
            "Exceeds the limiting guideline value", na=False
        )
    ].to_list()
    row_last = footer[0] if footer else soil_df_full.index[-1] + 1
    soil_df = soil_df_full.loc[row_first + 1: row_last - 1].copy()

    # Guideline blocks embedded below the data, extracted one at a time exactly as
    # the notebook does (Excel-header columns, last matching row per label).
    ctx.frames["limiting_df"] = _extract_guideline_row(
        soil_df_full, ["LIMITING GUIDELINE OR SCREENING VALUE", "LIMITING GUIDELINE VALUE"]
    )
    ctx.frames["management_limits_df"] = _extract_guideline_row(
        soil_df_full, ["Management Limits_Minimum"]
    )
    ctx.frames["tier1_bg_df"] = _extract_guideline_row(
        soil_df_full, ["TIER 1 WITH BACKGROUND"]
    )
    ctx.frames["limiting_tier1_guideline_df"] = _extract_guideline_row(
        soil_df_full, ["Limiting Tier 1 Guideline"]
    )
    ctx.frames["tier2_guideline_df"] = _extract_guideline_row(
        soil_df_full, ["Tier 2 Guideline"]
    )

    ctx.frames["limiting_df"] = ctx.frames["limiting_df"].rename(columns=excel_header_to_cleaned_name_map)
    ctx.frames["tier2_guideline_df"] = ctx.frames["tier2_guideline_df"].rename(columns=excel_header_to_cleaned_name_map)


    # Drop empty-depth rows (typically header rows).
    soil_df = soil_df[soil_df["Depth (m)"].notna() & (soil_df["Depth (m)"] != "")]

    # Keep-low-detect copy for the "split" workflow: taken before numeric
    # coercion so the '<x' low-detect strings survive (cell keeps this alongside
    # the numeric-cleaned soil_df).
    soil_df_keep_low_detect = soil_df.copy()

    # Main path: coerce '<x'/'-' values in numeric columns to floats.
    for col in soil_df.columns:
        if col in numeric_columns:
            soil_df[col] = soil_df[col].apply(remove_signs)
    soil_df = soil_df.round(3)

    # Split path: keep the '<' low-detect strings, round only numeric cells.
    for col in soil_df_keep_low_detect.columns:
        soil_df_keep_low_detect[col] = soil_df_keep_low_detect[col].apply(remove_signs_keep_low_detect)
    soil_df_keep_low_detect = soil_df_keep_low_detect.round(2)

    # snake_case copy for the analysis modules.
    soil_data_filtered = soil_df.rename(columns=excel_header_to_cleaned_name_map)
    soil_data_filtered = soil_data_filtered.where(pd.notna(soil_data_filtered), None)

    ctx.frames["soil_df"] = soil_df                       # excel headers (as notebook)
    ctx.frames["soil_df_keep_low_detect"] = soil_df_keep_low_detect  # excel headers, '<x' kept
    ctx.frames["soil_data_filtered"] = soil_data_filtered  # cleaned snake_case

    ctx.options["columns"] = [str(c) for c in soil_data_filtered.columns]
    ctx.options["sheet_names"] = _sheet_names
    ctx.options["row_count"] = int(len(soil_data_filtered))
    ctx.options["sample_ids"] = [
        str(s) for s in soil_data_filtered["sample_id"].dropna().unique()
    ]
    return ctx


# --- duplicate rows (notebook cell 36) --------------------------------------
_DEDUP_KEY = ["sample_id", "z"]


def drop_duplicate_rows(ctx: Context) -> Context:
    """Enforce one row per (sample_id, z); keep the first occurrence.

    `duplicates_dropped` counts rows removed; `duplicate_conflicts` counts how
    many of those differed from the kept row (a genuine data conflict).
    """
    df = ctx.frames["soil_data_filtered"]
    before = len(df)

    removed_mask = df.duplicated(subset=_DEDUP_KEY, keep="first")
    conflicts = int((removed_mask & ~df.duplicated(keep="first")).sum())

    ctx.frames["soil_data_filtered"] = df[~removed_mask].reset_index(drop=True)
    ctx.options["duplicates_dropped"] = before - len(ctx.frames["soil_data_filtered"])
    ctx.options["duplicate_conflicts"] = conflicts
    return ctx


# --- soluble-ion unit conversion (notebook cell 41) -------------------------
SOLUBLE_IONS_REFERENCE_VALUES = [
    {"parameter": "chloride", "label": "Cl", "valency": 1, "molecular_weight": 35.453},
    {"parameter": "sulphate", "label": "SO4", "valency": 2, "molecular_weight": 96.061},
    {"parameter": "sodium", "label": "Na", "valency": 1, "molecular_weight": 22.990},
    {"parameter": "calcium", "label": "Ca", "valency": 2, "molecular_weight": 40.078},
    {"parameter": "magnesium", "label": "Mg", "valency": 2, "molecular_weight": 24.305},
    {"parameter": "potassium", "label": "K", "valency": 1, "molecular_weight": 39.098},
    {"parameter": "carbonate", "label": "CO3", "valency": 2, "molecular_weight": 60.008},
    {"parameter": "bicarbonate", "label": "HCO3", "valency": 1, "molecular_weight": 61.016},
]


def convert_units(ctx: Context) -> Context:
    """Back-fill missing soluble-ion units on soil_data_filtered.

    mg/L  = mg/kg * 100 / saturation(%);  meq/L = mg/L * valency / molecular_weight.
    Stores a per-ion count summary in ctx.frames["soluble_ions_unit_conversion_summary"].
    """
    soil_data_filtered = ctx.frames["soil_data_filtered"]

    ref_values = pd.DataFrame(SOLUBLE_IONS_REFERENCE_VALUES)
    ref_values["equivalent_weight"] = ref_values["molecular_weight"] / ref_values["valency"]

    saturation = pd.to_numeric(soil_data_filtered["general_inorganics_saturation"], errors="coerce")
    valid_saturation = saturation.notna() & (saturation != 0)
    rows = []

    for _, ref in ref_values.iterrows():
        parameter = ref["parameter"]
        mg_kg_col = f"soluble_ions_{parameter}_mg_kg"
        mg_l_col = f"soluble_ions_{parameter}_mg_l"
        meq_l_col = f"soluble_ions_{parameter}_meq_l"

        if mg_kg_col not in soil_data_filtered.columns:
            continue
        if mg_l_col not in soil_data_filtered.columns:
            soil_data_filtered[mg_l_col] = pd.NA
        if meq_l_col not in soil_data_filtered.columns:
            soil_data_filtered[meq_l_col] = pd.NA

        mg_kg = pd.to_numeric(soil_data_filtered[mg_kg_col], errors="coerce")
        mg_l = pd.to_numeric(soil_data_filtered[mg_l_col], errors="coerce")
        meq_l = pd.to_numeric(soil_data_filtered[meq_l_col], errors="coerce")

        has_mg_kg = mg_kg.notna()
        missing_mg_l = has_mg_kg & mg_l.isna()
        computable_mg_l = missing_mg_l & valid_saturation
        computed_mg_l = mg_kg * 100 / saturation
        soil_data_filtered.loc[computable_mg_l, mg_l_col] = computed_mg_l.loc[computable_mg_l]

        mg_l_after = pd.to_numeric(soil_data_filtered[mg_l_col], errors="coerce")
        missing_meq_l = has_mg_kg & meq_l.isna()
        computable_meq_l = missing_meq_l & mg_l_after.notna()
        computed_meq_l = mg_l_after * ref["valency"] / ref["molecular_weight"]
        soil_data_filtered.loc[computable_meq_l, meq_l_col] = computed_meq_l.loc[computable_meq_l]

        meq_l_after = pd.to_numeric(soil_data_filtered[meq_l_col], errors="coerce")
        rows.append({
            "Parameter": parameter.title(),
            "Valency": int(ref["valency"]),
            "Molecular Weight": ref["molecular_weight"],
            "mg/kg rows": int(has_mg_kg.sum()),
            "Missing mg/L before": int(missing_mg_l.sum()),
            "Computed mg/L": int(computable_mg_l.sum()),
            "Missing mg/L after": int((has_mg_kg & mg_l_after.isna()).sum()),
            "Missing meq/L before": int(missing_meq_l.sum()),
            "Computed meq/L": int(computable_meq_l.sum()),
            "Missing meq/L after": int((has_mg_kg & meq_l_after.isna()).sum()),
        })

    ctx.frames["soil_data_filtered"] = soil_data_filtered
    ctx.frames["soluble_ions_unit_conversion_summary"] = pd.DataFrame(rows)
    return ctx


# --- average 1.0-1.5 m duplicate boreholes (notebook cell 45-49) ------------
def average_duplicates(ctx: Context) -> Context:
    """Produce soil_df_averaged: rows with z in [1, 1.5] collapsed per sample_id
    (numeric meaned, non-numeric concatenated with ';'); other rows kept as-is.
    Use soil_df_averaged for statistics, soil_data_filtered for exceedances.
    """
    soil_data_filtered = ctx.frames["soil_data_filtered"]

    z_filtered = soil_data_filtered[
        (soil_data_filtered["z"] >= 1) & (soil_data_filtered["z"] <= 1.5)
    ]

    dtypes = z_filtered.dtypes
    numeric_cols = dtypes[(dtypes == "float64") | (dtypes == "int64")].index.tolist()
    non_numeric_cols = [
        col for col in z_filtered.columns if col not in numeric_cols and col != "sample_id"
    ]

    def agg_concat(series):
        non_null_values = series.dropna().astype(str).unique()
        return ";".join(non_null_values)

    agg_dict = {col: "mean" for col in numeric_cols}
    agg_dict.update({col: agg_concat for col in non_numeric_cols})

    z_agg_by_sample_id = (
        z_filtered.groupby("sample_id", dropna=False).agg(agg_dict).reset_index()
    )

    soil_data_no_z_1_to_1_5 = soil_data_filtered[
        (soil_data_filtered["z"] < 1) | (soil_data_filtered["z"] > 1.5)
    ]

    soil_df_averaged = pd.concat(
        [soil_data_no_z_1_to_1_5, z_agg_by_sample_id], ignore_index=True
    )
    soil_df_averaged = soil_df_averaged.replace(r"^\s*$", None, regex=True)

    ctx.frames["soil_df_averaged"] = soil_df_averaged
    return ctx


# --- SST guidelines read (notebook cell 53) ---------------------------------
def _format_depth_range(top, btm):
    """Render a top/bottom pair as the 'min-max' string the exceedance cells parse."""
    if pd.isna(top) or pd.isna(btm):
        return None
    return "{0:g}-{1:g}".format(float(top), float(btm))


def _format_guideline(val):
    if pd.isna(val):
        return None
    return "{0:g}".format(float(val))


def read_sst_guidelines(ctx: Context) -> Context:
    """Read the SITE-SPECIFIC guideline block (Chloride, Na, SAR per subarea).

    Produces:
      sst_guideline_block_df       - raw block (subarea + cl/sar/na guidelines + depths)
      sst_cl_guide_default_df      - Subarea / Depth Range / Cl Guideline
      sst_na_sar_guide_default_df  - Subarea / Depth Range / Na / SAR guidelines
    """
    # Reuse the single parse from load(); fall back to a one-off parse if run standalone.
    raw_sheet = ctx.frames.pop("soil_sheet_raw", None)
    if raw_sheet is None:
        sheet = ctx.params.get("sheet_name") or "Soil Table"
        raw_sheet = pd.ExcelFile(ctx.excel_path, engine="openpyxl").parse(
            sheet, header=None, usecols="A:DH"
        )

    # Cols C, R, Z, AA, AB, AD, AE, AF, AG (absolute positions).
    sst_guideline_raw_df = raw_sheet.iloc[:, [2, 17, 25, 26, 27, 29, 30, 31, 32]].copy()
    sst_guideline_raw_df.columns = [
        "label", "subarea", "cl_guideline", "sar_guideline", "na_guideline",
        "cl_top", "cl_btm", "na_sar_top", "na_sar_btm",
    ]

    # Block runs from the 'SITE-SPECIFIC' header to the limiting-guideline footer.
    sst_row_first = (sst_guideline_raw_df["label"] == "SITE-SPECIFIC").idxmax()
    sst_row_last = (sst_guideline_raw_df["label"] == "LIMITING GUIDELINE OR SCREENING VALUE").idxmax()

    block = sst_guideline_raw_df.loc[sst_row_first + 1: sst_row_last - 1].copy()
    block = block[block["subarea"].notna()]
    block["subarea"] = block["subarea"].astype(str).str.strip()
    for _num_col in ["cl_guideline", "sar_guideline", "na_guideline",
                     "cl_top", "cl_btm", "na_sar_top", "na_sar_btm"]:
        block[_num_col] = pd.to_numeric(block[_num_col], errors="coerce")

    sst_cl = pd.DataFrame({
        "Subarea": block["subarea"],
        "Depth Range": [_format_depth_range(t, b) for t, b in zip(block["cl_top"], block["cl_btm"])],
        "Cl Guideline": block["cl_guideline"].map(_format_guideline),
    }).reset_index(drop=True)

    sst_na_sar = pd.DataFrame({
        "Subarea": block["subarea"],
        "Depth Range": [_format_depth_range(t, b) for t, b in zip(block["na_sar_top"], block["na_sar_btm"])],
        "Na Guideline": block["na_guideline"].map(_format_guideline),
        "SAR Guideline": block["sar_guideline"].map(_format_guideline),
    }).reset_index(drop=True)

    ctx.frames["sst_guideline_block_df"] = block.reset_index(drop=True)
    ctx.frames["sst_cl_guide_default_df"] = sst_cl[sst_cl["Depth Range"].notna()].reset_index(drop=True)
    ctx.frames["sst_na_sar_guide_default_df"] = sst_na_sar[sst_na_sar["Depth Range"].notna()].reset_index(drop=True)
    return ctx

# ---------------------------------------------------------------------------
# Static header definitions (the soil sheet has multi-row headers + metadata,
# so columns are assigned positionally from header_columns, then mapped to
# snake_case / display names). Kept at the bottom so the logic reads first.
# ---------------------------------------------------------------------------

header_columns = [
    'Sample ID',
    'Depth (m)',
    'Date',
    'Lab ID',
    'X',
    'Y',
    'Z',
    'APEC',
    'Hidden Comments',
    'Comments',
    'Subarea',
    'General Inorganics_pH',
    'General Inorganics_EC_dS/m',
    'General Inorganics_SAR',
    'General Inorganics_Saturation_%',
    'Soluble Ions_Chloride_mg/L',
    'Soluble Ions_Sulphate_mg/L',
    'Soluble Ions_Sodium_mg/L',
    'Soluble Ions_Calcium_mg/L',
    'Soluble Ions_Magnesium_mg/L',
    'Soluble Ions_Potassium_mg/L',
    'Soluble Ions_Carbonate_mg/L',
    'Soluble Ions_Bicarbonate_mg/L',
    'Soluble Ions_Chloride_mg/kg',
    'Soluble Ions_Sulphate_mg/kg',
    'Soluble Ions_Sodium_mg/kg',
    'Soluble Ions_Calcium_mg/kg',
    'Soluble Ions_Magnesium_mg/kg',
    'Soluble Ions_Potassium_mg/kg',
    'Soluble Ions_Carbonate_mg/kg',
    'Soluble Ions_Bicarbonate_mg/kg',
    'Soluble Ions_Chloride_meq/L',
    'Soluble Ions_Sulphate_meq/L',
    'Soluble Ions_Sodium_meq/L',
    'Soluble Ions_Calcium_meq/L',
    'Soluble Ions_Magnesium_meq/L',
    'Soluble Ions_Potassium_meq/L',
    'Soluble Ions_Carbonate_meq/L',
    'Soluble Ions_Bicarbonate_meq/L',
    'Soluble Ions_Anions Total_meq/L',
    'Soluble Ions_Cations Total_meq/L',
    'Soluble Ions_Ionic Balance_%',
    'Particle Size_Sand_%',
    'Particle Size_Silt_%',
    'Particle Size_Clay_%',
    'Particle Size_Soil Texture',
    'Particle Size_75 Micron Sieve_% ret.',
    'Particle Size_Fine/Coarse',
    'Hydrocarbons_Moisture_%',
    'Hydrocarbons_Benzene_mg/kg',
    'Hydrocarbons_Toluene_mg/kg',
    'Hydrocarbons_Ethylbenzene_mg/kg',
    'Hydrocarbons_Xylenes_mg/kg',
    'Hydrocarbons_F1 (C6-C10) - BTEX_mg/kg',
    'Hydrocarbons_F2 (C10-C16)_mg/kg',
    'Hydrocarbons_F3 (C16-C34)_mg/kg',
    'Hydrocarbons_F4 (C34-C50)_mg/kg',
    'Hydrocarbons_F4G (C34+)_mg/kg',
    'Hydrocarbons_Chromatogram  returns to baseline?',
    'Non-Carcinogenic PAHs_Acenaphthene_mg/kg',
    'Non-Carcinogenic PAHs_Acenaphthylene_mg/kg',
    'Non-Carcinogenic PAHs_Anthracene_mg/kg',
    'Non-Carcinogenic PAHs_Fluoranthene_mg/kg',
    'Non-Carcinogenic PAHs_Fluorene_mg/kg',
    'Non-Carcinogenic PAHs_Naphthalene_mg/kg',
    'Non-Carcinogenic PAHs_Methylnapthalene (2-)_mg/kg',
    'Non-Carcinogenic PAHs_Phenanthrene_mg/kg',
    'Non-Carcinogenic PAHs_Pyrene_mg/kg',
    'Carcinogenic PAHs_Benzo[a]anthracene_mg/kg',
    'Carcinogenic PAHs_Benzo[b+j]fluoranthene_mg/kg',
    'Carcinogenic PAHs_Benzo[k]fluoranthene_mg/kg',
    'Carcinogenic PAHs_Benzo[g,h,i]perylene_mg/kg',
    'Carcinogenic PAHs_Benzo[a]pyrene_mg/kg',
    'Carcinogenic PAHs_Chrysene_mg/kg',
    'Carcinogenic PAHs_Dibenz[a,h]anthracene_mg/kg',
    'Carcinogenic PAHs_Indeno[1,2,3-c,d]pyrene_mg/kg',
    'Carcinogenic PAHs_Carcinogenic PAHs: IACR (Fine)_mg/kg',
    'Carcinogenic PAHs_Carcinogenic PAHs: IACR (Coarse)_mg/kg',
    'Carcinogenic PAHs_Carcinogenic PAHs: TPE_mg/kg',
    'Carcinogenic PAHs_PAH Total (for sediment)*_mg/kg',
    'Other Organics_Ethylene glycol_mg/kg',
    'Other Organics_Diethylene glycol_mg/kg',
    'Other Organics_Triethylene glycol_mg/kg',
    'Other Organics_Methanol_mg/kg',
    'Other Organics_Phenol_mg/kg',
    'Metals_Antimony_mg/kg',
    'Metals_Arsenic (inorganic)_mg/kg',
    'Metals_Barium (non-barite)_mg/kg',
    'Metals_Barite-barium_mg/kg',
    'Metals_Extractable Barium_mg/kg',
    'Metals_Beryllium_mg/kg',
    'Metals_Boron (saturated paste)_mg/L',
    'Metals_Boron  (hot water soluble)_mg/kg',
    'Metals_Cadmium_mg/kg',
    'Metals_Chromium (hexavalent)_mg/kg',
    'Metals_Chromium (total)_mg/kg',
    'Metals_Cobalt_mg/kg',
    'Metals_Copper_mg/kg',
    'Metals_Lead_mg/kg',
    'Metals_Manganese_mg/kg',
    'Metals_Mercury (inorganic)_mg/kg',
    'Metals_Molybdenum_mg/kg',
    'Metals_Nickel_mg/kg',
    'Metals_Selenium_mg/kg',
    'Metals_Silver_mg/kg',
    'Metals_Thallium_mg/kg',
    'Metals_Tin_mg/kg',
    'Metals_Uranium_mg/kg',
    'Metals_Vanadium_mg/kg',
    'Metals_Zinc_mg/kg'
 ]

excel_header_to_cleaned_name_map = OrderedDict([
             ('Sample ID', 'sample_id'),
             ('Depth (m)', 'depth_m'),
             ('Date', 'date'),
             ('Lab ID', 'lab_id'),
             ('X', 'x'),
             ('Y', 'y'),
             ('Z', 'z'),
             ('APEC', 'apec'),
             ('Hidden Comments', 'hidden_comments'),
             ('Comments', 'comments'),
             ('Subarea', 'subarea'),
             ('General Inorganics_pH', 'general_inorganics_ph'),
             ('General Inorganics_EC_dS/m', 'general_inorganics_ec_ds_m'),
             ('General Inorganics_SAR', 'general_inorganics_sar'),
             ('General Inorganics_Saturation_%',
              'general_inorganics_saturation'),
             ('Soluble Ions_Chloride_mg/L', 'soluble_ions_chloride_mg_l'),
             ('Soluble Ions_Sulphate_mg/L', 'soluble_ions_sulphate_mg_l'),
             ('Soluble Ions_Sodium_mg/L', 'soluble_ions_sodium_mg_l'),
             ('Soluble Ions_Calcium_mg/L', 'soluble_ions_calcium_mg_l'),
             ('Soluble Ions_Magnesium_mg/L', 'soluble_ions_magnesium_mg_l'),
             ('Soluble Ions_Potassium_mg/L', 'soluble_ions_potassium_mg_l'),
             ('Soluble Ions_Carbonate_mg/L', 'soluble_ions_carbonate_mg_l'),
             ('Soluble Ions_Bicarbonate_mg/L',
              'soluble_ions_bicarbonate_mg_l'),
             ('Soluble Ions_Chloride_mg/kg', 'soluble_ions_chloride_mg_kg'),
             ('Soluble Ions_Sulphate_mg/kg', 'soluble_ions_sulphate_mg_kg'),
             ('Soluble Ions_Sodium_mg/kg', 'soluble_ions_sodium_mg_kg'),
             ('Soluble Ions_Calcium_mg/kg', 'soluble_ions_calcium_mg_kg'),
             ('Soluble Ions_Magnesium_mg/kg', 'soluble_ions_magnesium_mg_kg'),
             ('Soluble Ions_Potassium_mg/kg', 'soluble_ions_potassium_mg_kg'),
             ('Soluble Ions_Carbonate_mg/kg', 'soluble_ions_carbonate_mg_kg'),
             ('Soluble Ions_Bicarbonate_mg/kg',
              'soluble_ions_bicarbonate_mg_kg'),
             ('Soluble Ions_Chloride_meq/L', 'soluble_ions_chloride_meq_l'),
             ('Soluble Ions_Sulphate_meq/L', 'soluble_ions_sulphate_meq_l'),
             ('Soluble Ions_Sodium_meq/L', 'soluble_ions_sodium_meq_l'),
             ('Soluble Ions_Calcium_meq/L', 'soluble_ions_calcium_meq_l'),
             ('Soluble Ions_Magnesium_meq/L', 'soluble_ions_magnesium_meq_l'),
             ('Soluble Ions_Potassium_meq/L', 'soluble_ions_potassium_meq_l'),
             ('Soluble Ions_Carbonate_meq/L', 'soluble_ions_carbonate_meq_l'),
             ('Soluble Ions_Bicarbonate_meq/L',
              'soluble_ions_bicarbonate_meq_l'),
             ('Soluble Ions_Anions Total_meq/L',
              'soluble_ions_anions_total_meq_l'),
             ('Soluble Ions_Cations Total_meq/L',
              'soluble_ions_cations_total_meq_l'),
             ('Soluble Ions_Ionic Balance_%', 'soluble_ions_ionic_balance'),
             ('Particle Size_Sand_%', 'particle_size_sand'),
             ('Particle Size_Silt_%', 'particle_size_silt'),
             ('Particle Size_Clay_%', 'particle_size_clay'),
             ('Particle Size_Soil Texture', 'particle_size_soil_texture'),
             ('Particle Size_75 Micron Sieve_% ret.',
              'particle_size_75_micron_sieve_ret'),
             ('Particle Size_Fine/Coarse', 'particle_size_fine_coarse'),
             ('Hydrocarbons_Moisture_%', 'hydrocarbons_moisture'),
             ('Hydrocarbons_Benzene_mg/kg', 'hydrocarbons_benzene_mg_kg'),
             ('Hydrocarbons_Toluene_mg/kg', 'hydrocarbons_toluene_mg_kg'),
             ('Hydrocarbons_Ethylbenzene_mg/kg',
              'hydrocarbons_ethylbenzene_mg_kg'),
             ('Hydrocarbons_Xylenes_mg/kg', 'hydrocarbons_xylenes_mg_kg'),
             ('Hydrocarbons_F1 (C6-C10) - BTEX_mg/kg',
              'hydrocarbons_f1_c6_c10_btex_mg_kg'),
             ('Hydrocarbons_F2 (C10-C16)_mg/kg',
              'hydrocarbons_f2_c10_c16_mg_kg'),
             ('Hydrocarbons_F3 (C16-C34)_mg/kg',
              'hydrocarbons_f3_c16_c34_mg_kg'),
             ('Hydrocarbons_F4 (C34-C50)_mg/kg',
              'hydrocarbons_f4_c34_c50_mg_kg'),
             ('Hydrocarbons_F4G (C34+)_mg/kg', 'hydrocarbons_f4g_c34_mg_kg'),
             ('Hydrocarbons_Chromatogram  returns to baseline?',
              'hydrocarbons_chromatogram_returns_to_baseline'),
             ('Non-Carcinogenic PAHs_Acenaphthene_mg/kg',
              'non_carcinogenic_pahs_acenaphthene_mg_kg'),
             ('Non-Carcinogenic PAHs_Acenaphthylene_mg/kg',
              'non_carcinogenic_pahs_acenaphthylene_mg_kg'),
             ('Non-Carcinogenic PAHs_Anthracene_mg/kg',
              'non_carcinogenic_pahs_anthracene_mg_kg'),
             ('Non-Carcinogenic PAHs_Fluoranthene_mg/kg',
              'non_carcinogenic_pahs_fluoranthene_mg_kg'),
             ('Non-Carcinogenic PAHs_Fluorene_mg/kg',
              'non_carcinogenic_pahs_fluorene_mg_kg'),
             ('Non-Carcinogenic PAHs_Naphthalene_mg/kg',
              'non_carcinogenic_pahs_naphthalene_mg_kg'),
             ('Non-Carcinogenic PAHs_Methylnapthalene (2-)_mg/kg',
              'non_carcinogenic_pahs_methylnapthalene_2_mg_kg'),
             ('Non-Carcinogenic PAHs_Phenanthrene_mg/kg',
              'non_carcinogenic_pahs_phenanthrene_mg_kg'),
             ('Non-Carcinogenic PAHs_Pyrene_mg/kg',
              'non_carcinogenic_pahs_pyrene_mg_kg'),
             ('Carcinogenic PAHs_Benzo[a]anthracene_mg/kg',
              'carcinogenic_pahs_benzo_a_anthracene_mg_kg'),
             ('Carcinogenic PAHs_Benzo[b+j]fluoranthene_mg/kg',
              'carcinogenic_pahs_benzo_b_j_fluoranthene_mg_kg'),
             ('Carcinogenic PAHs_Benzo[k]fluoranthene_mg/kg',
              'carcinogenic_pahs_benzo_k_fluoranthene_mg_kg'),
             ('Carcinogenic PAHs_Benzo[g,h,i]perylene_mg/kg',
              'carcinogenic_pahs_benzo_g_h_i_perylene_mg_kg'),
             ('Carcinogenic PAHs_Benzo[a]pyrene_mg/kg',
              'carcinogenic_pahs_benzo_a_pyrene_mg_kg'),
             ('Carcinogenic PAHs_Chrysene_mg/kg',
              'carcinogenic_pahs_chrysene_mg_kg'),
             ('Carcinogenic PAHs_Dibenz[a,h]anthracene_mg/kg',
              'carcinogenic_pahs_dibenz_a_h_anthracene_mg_kg'),
             ('Carcinogenic PAHs_Indeno[1,2,3-c,d]pyrene_mg/kg',
              'carcinogenic_pahs_indeno_1_2_3_c_d_pyrene_mg_kg'),
             ('Carcinogenic PAHs_Carcinogenic PAHs: IACR (Fine)_mg/kg',
              'carcinogenic_pahs_carcinogenic_pahs_iacr_fine_mg_kg'),
             ('Carcinogenic PAHs_Carcinogenic PAHs: IACR (Coarse)_mg/kg',
              'carcinogenic_pahs_carcinogenic_pahs_iacr_coarse_mg_kg'),
             ('Carcinogenic PAHs_Carcinogenic PAHs: TPE_mg/kg',
              'carcinogenic_pahs_carcinogenic_pahs_tpe_mg_kg'),
             ('Carcinogenic PAHs_PAH Total (for sediment)*_mg/kg',
              'carcinogenic_pahs_pah_total_for_sediment_mg_kg'),
             ('Other Organics_Ethylene glycol_mg/kg',
              'other_organics_ethylene_glycol_mg_kg'),
             ('Other Organics_Diethylene glycol_mg/kg',
              'other_organics_diethylene_glycol_mg_kg'),
             ('Other Organics_Triethylene glycol_mg/kg',
              'other_organics_triethylene_glycol_mg_kg'),
             ('Other Organics_Methanol_mg/kg',
              'other_organics_methanol_mg_kg'),
             ('Other Organics_Phenol_mg/kg', 'other_organics_phenol_mg_kg'),
             ('Metals_Antimony_mg/kg', 'metals_antimony_mg_kg'),
             ('Metals_Arsenic (inorganic)_mg/kg',
              'metals_arsenic_inorganic_mg_kg'),
             ('Metals_Barium (non-barite)_mg/kg',
              'metals_barium_non_barite_mg_kg'),
             ('Metals_Barite-barium_mg/kg', 'metals_barite_barium_mg_kg'),
             ('Metals_Extractable Barium_mg/kg',
              'metals_extractable_barium_mg_kg'),
             ('Metals_Beryllium_mg/kg', 'metals_beryllium_mg_kg'),
             ('Metals_Boron (saturated paste)_mg/L',
              'metals_boron_saturated_paste_mg_l'),
             ('Metals_Boron  (hot water soluble)_mg/kg',
              'metals_boron_hot_water_soluble_mg_kg'),
             ('Metals_Cadmium_mg/kg', 'metals_cadmium_mg_kg'),
             ('Metals_Chromium (hexavalent)_mg/kg',
              'metals_chromium_hexavalent_mg_kg'),
             ('Metals_Chromium (total)_mg/kg', 'metals_chromium_total_mg_kg'),
             ('Metals_Cobalt_mg/kg', 'metals_cobalt_mg_kg'),
             ('Metals_Copper_mg/kg', 'metals_copper_mg_kg'),
             ('Metals_Lead_mg/kg', 'metals_lead_mg_kg'),
             ('Metals_Manganese_mg/kg', 'metals_manganese_mg_kg'),
             ('Metals_Mercury (inorganic)_mg/kg',
              'metals_mercury_inorganic_mg_kg'),
             ('Metals_Molybdenum_mg/kg', 'metals_molybdenum_mg_kg'),
             ('Metals_Nickel_mg/kg', 'metals_nickel_mg_kg'),
             ('Metals_Selenium_mg/kg', 'metals_selenium_mg_kg'),
             ('Metals_Silver_mg/kg', 'metals_silver_mg_kg'),
             ('Metals_Thallium_mg/kg', 'metals_thallium_mg_kg'),
             ('Metals_Tin_mg/kg', 'metals_tin_mg_kg'),
             ('Metals_Uranium_mg/kg', 'metals_uranium_mg_kg'),
             ('Metals_Vanadium_mg/kg', 'metals_vanadium_mg_kg'),
             ('Metals_Zinc_mg/kg', 'metals_zinc_mg_kg')])

# Create a reverse mapping dictionary where the key is the cleaned database name, and the value is the display name
cleaned_name_to_excel_header_map = {
    'sample_id': 'Sample ID',
    'depth_m': 'Depth (m)',
    'date': 'Date',
    'lab_id': 'Lab ID',
    'x': 'X',
    'y': 'Y',
    'z': 'Z',
    'apec': 'APEC',
    'hidden_comments': 'Hidden Comments',
    'comments': 'Comments',
    'subarea': 'Subarea',
    'general_inorganics_ph': 'pH',
    'general_inorganics_ec_ds_m': 'EC (dS/m)',
    'general_inorganics_sar': 'SAR',
    'general_inorganics_saturation': 'Saturation (%)',
    'soluble_ions_chloride_mg_l': 'Chloride (mg/L)',
    'soluble_ions_sulphate_mg_l': 'Sulphate (mg/L)',
    'soluble_ions_sodium_mg_l': 'Sodium (mg/L)',
    'soluble_ions_calcium_mg_l': 'Calcium (mg/L)',
    'soluble_ions_magnesium_mg_l': 'Magnesium (mg/L)',
    'soluble_ions_potassium_mg_l': 'Potassium (mg/L)',
    'soluble_ions_carbonate_mg_l': 'Carbonate (mg/L)',
    'soluble_ions_bicarbonate_mg_l': 'Bicarbonate (mg/L)',
    'soluble_ions_chloride_mg_kg': 'Chloride (mg/kg)',
    'soluble_ions_sulphate_mg_kg': 'Sulphate (mg/kg)',
    'soluble_ions_sodium_mg_kg': 'Sodium (mg/kg)',
    'soluble_ions_calcium_mg_kg': 'Calcium (mg/kg)',
    'soluble_ions_magnesium_mg_kg': 'Magnesium (mg/kg)',
    'soluble_ions_potassium_mg_kg': 'Potassium (mg/kg)',
    'soluble_ions_carbonate_mg_kg': 'Carbonate (mg/kg)',
    'soluble_ions_bicarbonate_mg_kg': 'Bicarbonate (mg/kg)',
    'soluble_ions_chloride_meq_l': 'Chloride (meq/L)',
    'soluble_ions_sulphate_meq_l': 'Sulphate (meq/L)',
    'soluble_ions_sodium_meq_l': 'Sodium (meq/L)',
    'soluble_ions_calcium_meq_l': 'Calcium (meq/L)',
    'soluble_ions_magnesium_meq_l': 'Magnesium (meq/L)',
    'soluble_ions_potassium_meq_l': 'Potassium (meq/L)',
    'soluble_ions_carbonate_meq_l': 'Carbonate (meq/L)',
    'soluble_ions_bicarbonate_meq_l': 'Bicarbonate (meq/L)',
    'soluble_ions_anions_total_meq_l': 'Anions Total (meq/L)',
    'soluble_ions_cations_total_meq_l': 'Cations Total (meq/L)',
    'soluble_ions_ionic_balance': 'Ionic Balance (%)',
    'particle_size_sand': 'Sand (%)',
    'particle_size_silt': 'Silt (%)',
    'particle_size_clay': 'Clay (%)',
    'particle_size_soil_texture': 'Soil Texture',
    'particle_size_75_micron_sieve_ret': '75 Micron Sieve (%) ret.',
    'particle_size_fine_coarse': 'Fine/Coarse',
    'hydrocarbons_moisture': 'Moisture (%)',
    'hydrocarbons_benzene_mg_kg': 'Benzene (mg/kg)',
    'hydrocarbons_toluene_mg_kg': 'Toluene (mg/kg)',
    'hydrocarbons_ethylbenzene_mg_kg': 'Ethylbenzene (mg/kg)',
    'hydrocarbons_xylenes_mg_kg': 'Xylenes (mg/kg)',
    'hydrocarbons_f1_c6_c10_btex_mg_kg': 'F1 (C6-C10) - BTEX (mg/kg)',
    'hydrocarbons_f2_c10_c16_mg_kg': 'F2 (C10-C16) (mg/kg)',
    'hydrocarbons_f3_c16_c34_mg_kg': 'F3 (C16-C34) (mg/kg)',
    'hydrocarbons_f4_c34_c50_mg_kg': 'F4 (C34-C50) (mg/kg)',
    'hydrocarbons_f4g_c34_mg_kg': 'F4G (C34+) (mg/kg)',
    'hydrocarbons_chromatogram_returns_to_baseline': 'Chromatogram  returns to baseline?',
    'non_carcinogenic_pahs_acenaphthene_mg_kg': 'Acenaphthene (mg/kg)',
    'non_carcinogenic_pahs_acenaphthylene_mg_kg': 'Acenaphthylene (mg/kg)',
    'non_carcinogenic_pahs_anthracene_mg_kg': 'Anthracene (mg/kg)',
    'non_carcinogenic_pahs_fluoranthene_mg_kg': 'Fluoranthene (mg/kg)',
    'non_carcinogenic_pahs_fluorene_mg_kg': 'Fluorene (mg/kg)',
    'non_carcinogenic_pahs_naphthalene_mg_kg': 'Naphthalene (mg/kg)',
    'non_carcinogenic_pahs_methylnapthalene_2_mg_kg': 'Methylnapthalene (2-) (mg/kg)',
    'non_carcinogenic_pahs_phenanthrene_mg_kg': 'Phenanthrene (mg/kg)',
    'non_carcinogenic_pahs_pyrene_mg_kg': 'Pyrene (mg/kg)',
    'carcinogenic_pahs_benzo_a_anthracene_mg_kg': 'Benzo[a]anthracene (mg/kg)',
    'carcinogenic_pahs_benzo_b_j_fluoranthene_mg_kg': 'Benzo[b+j]fluoranthene (mg/kg)',
    'carcinogenic_pahs_benzo_k_fluoranthene_mg_kg': 'Benzo[k]fluoranthene (mg/kg)',
    'carcinogenic_pahs_benzo_g_h_i_perylene_mg_kg': 'Benzo[g,h,i]perylene (mg/kg)',
    'carcinogenic_pahs_benzo_a_pyrene_mg_kg': 'Benzo[a]pyrene (mg/kg)',
    'carcinogenic_pahs_chrysene_mg_kg': 'Chrysene (mg/kg)',
    'carcinogenic_pahs_dibenz_a_h_anthracene_mg_kg': 'Dibenz[a,h]anthracene (mg/kg)',
    'carcinogenic_pahs_indeno_1_2_3_c_d_pyrene_mg_kg': 'Indeno[1,2,3-c,d]pyrene (mg/kg)',
    'carcinogenic_pahs_carcinogenic_pahs_iacr_fine_mg_kg': 'IACR (Fine) (mg/kg)',
    'carcinogenic_pahs_carcinogenic_pahs_iacr_coarse_mg_kg': 'IACR (Coarse) (mg/kg)',
    'carcinogenic_pahs_carcinogenic_pahs_tpe_mg_kg': 'TPE (mg/kg)',
    'carcinogenic_pahs_pah_total_for_sediment_mg_kg': 'PAH Total (for sediment)* (mg/kg)',
    'other_organics_ethylene_glycol_mg_kg': 'Ethylene glycol (mg/kg)',
    'other_organics_diethylene_glycol_mg_kg': 'Diethylene glycol (mg/kg)',
    'other_organics_triethylene_glycol_mg_kg': 'Triethylene glycol (mg/kg)',
    'other_organics_methanol_mg_kg': 'Methanol (mg/kg)',
    'other_organics_phenol_mg_kg': 'Phenol (mg/kg)',
    'metals_antimony_mg_kg': 'Antimony (mg/kg)',
    'metals_arsenic_inorganic_mg_kg': 'Arsenic (inorganic) (mg/kg)',
    'metals_barium_non_barite_mg_kg': 'Barium (non-barite) (mg/kg)',
    'metals_barite_barium_mg_kg': 'Barite-barium (mg/kg)',
    'metals_extractable_barium_mg_kg': 'Extractable Barium (mg/kg)',
    'metals_beryllium_mg_kg': 'Beryllium (mg/kg)',
    'metals_boron_saturated_paste_mg_l': 'Boron (saturated paste) (mg/L)',
    'metals_boron_hot_water_soluble_mg_kg': 'Boron  (hot water soluble) (mg/kg)',
    'metals_cadmium_mg_kg': 'Cadmium (mg/kg)',
    'metals_chromium_hexavalent_mg_kg': 'Chromium (hexavalent) (mg/kg)',
    'metals_chromium_total_mg_kg': 'Chromium (total) (mg/kg)',
    'metals_cobalt_mg_kg': 'Cobalt (mg/kg)',
    'metals_copper_mg_kg': 'Copper (mg/kg)',
    'metals_lead_mg_kg': 'Lead (mg/kg)',
    'metals_manganese_mg_kg': 'Manganese (mg/kg)',
    'metals_mercury_inorganic_mg_kg': 'Mercury (inorganic) (mg/kg)',
    'metals_molybdenum_mg_kg': 'Molybdenum (mg/kg)',
    'metals_nickel_mg_kg': 'Nickel (mg/kg)',
    'metals_selenium_mg_kg': 'Selenium (mg/kg)',
    'metals_silver_mg_kg': 'Silver (mg/kg)',
    'metals_thallium_mg_kg': 'Thallium (mg/kg)',
    'metals_tin_mg_kg': 'Tin (mg/kg)',
    'metals_uranium_mg_kg': 'Uranium (mg/kg)',
    'metals_vanadium_mg_kg': 'Vanadium (mg/kg)',
    'metals_zinc_mg_kg': 'Zinc (mg/kg)',
    "media": "Media",
    "parameter_exceedance_value": "Value",
    "parameter": "Parameter",
    "threshold": "Guideline",
    "ec_category": "EC Category",
    "sar_category": "SAR Category",
 }

# Reverse maping dictionary from display name to cleaned name
display_name_to_cleaned_name_map = {v: k for k, v in cleaned_name_to_excel_header_map.items()}
cleaned_to_excel = {v: k for k, v in excel_header_to_cleaned_name_map.items()}

non_numeric_columns = [
    'Sample ID',
    'Depth (m)',
    'Date',
    'Lab ID',
    'APEC',
    'Hidden Comments',
    'Comments',
    'Subarea',
    'Particle Size_Soil Texture',
    'Particle Size_Fine/Coarse',
    'Hydrocarbons_Chromatogram  returns to baseline?',
]

numeric_columns = list(set(header_columns).symmetric_difference(set(non_numeric_columns)))
