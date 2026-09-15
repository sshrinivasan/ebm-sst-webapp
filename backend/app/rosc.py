from .context import Context
from .tier1_exceedances import tier1_exceedance_output_columns, cleaned_name_to_excel_header_map
import pandas as pd

def _parse_guideline_bounds(val):
    """Return (lower, upper) bounds for a guideline. One-sided guidelines get lower=-inf."""
    text = str(val).strip()
    parts = text.split("-")
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    try:
        return float("-inf"), float(text)
    except ValueError:
        return float("-inf"), float("nan")


def _deviation_series(values, bounds):
    """How far each value sits outside its guideline.

    One-sided guidelines reduce to value - limit, so ranking by deviation matches
    ranking by value. Two-sided guidelines (pH) can be exceeded from below.
    """
    values = pd.to_numeric(values, errors="coerce")
    parsed = bounds.map(_parse_guideline_bounds)
    lower = parsed.map(lambda b: b[0]).astype(float)
    upper = parsed.map(lambda b: b[1]).astype(float)
    deviation = pd.concat([lower - values, values - upper], axis=1).max(axis=1)
    return deviation.where(values.notna())


def rosc_exceedances(ctx: Context) -> Context:
    # TODO: select correct source dataframe
    ab_all_exceedances_df = ctx.frames["tier1_exceedances_df"]
    # Group by the user-selected ROSC grouping column and then parameter to find the maximum per group
    rosc_grouping_column_map = {
        "Subarea": "subarea",
        "APEC": "apec",
    }
    rosc_grouping_column = ctx.params.get("rosc_grouping_column", "Subarea")
    rosc_group_col = rosc_grouping_column_map.get(rosc_grouping_column, "subarea")

    ab_max_exceedances_df = ab_all_exceedances_df.copy()
    _group_values = ab_max_exceedances_df[rosc_group_col]
    _blank_mask = (
        _group_values.isna()
        | _group_values.astype(str).str.strip().isin(["", "-"])
    )
    ab_max_exceedances_df["grouping_column"] = _group_values.where(~_blank_mask, None)

    # Rank by deviation from the guideline rather than raw magnitude so that pH
    # exceedances below the lower bound compete with those above the upper bound.
    ab_max_exceedances_df["_guideline_deviation"] = _deviation_series(
        ab_max_exceedances_df["exceedance_value"],
        ab_max_exceedances_df["guideline_value"],
    ).fillna(pd.to_numeric(ab_max_exceedances_df["exceedance_value"], errors="coerce"))

    ab_max_exceedances_df = (
        ab_max_exceedances_df
        .sort_values("_guideline_deviation", ascending=False)
        .groupby(["grouping_column", "exceedance_parameter"], as_index=False, dropna=False)
        .first()
        .drop(columns=["_guideline_deviation"])
    )
    max_exceedance_output_columns = dict(tier1_exceedance_output_columns)
    ab_max_exceedances_df_display = ab_max_exceedances_df[max_exceedance_output_columns.keys()].rename(columns=max_exceedance_output_columns)
    ab_max_exceedances_df_display["Parameter"] = ab_max_exceedances_df_display["Parameter"].map(
        lambda v: cleaned_name_to_excel_header_map.get(v, v)
    )
    ab_max_exceedances_df_display["Date"] = pd.to_datetime(
        ab_max_exceedances_df_display["Date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    ab_max_exceedances_df_display = ab_max_exceedances_df_display.fillna("-").replace("", "-")
    
    ctx.frames["max_exceedances_per_subarea_df"] = ab_max_exceedances_df_display
    return ctx