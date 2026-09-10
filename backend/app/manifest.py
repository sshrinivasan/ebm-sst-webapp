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
    {"id": "npp", "title": "NPP", "icon": "table"},
    {"id": "tds", "title": "TDS", "icon": "table"},
    {"id": "tier1_graphs", "title": "Tier 1 Graphs", "icon": "chart"},
    {"id": "bg_chloride", "title": "BG Chloride", "icon": "chart"},
    {"id": "sst_charts", "title": "SST Charts", "icon": "chart"},
    {"id": "texture", "title": "Texture", "icon": "table"},
    {"id": "95_percentile", "title": "95th Percentile", "icon": "table"},
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
    {"var": "npp_test_results", "label": "Sulphate Profile Interpretation", "tab": "npp"},
    {"var": "npp_numerical_ref_info", "label": "NPP Numerical Reference Info", "tab": "npp"},
    {"var": "npp_test_statistics", "label": "NPP Test Statistics", "tab": "npp"},
    {"var": "npp_marginal_results", "label": "Justifications", "tab": "npp"},
    {"var": "npp_selected_data", "label": "NPP Selected Data", "tab": "npp"},
    {"var": "bg_chloride_df", "label": "Background Chloride", "tab": "bg_chloride"},
    {"var": "texture_analysis", "label": "Texture Analysis", "tab": "texture"},
    {"var": "tds_data_table", "label": "TDS Data Table", "tab": "tds"},
    {"var": "tds_grouped_data", "label": "TDS Grouped Data", "tab": "tds"},
    {"var": "tds_test_results", "label": "TDS Practitioner Notes", "tab": "tds"},
    {"var": "additional_guidelines_df", "label": "Additional Guidelines", "tab": "sst_charts"},
    {"var": "chloride_plot_config", "label": "Chloride Plot Config", "tab": "sst_charts"},
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
    # NPP tab: sulphate vertical profile for the selected samples.
    {"var": "npp_profile", "label": "NPP Profile (Sulphate)", "tab": "npp"},
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

# Dynamic charts: the workflow produces a variable number of chart figures keyed
# by a prefix (e.g. p95_chloride_profile_<subarea>). The frontend renders each
# present key on the declared tab.
DYNAMIC_CHARTS = [
    {"prefix": "p95_chloride_profile_", "tab": "95_percentile", "label_prefix": "Chloride Profile: "},
]


# Tabs that belong to the site-specific (SST) analysis. When sst_flag is off,
# these tabs are removed from the schema (and the frontend hides them).
SST_TABS = {"npp", "tds", "sst_charts", "texture", "95_percentile"}

# Outputs that belong to the SST analysis. When sst_flag is off, these tables
# are removed from the schema. Note: the Exceedances tab keeps Tier 1
# (tier1_exceedances) and only the Site-Specific table is removed.
SST_OUTPUTS = {
    "site_specific_exceedances",   # Site-Specific table on the Exceedances tab
    "npp_test_results", "npp_numerical_ref_info", "npp_test_statistics",
    "npp_marginal_results", "npp_selected_data",
    "tds_data_table", "tds_grouped_data", "tds_test_results",
    "additional_guidelines_df", "chloride_plot_config",
    "texture_analysis",
}

# Charts that belong to the SST analysis.
SST_CHARTS = {
    "npp_profile",
    "saturation_profile", "sand_clay_scatter",
}

# Dynamic outputs/charts that belong to the SST analysis (prefix match).
SST_DYNAMIC_OUTPUT_PREFIXES = {"texture_split_"}
SST_DYNAMIC_CHART_PREFIXES = {"p95_chloride_profile_"}

# Params that belong to the SST analysis. When sst_flag is off, these inputs
# are removed from the schema so the frontend doesn't render them.
SST_PARAMS = {
    "npp_bg_samples", "npp_near_apec_samples", "gw_measurement_type",
    "npp_practitioner_notes",
    "tds_bg_samples", "use_custom_wt_depths", "upper_depth_limit",
    "lower_depth_limit",
    "subarea_assignments",
    "chloride_additional_guidelines", "sst_cl_x_axis_max", "chloride_plot_config",
    "texture_depth_user", "saturation_profile_samples",
}


def build_schema(sst_flag: bool = True) -> dict:
    """Build the presentation schema, optionally filtering out the SST analysis.

    When ``sst_flag`` is False, the SST tabs, outputs, charts, dynamic entries,
    and params are removed so the frontend hides them entirely. The Exceedances
    tab keeps Tier 1 (tier1_exceedances) — only the Site-Specific table is
    removed.
    """
    # example = default so the frontend prefills the control.
    inputs = [{**p, "example": p.get("default")} for p in PARAMS]

    if sst_flag:
        return {
            "nav": NAV,
            "tabs": _leaves(NAV),
            "inputs": inputs,
            "outputs": OUTPUTS,
            "charts": CHARTS,
            "dynamic_outputs": DYNAMIC_OUTPUTS,
            "dynamic_charts": DYNAMIC_CHARTS,
        }

    # --- SST disabled: filter everything ---
    nav = [n for n in NAV if n["id"] not in SST_TABS]
    tabs = _leaves(nav)
    outputs = [o for o in OUTPUTS if o["var"] not in SST_OUTPUTS]
    charts = [c for c in CHARTS if c["var"] not in SST_CHARTS]
    dynamic_outputs = [
        d for d in DYNAMIC_OUTPUTS
        if not any(d["prefix"].startswith(p) for p in SST_DYNAMIC_OUTPUT_PREFIXES)
    ]
    dynamic_charts = [
        d for d in DYNAMIC_CHARTS
        if not any(d["prefix"].startswith(p) for p in SST_DYNAMIC_CHART_PREFIXES)
    ]
    inputs = [i for i in inputs if i["name"] not in SST_PARAMS]

    return {
        "nav": nav,
        "tabs": tabs,
        "inputs": inputs,
        "outputs": outputs,
        "charts": charts,
        "dynamic_outputs": dynamic_outputs,
        "dynamic_charts": dynamic_charts,
    }
