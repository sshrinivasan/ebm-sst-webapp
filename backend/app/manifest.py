"""Presentation manifest: tabs/nav and output tables for the frontend.

Mirrors ebm-webapp's schema contract so the same (schema-driven) frontend works
unchanged. Grow NAV and OUTPUTS as we port analysis sections.
"""
from __future__ import annotations

from .params import PARAMS

# tabs
NAV = [
    {"id": "input_config", "title": "Input Configuration", "icon": "sliders"},
    {"id": "data", "title": "Data", "icon": "table"},
    {"id": "ec_sar", "title": "EC / SAR Rating", "icon": "table"},
    {"id": "background", "title": "Background & Guidelines", "icon": "table"},
    {"id": "borehole", "title": "Borehole Characteristics", "icon": "table"},
    {"id": "exceedances", "title": "Exceedances", "icon": "alert"},
    {"id": "tier1_graphs", "title": "Tier 1 Graphs", "icon": "chart"},
    {"id": "bg_chloride", "title": "BG Chloride", "icon": "chart"},
    {"id": "texture", "title": "Texture", "icon": "table"},
]

# tables
OUTPUTS = [
    {"var": "soil_data_preview", "label": "Soil Analytical Data — full (for exceedances)", "tab": "data"},
    {"var": "ec_sar_category_report", "label": "EC & SAR Rating Categories", "tab": "ec_sar"},
    {"var": "scarg_rating_guideline_summary", "label": "SCARG Rating & Guideline Summary", "tab": "background"},
    {"var": "scarg_guidelines", "label": "SCARG Guidelines", "tab": "background"},
    {"var": "ec_guidelines_summary", "label": "EC Guidelines Summary", "tab": "background"},
    {"var": "sar_guidelines_summary", "label": "SAR Guidelines Summary", "tab": "background"},
    {"var": "borehole_characteristics", "label": "Borehole Characteristics", "tab": "borehole"},
    {"var": "borehole_data", "label": "Borehole Data", "tab": "borehole"},
    {"var": "tier1_exceedances", "label": "Tier 1", "tab": "exceedances"},
    {"var": "site_specific_exceedances", "label": "Site-Specific", "tab": "exceedances"},
    {"var": "bg_chloride_df", "label": "Background Chloride", "tab": "bg_chloride"},
    {"var": "texture_analysis", "label": "Texture Analysis", "tab": "texture"},
]

# Chart figures (PNG data URIs) keyed by var, grouped onto a tab. The producing
# workflow pushes each var into ctx.charts; the frontend renders it on `tab`.
CHARTS = [
    {"var": "tier1_graph_ec", "label": "EC (dS/m)", "tab": "tier1_graphs"},
    {"var": "tier1_graph_sar", "label": "SAR", "tab": "tier1_graphs"},
    {"var": "tier1_graph_chloride", "label": "Chloride (mg/kg)", "tab": "tier1_graphs"},
    # Variable Graphs sub-tab (rendered separately in the frontend).
    {"var": "tier1_variable_graph_1", "label": "Parameter 1", "tab": "tier1_graphs"},
    {"var": "tier1_variable_graph_2", "label": "Parameter 2", "tab": "tier1_graphs"},
    # BG Chloride tab: 3 identical scatter plots.
    {"var": "bg_chloride_plot_1", "label": "Plot 1", "tab": "bg_chloride"},
    {"var": "bg_chloride_plot_2", "label": "Plot 2", "tab": "bg_chloride"},
    {"var": "bg_chloride_plot_3", "label": "Plot 3", "tab": "bg_chloride"},
    # Texture tab: saturation profile + sand/clay scatter charts.
    {"var": "saturation_profile", "label": "Saturation Profile", "tab": "texture"},
    {"var": "sand_clay_scatter", "label": "Sand / Clay Scatter", "tab": "texture"},
]


def _leaves(nodes) -> list[dict]:
    out = []
    for n in nodes:
        if n.get("children"):
            out += _leaves(n["children"])
        else:
            out.append({"id": n["id"], "title": n["title"]})
    return out


# Dynamic outputs: the workflow produces a variable number of tables keyed by a
# prefix (e.g. texture_split_0, texture_split_1, ...). The frontend renders each
# present key as its own subtab on the declared tab.
DYNAMIC_OUTPUTS = [
    {"prefix": "texture_split_", "tab": "texture", "label_prefix": "Depth: "},
]


def build_schema() -> dict:
    # example = default so the frontend prefills the control.
    inputs = [{**p, "example": p.get("default")} for p in PARAMS]
    return {
        "nav": NAV,
        "tabs": _leaves(NAV),
        "inputs": inputs,
        "outputs": OUTPUTS,
        "charts": CHARTS,
        "dynamic_outputs": DYNAMIC_OUTPUTS,
    }
