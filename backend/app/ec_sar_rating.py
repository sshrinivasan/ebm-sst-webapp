"""EC & SAR rating categories workflow (notebook cells 30, 57-62).

  validate_topsoil_depths(ctx)  -> validate the topsoil/subsoil depth-band input
                                    (cell 30) -> topsoil_depths_validated
  compute_ec_sar_ratings(ctx)   -> assign Good/Fair/Poor/Unsuitable EC & SAR
                                    categories per sample using topsoil vs subsoil
                                    bins (cells 57-62) -> ec_sar_category_report_df
"""
from __future__ import annotations

import pandas as pd

from .context import Context, InputValidationError
from .loader import cleaned_name_to_excel_header_map

_ALLOWED_SOIL_TYPES = {"topsoil": "Topsoil", "subsoil": "Subsoil"}


def validate_topsoil_depths(ctx: Context) -> Context:
    """Validate the topsoil/subsoil depth table (cell 30). Raises InputValidationError."""
    df = pd.DataFrame(ctx.params.get("topsoil_depths") or [])

    if "type" not in df.columns:
        raise InputValidationError("The topsoil/subsoil depth table is missing a 'type' column.")

    # Drop fully-blank rows.
    blank = (
        df[["top", "bottom", "type"]].astype(str)
        .apply(lambda col: col.str.strip().isin(["", "None", "nan", "NaN"]))
        .all(axis=1)
    )
    df = df[~blank].copy()

    # type must be Topsoil/Subsoil (normalize casing).
    types = df["type"].astype(str).str.strip().str.lower().map(_ALLOWED_SOIL_TYPES)
    if types.isna().any():
        raise InputValidationError("Every row must have a type of 'Topsoil' or 'Subsoil'.")
    df["type"] = types

    # top/bottom numeric.
    df["top"] = pd.to_numeric(df["top"], errors="coerce")
    df["bottom"] = pd.to_numeric(df["bottom"], errors="coerce")
    if df["top"].isna().any() or df["bottom"].isna().any():
        raise InputValidationError("Every interval must have a numeric 'top' and 'bottom'.")

    df = df.sort_values("top").reset_index(drop=True)
    if (df["bottom"] <= df["top"]).any():
        raise InputValidationError("Every interval must have 'bottom' deeper than 'top'.")

    topsoil = df[df["type"] == "Topsoil"]
    if len(topsoil) > 1:
        raise InputValidationError("Only one Topsoil interval is allowed.")
    if not topsoil.empty and topsoil.index[0] != 0:
        raise InputValidationError("The Topsoil interval must be the shallowest interval.")

    # Contiguous: each row starts where the previous ended.
    gaps = [i for i in range(1, len(df)) if df.loc[i, "top"] != df.loc[i - 1, "bottom"]]
    if gaps:
        raise InputValidationError("Depth intervals must be contiguous, with no gaps or overlaps.")

    ctx.frames["topsoil_depths_validated"] = df
    return ctx


# SCARG rating thresholds (notebook cell 57).
EC_TOP_BINS = [-float("inf"), 2, 4, 8, float("inf")]
EC_SUB_BINS = [-float("inf"), 3, 5, 10, float("inf")]
SAR_BINS = [-float("inf"), 4, 8, 12, float("inf")]
RATING_LABELS = ["Good", "Fair", "Poor", "Unsuitable"]


def compute_ec_sar_ratings(ctx: Context) -> Context:
    """Assign EC & SAR categories and build ec_sar_category_report_df (cells 57-62)."""
    soil = ctx.frames["soil_data_filtered"].copy()  # de-fragment before adding columns
    validated = ctx.frames["topsoil_depths_validated"]

    topsoil_interval = validated[validated["type"] == "Topsoil"]
    if topsoil_interval.empty:
        raise InputValidationError("No Topsoil interval found in the topsoil/subsoil depth table.")
    threshold = float(topsoil_interval.iloc[0]["bottom"])

    z = pd.to_numeric(soil["z"], errors="coerce")
    soil["z"] = z
    top_mask = z < threshold
    sub_mask = z >= threshold

    ec = pd.to_numeric(soil["general_inorganics_ec_ds_m"], errors="coerce")
    soil["general_inorganics_ec_ds_m"] = ec
    soil.loc[top_mask, "ec_category"] = pd.cut(ec.loc[top_mask], bins=EC_TOP_BINS, labels=RATING_LABELS, right=True)
    soil.loc[sub_mask, "ec_category"] = pd.cut(ec.loc[sub_mask], bins=EC_SUB_BINS, labels=RATING_LABELS, right=True)

    sar = pd.to_numeric(soil["general_inorganics_sar"], errors="coerce")
    soil["general_inorganics_sar"] = sar
    soil.loc[top_mask, "sar_category"] = pd.cut(sar.loc[top_mask], bins=SAR_BINS, labels=RATING_LABELS, right=True)
    soil.loc[sub_mask, "sar_category"] = pd.cut(sar.loc[sub_mask], bins=SAR_BINS, labels=RATING_LABELS, right=True)

    ctx.frames["soil_data_filtered"] = soil  # write back the de-fragmented frame

    cols = ["sample_id", "z", "comments", "ec_category", "sar_category",
            "soluble_ions_chloride_mg_kg", "soluble_ions_chloride_mg_l"]
    report = soil[cols].rename(columns=cleaned_name_to_excel_header_map).round(1)
    ctx.frames["ec_sar_category_report_df"] = report
    return ctx
