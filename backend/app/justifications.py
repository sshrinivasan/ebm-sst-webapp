"""Exceedance Justifications workflow.

Produces a static ``justified_exceedances_display_df`` frame: the Tier 1
exceedances display frame (``tier1_exceedances_display_df``) plus two computed,
display-named columns — ``Justified`` and ``Justification Reason`` (the Tier 1
frame itself is never mutated). Three inputs drive the automatic justification
of the selected salinity exceedances:

- ``justification_cl_secondary_limit`` — chloride secondary limit (mg/L when SST
  is off, mg/kg when SST is on; the label is switched in manifest.build_schema).
- ``select_salinity_parameters`` — which salinity parameters (pH/EC/SAR) are
  considered for justification (multiselect, all selected by default).
- ``justify_100_mg_l`` — allow the "Naturally Occurring" justification for
  chloride concentrations below 100.

Auto-justification rules:
- Naturally Occurring: row is a selected salinity parameter and chloride < 100
  (only when ``justify_100_mg_l`` is on).
- Low Risk: row is a selected salinity parameter and
  100 <= chloride <= secondary limit (only when a positive secondary limit has
  been entered).
"""
from __future__ import annotations

import pandas as pd

from .context import Context
from .loader import cleaned_name_to_excel_header_map

# Multiselect choices ("pH", "EC", "SAR") -> cleaned exceedance parameter keys
# used by the `exceedance_parameter` column of the Tier 1 exceedances frame.
SALINITY_PARAMETER_KEYS = {
    "ph": "general_inorganics_ph",
    "ec": "general_inorganics_ec_ds_m",
    "sar": "general_inorganics_sar",
}

# Display "Parameter" header -> cleaned key (inverse of the loader map). The
# Tier 1 display frame carries Excel header names (e.g. "EC (dS/m)") in its
# Parameter column, so this recovers the cleaned key the rules match against.
_EXCEL_TO_CLEANED = {v: k for k, v in cleaned_name_to_excel_header_map.items()}


def _selected_salinity_params(ctx: Context) -> list[str]:
    """Cleaned exceedance keys the user wants considered for justification."""
    return [
        SALINITY_PARAMETER_KEYS[str(p).strip().lower()]
        for p in (ctx.params.get("select_salinity_parameters") or [])
        if str(p).strip().lower() in SALINITY_PARAMETER_KEYS
    ]


def _chloride_column(ctx: Context) -> str:
    """Chloride column the secondary limit is expressed in.

    Mirrors the chloride-units defaults (mg/L with SST off, mg/kg with SST on)
    and the label switching in manifest.build_schema.
    """
    return "Chloride (mg/kg)" if bool(ctx.params.get("sst_flag", False)) else "Chloride (mg/L)"


def exceedance_justifications(ctx: Context) -> Context:
    """Compute 'Justified' + 'Justification Reason' on the Tier 1 exceedances."""
    # The Tier 1 exceedances display frame is read-only input; the justified
    # frame is a separate copy stored under its own key.
    display_df = ctx.frames["tier1_exceedances_display_df"].copy()

    _selection = _selected_salinity_params(ctx)
    _cl_col = _chloride_column(ctx)
    _cl = pd.to_numeric(display_df[_cl_col], errors="coerce")
    _is_selected = (
        display_df["Parameter"].map(lambda v: _EXCEL_TO_CLEANED.get(str(v).strip())).isin(_selection)
    )

    try:
        _secondary_limit = float(ctx.params.get("justification_cl_secondary_limit"))
    except (TypeError, ValueError):
        _secondary_limit = None

    # Naturally Occurring: toggle on AND selected salinity param AND chloride < 100.
    _naturally_occurring = (
        _is_selected
        & bool(ctx.params.get("justify_100_mg_l", True))
        & (_cl < 100)
    )

    # Low Risk: positive secondary limit set AND 100 <= chloride <= secondary limit.
    if (_secondary_limit or 0) > 0:
        _low_risk = _is_selected & _cl.between(100, _secondary_limit)
    else:
        _low_risk = pd.Series(False, index=display_df.index)

    display_df["Justified"] = "No"
    display_df["Justification Reason"] = None
    display_df.loc[_naturally_occurring, "Justified"] = "Yes"
    display_df.loc[_naturally_occurring, "Justification Reason"] = "Naturally Occurring"
    display_df.loc[_low_risk, "Justified"] = "Yes"
    display_df.loc[_low_risk, "Justification Reason"] = "Low Risk"

    ctx.frames["justified_exceedances_display_df"] = display_df
    return ctx
