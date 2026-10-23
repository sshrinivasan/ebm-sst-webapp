"""Excel + charts export — write the analysis frames to a multi-sheet workbook
and the generated charts to a zip with a folder hierarchy.

Maps the notebook's export dataframes to the webapp's ``ctx.frames`` /
``ctx.exports`` (see the export cells in the SST notebook). The "Metals" and
"Surface_PHC" sheets are intentionally omitted for now — the notebook's
"Split Metals and PHC data" step has not been ported to the webapp yet.
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd

from .bg_chloride import _bg_figure_name
from .context import Context
from .loader import (
    cleaned_name_to_excel_header_map,
    excel_header_to_cleaned_name_map,
    numeric_columns,
)

# Chloride justification additional-threshold used by the Site Summary sheet.
# Hardcoded for now (mirrors the skill's default); parameterize later.
JUSTIFICATION_CL_SECONDARY_LIMIT = 300


def _first_present(*frames: pd.DataFrame | None) -> pd.DataFrame | None:
    """Return the first non-None, non-empty frame (for sheet-source fallbacks)."""
    for df in frames:
        if df is not None and not df.empty:
            return df
    return None


def _npp_profile_interpretation(ctx: Context) -> pd.DataFrame | None:
    """NPP-Profile Interpretation sheet: npp_test_results minus the internal
    site_pass / Test A part columns (mirrors the notebook's export)."""
    df = ctx.frames.get("npp_test_results")
    if df is None:
        return None
    return df.drop(
        columns=["site_pass", "Test A: P1", "Test A: P2", "Test A: P3"],
        errors="ignore",
    )


def build_site_summary(ctx: Context) -> pd.DataFrame | None:
    """Build the Site Summary one-row DataFrame for the export workbook.

    Combines the land-use block (Version/Land Use/Texture/Strata labels parsed
    in load()) with the measured COPC list and the hardcoded Cl justification
    threshold. Returns None if the land-use block is unavailable.
    """
    landuse_details_df = ctx.frames.get("landuse_details_df")
    if landuse_details_df is None or landuse_details_df.empty:
        return None

    _landuse_lookup = dict(zip(landuse_details_df["field"], landuse_details_df["value"]))

    def _combine_c1_c2(prefix: str) -> str:
        _vals = [_landuse_lookup.get(f"{prefix}_C1"), _landuse_lookup.get(f"{prefix}_C2")]
        _vals = [str(v).strip() for v in _vals if pd.notna(v) and str(v).strip() != ""]
        return ", ".join(dict.fromkeys(_vals))

    copcs_measured = ctx.options.get("copcs_measured") or []
    # Prefer the Justifications-tab secondary limit when provided; fall back to
    # the hardcoded default so non-Justifications runs are unchanged.
    _cl_limit = ctx.params.get("justification_cl_secondary_limit")
    try:
        _cl_limit_num = float(_cl_limit) if _cl_limit not in (None, "") else None
    except (TypeError, ValueError):
        _cl_limit_num = None
    return pd.DataFrame([{
        "Land Use": _combine_c1_c2("Landuse"),
        "Texture": _combine_c1_c2("Texture"),
        "Strata": _combine_c1_c2("Strata"),
        "COPCs": ", ".join(copcs_measured),
        "Cl Justification additional threshold": _cl_limit_num if _cl_limit_num else JUSTIFICATION_CL_SECONDARY_LIMIT,
    }])


def build_guidelines(ctx: Context) -> pd.DataFrame | None:
    """Combine all single-row guideline tables into one: rows = guideline, columns = parameters.

    Some tables already use cleaned (SQL) names and others still use raw Excel
    headers, so map raw -> cleaned first, then cleaned -> human-readable names.
    """
    _guideline_sources = {
        "Limiting Tier 1 Guideline": ctx.frames.get("limiting_tier1_guideline_df"),
        "Tier 1 with Background": ctx.frames.get("tier1_bg_df"),
        "Tier 2 Guideline": ctx.frames.get("tier2_guideline_df"),
        "Limiting Guideline Value": ctx.frames.get("limiting_df"),
        "Management Limits (Minimum)": ctx.frames.get("management_limits_df"),
    }

    # Parameter columns = numeric Excel columns (cleaned names), excluding
    # coordinates/depth.
    _parameter_cols = {
        excel_header_to_cleaned_name_map.get(c, c) for c in numeric_columns
    } - {"x", "y", "z"}

    def _guideline_row(name: str, df: pd.DataFrame) -> pd.Series:
        """Return one guideline row keyed by cleaned parameter name, numeric/parameter columns only."""
        row = df.rename(columns=excel_header_to_cleaned_name_map).iloc[0]
        row = row[[c for c in row.index if c in _parameter_cols]]
        return row.rename(name)

    rows = [
        _guideline_row(n, d)
        for n, d in _guideline_sources.items()
        if d is not None and not d.empty
    ]
    if not rows:
        return None

    all_guidelines_df = pd.DataFrame(rows)
    all_guidelines_df.index.name = "Guideline"

    # Keep only parameters with at least one guideline value, then use readable names.
    all_guidelines_df = (
        all_guidelines_df.loc[:, all_guidelines_df.notna().any()]
        .rename(columns=cleaned_name_to_excel_header_map)
    )
    return all_guidelines_df


# ---------------------------------------------------------------------------
# Excel export column manifests — reference-workbook parity
#
# The four exceedance/rating sheets below must match the reference workflow's
# columns exactly (same names, same order, nothing extra). These are built as
# EXPORT-ONLY frames so the in-app tables and the row logic stay untouched.
# ---------------------------------------------------------------------------

_TIER1_EXPORT_COLUMNS = [
    "Media", "Sample ID", "Depth (m)", "Subarea", "APEC", "Parameter", "Label",
    "Chemical Group", "Value", "Tier 2 Guideline", "Guideline",
    "Limiting Guideline", "10X guideline", "Mgmt Limit", "Exceeds Mgmt Limit",
    "Chloride (mg/kg)", "Chloride (mg/L)", "Sulphate (mg/L)",
    "Justified (Yes/No)", "Justification Reason",
]

_SITE_SPECIFIC_EXPORT_COLUMNS = [
    "Media", "Sample ID", "Depth (m)", "Subarea", "APEC", "Parameter", "Label",
    "Chemical Group", "Value", "Tier 2 Guideline", "Guideline",
    "Limiting Guideline", "10X guideline", "Mgmt Limit", "Exceeds Mgmt Limit",
    "Chloride (mg/kg)", "Chloride (mg/L)", "Sulphate (mg/L)", "Tier 1 w BG",
]

_ROSC_EXPORT_COLUMNS = [
    "Grouping", "Media", "Sample ID", "Depth (m)", "Subarea", "APEC",
    "Parameter", "Label", "Chemical Group", "Value", "Tier 2 Guideline",
    "Guideline", "Limiting Guideline", "10X guideline", "Mgmt Limit",
    "Exceeds Mgmt Limit", "Chloride (mg/kg)", "Chloride (mg/L)",
    "Sulphate (mg/L)",
]


def _sulphate_mg_l_series(ctx: Context, df: pd.DataFrame) -> pd.Series:
    """Sulphate (mg/L) per displayed sample row, matched to soil_data_filtered.

    Matched on (sample_id, depth_m) so each exceedance row reports the sulphate
    concentration of the physical sample it came from.
    """
    soil = ctx.frames.get("soil_data_filtered")
    if (soil is None or "soluble_ions_sulphate_mg_l" not in soil.columns
            or "Sample ID" not in df.columns or "Depth (m)" not in df.columns):
        return pd.Series(float("nan"), index=df.index)
    lookup = dict(zip(
        zip(soil["sample_id"].astype(str), pd.to_numeric(soil["depth_m"], errors="coerce")),
        pd.to_numeric(soil["soluble_ions_sulphate_mg_l"], errors="coerce"),
    ))
    depths = pd.to_numeric(df["Depth (m)"], errors="coerce")
    return pd.to_numeric(
        [lookup.get((str(sid), d)) for sid, d in zip(df["Sample ID"].astype(str), depths)],
        errors="coerce",
    )


def build_tier1_exceedances_export(ctx: Context) -> pd.DataFrame | None:
    """"Tier 1 Exceedances" sheet: Tier 1 columns + Justified / Justification Reason."""
    just = ctx.frames.get("justified_exceedances_display_df")
    if just is None:
        just = ctx.frames.get("tier1_exceedances_display_df")
    if just is None or just.empty:
        return None
    df = just.rename(columns={
        "Tier 1 Guideline": "Guideline",
        "Justified": "Justified (Yes/No)",
    })
    if "Justified (Yes/No)" not in df.columns:
        df["Justified (Yes/No)"] = "No"
    if "Justification Reason" not in df.columns:
        df["Justification Reason"] = None
    df["Sulphate (mg/L)"] = _sulphate_mg_l_series(ctx, df)
    return df[_TIER1_EXPORT_COLUMNS]


def build_site_specific_exceedances_export(ctx: Context) -> pd.DataFrame | None:
    """Site-Specific Exceedances sheet: reference columns, Tier 1 w BG last."""
    base = _first_present(
        ctx.frames.get("site_specific_sst_exceedances_display_df"),
        ctx.frames.get("site_specific_tier1_exceedances_display_df"),
    )
    if base is None or base.empty:
        return None
    df = base.rename(columns={"Tier 1 Guideline": "Guideline"})
    df["Sulphate (mg/L)"] = _sulphate_mg_l_series(ctx, df)
    if "Tier 1 w BG" in df.columns:
        df["Tier 1 w BG"] = df.pop("Tier 1 w BG")  # move to last position
    return df[_SITE_SPECIFIC_EXPORT_COLUMNS]


def build_rosc_exceedances_export(ctx: Context) -> pd.DataFrame | None:
    """ROSC Exceedances sheet: reference columns with Grouping first."""
    rosc = ctx.frames.get("max_exceedances_per_subarea_df")
    if rosc is None or rosc.empty:
        return None
    df = rosc.rename(columns={"Tier 1 Guideline": "Guideline"})
    df["Sulphate (mg/L)"] = _sulphate_mg_l_series(ctx, df)
    return df[_ROSC_EXPORT_COLUMNS]


def build_ec_sar_rating_categories_export(ctx: Context) -> pd.DataFrame | None:
    """EC & SAR Rating Categories sheet: Comments replaced with the filled-down APEC."""
    report = ctx.frames.get("ec_sar_category_report_df")
    if report is None or report.empty:
        return None
    df = report.rename(columns={
        "ec_category": "EC Category",
        "sar_category": "SAR Category",
    })
    soil = ctx.frames.get("soil_data_filtered")
    apec = soil["apec"].reindex(df.index) if (soil is not None and "apec" in soil.columns) else None
    df = df.drop(columns=["Comments"], errors="ignore")
    df.insert(2, "APEC", apec if apec is not None else None)
    return df[["Sample ID", "Z", "APEC", "EC Category", "SAR Category",
               "Chloride (mg/kg)", "Chloride (mg/L)"]]


def build_export_workbook(ctx: Context) -> io.BytesIO:
    """Write the export sheets into an in-memory .xlsx and return the buffer.

    Sheets are written in the notebook's export order. Frames that are absent
    or empty are skipped so a partial run still produces a valid workbook.
    """
    buf = io.BytesIO()

    # (sheet_name, frame) pairs in the notebook's export order. The "Metals",
    # "Surface_PHC", and "Converted Ion Units" sheets are omitted (not ported /
    # skipped by decision). Texture is exported as one sheet per depth split.
    sheets: list[tuple[str, pd.DataFrame | None]] = [
        # EC & SAR Rating Categories: Comments replaced with the filled-down APEC.
        ("EC & SAR Rating Categories", build_ec_sar_rating_categories_export(ctx)),
        ("SAR Report Summary Tables", ctx.frames.get("sar_report_data_display_df")),
        ("EC Report Summary Tables", ctx.frames.get("ec_report_data_display_df")),
        ("SCARG Guideline Summary", ctx.frames.get("scarg_rating_guideline_summary_df")),
        ("Borehole_Characteristics", ctx.frames.get("borehole_characteristics")),
        ("NPP-Test Stats", ctx.frames.get("npp_test_statistics")),
        ("NPP-Profile Interpretation", _npp_profile_interpretation(ctx)),
        ("TDS", ctx.frames.get("tds_grouped_data")),
        ("Site-Specific Exceedances", build_site_specific_exceedances_export(ctx)),
        ("Site Summary", build_site_summary(ctx)),
        ("Borehole Rationale", ctx.frames.get("borehole_rationale_df")),
        ("Tier 1 Exceedances", build_tier1_exceedances_export(ctx)),
        ("ROSC Exceedances", build_rosc_exceedances_export(ctx)),
    ]

    # slug -> display name for the 95th Percentile subarea sheet names.
    p95_subareas = ctx.options.get("p95_subareas") or {}

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df in sheets:
            if df is not None and not df.empty:
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        # Guidelines sheet: one row per guideline, one column per parameter,
        # written with its index (the Guideline labels).
        _guidelines = build_guidelines(ctx)
        if _guidelines is not None and not _guidelines.empty:
            _guidelines.to_excel(writer, sheet_name="Guidelines", index=True)

        # Background appendix sheets (dict of sheet_name -> df), e.g.
        # "0.0-0.3", "1.0-1.5 Pre-Outlier", "1.5-6.0", ...
        appendix = ctx.exports.get("background_appendix_sheet_dfs") or {}
        for sheet_name, df in appendix.items():
            if df is not None and not df.empty:
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        # Texture split tables: one sheet per depth split, e.g. "Texture 0-1.5".
        for frame_key, df in ctx.frames.items():
            if df is None or df.empty:
                continue
            if frame_key.startswith("texture_split_"):
                depth_range = frame_key[len("texture_split_"):]
                df.to_excel(writer, sheet_name=f"Texture {depth_range}"[:31], index=False)

        # 95th Percentile Chloride / Vertical Mass / Stats per subarea.
        for frame_key, df in ctx.frames.items():
            if df is None or df.empty:
                continue
            if frame_key.startswith("p95_subsoil_mass_"):
                slug = frame_key[len("p95_subsoil_mass_"):]
                name = p95_subareas.get(slug, slug)
                df.to_excel(writer, sheet_name=f"95PCT Chloride {name}"[:31], index=False)
            elif frame_key.startswith("p95_vertical_mass_"):
                slug = frame_key[len("p95_vertical_mass_"):]
                name = p95_subareas.get(slug, slug)
                df.to_excel(writer, sheet_name=f"95PCT VMass {name}"[:31], index=False)
            elif frame_key.startswith("p95_stats_"):
                slug = frame_key[len("p95_stats_"):]
                name = p95_subareas.get(slug, slug)
                df.to_excel(writer, sheet_name=f"95PCT Stats {name}"[:31], index=False)

    buf.seek(0)
    return buf


def build_charts_zip(ctx: Context) -> io.BytesIO | None:
    """Write the generated figures as PNGs into a zip with a folder hierarchy.

    The figures are collected during the pipeline run by each chart workflow's
    ``_store_figure`` helper into ``ctx.exports['figure_files']`` as
    ``{zip_path: png_bytes}`` (150 dpi, tight bounding box, white background).
    Returns ``None`` when no figures were generated.

    Folder layout (per the export spec):
        CL_DELINEATION/Chloride_Delineation_1.png, _2.png, ...
        BG_CHLORIDE/{Y}_{X}.png
        TIER1_GRAPHS/t1_ec.png, t1_sar.png, t1_cl.png, {parameter}.png

    If two figures would get the same path, the later one overwrites the
    earlier one (dict semantics).
    """
    figure_files = ctx.exports.get("figure_files") or {}
    if not figure_files:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, png in figure_files.items():
            zf.writestr(path, png)
    buf.seek(0)
    return buf