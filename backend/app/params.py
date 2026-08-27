"""Input parameters — hand-authored (not auto-extracted from Hex).

As we port the notebook, add each input here and wire it into the module that
consumes it. This is the single place to reason about defaults.

Fields per param:
  name     variable name used by the analysis modules
  label    shown in the UI
  kind     data type hint (str | number | bool | file)
  control  frontend widget: file | text | number | select | multiselect | toggle | date
  tab      which frontend tab it appears on
  default  starting value (also prefilled in the UI)
  choices  fixed options (for select/multiselect), optional
  options  name of a Context.options list to populate choices from, optional
"""
from __future__ import annotations

from .tier1_charts import variable_graph_options
from .bg_chloride import bg_chloride_plottable_metrics

# Params surfaced in the frontend right now. Start small; grow as we port.
PARAMS: list[dict] = [
    {"name": "soil_file", "label": "Soil Analytical File (.xlsm)",
     "kind": "file", "control": "file", "tab": "input_config"},
    {"name": "sheet_name", "label": "Sheet name",
     "kind": "str", "control": "text", "tab": "input_config", "default": "Soil Table"},
    {"name": "input_water_table_depth", "label": "Water table depth (m)",
     "kind": "number", "control": "number", "tab": "input_config", "default": 1.5,
     "group": "sst"},
    {"name": "chloride_guideline", "label": "Chloride guideline (mg/kg)",
     "kind": "number", "control": "number", "tab": "input_config", "default": 100},
    {"name": "sst_flag", "label": "Site-specific (SST) enabled",
     "kind": "bool", "control": "toggle", "tab": "input_config", "default": True},
    {"name": "topsoil_depths", "label": "Topsoil / Subsoil depth intervals",
     "kind": "table", "control": "table", "tab": "input_config",
     "columns": [
         {"key": "top", "label": "Top (m)", "control": "number"},
         {"key": "bottom", "label": "Bottom (m)", "control": "number"},
         {"key": "type", "label": "Type", "control": "select", "choices": ["Topsoil", "Subsoil"]},
     ],
     "default": [
         {"top": "0",   "bottom": "0.3", "type": "Topsoil"},
         {"top": "0.3", "bottom": "1",   "type": "Subsoil"},
         {"top": "1",   "bottom": "1.5", "type": "Subsoil"},
         {"top": "1.5", "bottom": "6",   "type": "Subsoil"},
         {"top": "6",   "bottom": "12",  "type": "Subsoil"},
     ]},
    {"name": "texture_depth_user", "label": "Texture depth intervals",
     "kind": "table", "control": "table", "tab": "texture",
     "columns": [
         {"key": "depth", "label": "Depth", "control": "number"},
     ],
     "default": [
         {"depth": "1.5"},
     ]},
    {"name": "saturation_profile_samples", "label": "Samples to plot",
     "kind": "list", "control": "multiselect", "tab": "texture",
     "options": "sample_ids", "prefill": "all", "full": False},
    {"name": "tier1_graph_samples", "label": "Samples to plot",
     "kind": "list", "control": "multiselect", "tab": "tier1_graphs",
     "options": "sample_ids", "prefill": "all", "full": False},
    # Variable Graphs sub-tab: two parameter/borehole pairs feeding
    # tier1_variable_charts. Boreholes share the tier1 sample_ids option list.
    {"name": "variable_graph_1", "label": "Select Parameter",
     "kind": "str", "control": "select", "tab": "tier1_graphs",
     "choices": variable_graph_options},
    {"name": "variable_graph1_boreholes", "label": "Boreholes",
     "kind": "list", "control": "multiselect", "tab": "tier1_graphs",
     "options": "sample_ids", "prefill": "all", "full": False},
    {"name": "variable_graph_2", "label": "Select Parameter",
     "kind": "str", "control": "select", "tab": "tier1_graphs",
     "choices": variable_graph_options},
    {"name": "variable_graph2_boreholes", "label": "Boreholes",
     "kind": "list", "control": "multiselect", "tab": "tier1_graphs",
     "options": "sample_ids", "prefill": "all", "full": False},
    # BG Chloride tab: 3 identical scatter-plot configs (n = 1, 2, 3).
    *[
        param
        for n in (1, 2, 3)
        for param in (
            {"name": f"plot{n}_x_axis_metric1", "label": "X Metric A",
             "kind": "str", "control": "select", "tab": "bg_chloride",
             "choices": bg_chloride_plottable_metrics},
            {"name": f"plot{n}_x_axis_metric2", "label": "X Metric B",
             "kind": "str", "control": "select", "tab": "bg_chloride",
             "choices": bg_chloride_plottable_metrics},
            {"name": f"plot{n}_x_operation", "label": "X axis operation",
             "kind": "str", "control": "select", "tab": "bg_chloride",
             "choices": ["A only", "A/B", "B/A", "A+B"], "default": "A only"},
            {"name": f"plot{n}_x_axis_max", "label": "X axis max",
             "kind": "number", "control": "number", "tab": "bg_chloride"},
            {"name": f"plot{n}_y_axis_metric1", "label": "Y Metric A",
             "kind": "str", "control": "select", "tab": "bg_chloride",
             "choices": bg_chloride_plottable_metrics},
            {"name": f"plot{n}_y_axis_metric2", "label": "Y Metric B",
             "kind": "str", "control": "select", "tab": "bg_chloride",
             "choices": bg_chloride_plottable_metrics},
            {"name": f"plot{n}_y_operation", "label": "Y axis operation",
             "kind": "str", "control": "select", "tab": "bg_chloride",
             "choices": ["A only", "A/B", "B/A", "A+B"], "default": "A only"},
            {"name": f"plot{n}_y_axis_max", "label": "Y axis max",
             "kind": "number", "control": "number", "tab": "bg_chloride"},
        )
    ],
]

# Notebook params that have defaults but no UI control yet. Kept server-side so
# the pipeline runs; we design controls for these as we work through them.
SERVER_DEFAULTS: dict = {}


def defaults() -> dict:
    """Full default param set (UI defaults + server-only defaults)."""
    d = dict(SERVER_DEFAULTS)
    for p in PARAMS:
        if "default" in p:
            d[p["name"]] = p["default"]
    return d
