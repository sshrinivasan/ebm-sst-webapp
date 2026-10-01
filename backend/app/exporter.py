"""Excel + charts export — write the analysis frames to a multi-sheet workbook
and the generated charts to a zip with a folder hierarchy.

Maps the notebook's export dataframes to the webapp's ``ctx.frames`` /
``ctx.exports`` (see the export cells in the SST notebook). The "Metals" and
"Surface_PHC" sheets are intentionally omitted for now — the notebook's
"Split Metals and PHC data" step has not been ported to the webapp yet.
"""
from __future__ import annotations

import base64
import io
import zipfile

import pandas as pd

from .bg_chloride import _bg_figure_name
from .context import Context


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
        ("EC & SAR Rating Categories", ctx.frames.get("ec_sar_category_report_df")),
        ("SAR Report Summary Tables", ctx.frames.get("sar_report_data_display_df")),
        ("EC Report Summary Tables", ctx.frames.get("ec_report_data_display_df")),
        ("SCARG Guideline Summary", ctx.frames.get("scarg_rating_guideline_summary_df")),
        ("Borehole_Characteristics", ctx.frames.get("borehole_characteristics")),
        ("NPP-Test Stats", ctx.frames.get("npp_test_statistics")),
        ("NPP-Profile Interpretation", _npp_profile_interpretation(ctx)),
        ("TDS", ctx.frames.get("tds_grouped_data")),
        ("Site-Specific Exceedances", ctx.frames.get("all_exceedances_display_df")),
        ("Tier 1 Exceedances", ctx.frames.get("tier1_exceedances_display_df")),
        ("ROSC Exceedances", ctx.frames.get("max_exceedances_per_subarea_df")),
    ]

    # slug -> display name for the 95th Percentile subarea sheet names.
    p95_subareas = ctx.options.get("p95_subareas") or {}

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df in sheets:
            if df is not None and not df.empty:
                df.to_excel(writer, sheet_name=sheet_name, index=False)

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


def _png_bytes(data_uri: str) -> bytes:
    """Decode a ``data:image/png;base64,...`` chart URI to raw PNG bytes."""
    if data_uri.startswith("data:image/png;base64,"):
        return base64.b64decode(data_uri.split(",", 1)[1])
    raise ValueError("chart is not a PNG data URI")


def build_charts_zip(ctx: Context) -> io.BytesIO:
    """Write the generated charts as PNGs into a zip with a folder hierarchy.

    ``Tier1_Charts/``
        EC.png, SAR.png, Chloride.png (the Tier 1 profile charts), plus one
        file per variable graph named after the plotted parameter with units
        stripped (e.g. ``Sulphate.png`` when "Sulphate (mg/L)" was plotted).

    ``BG_Chloride/``
        One file per BG Chloride scatter plot named ``{Y}_{X}.png`` per the
        BG Chloride naming convention (reuses ``_bg_figure_name`` from
        bg_chloride.py): units removed, division rendered with a hyphen
        (e.g. ``Cl-SO4_Cl.png``).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Tier 1 profile charts.
        tier1_charts = {
            "tier1_graph_ec": "EC.png",
            "tier1_graph_sar": "SAR.png",
            "tier1_graph_chloride": "Chloride.png",
        }
        for key, name in tier1_charts.items():
            uri = ctx.charts.get(key)
            if uri:
                zf.writestr(f"Tier1_Charts/{name}", _png_bytes(uri))

        # Variable graphs: name after the plotted parameter (units stripped).
        for n in (1, 2, 3):
            uri = ctx.charts.get(f"tier1_variable_graph_{n}")
            if not uri:
                continue
            param = str(ctx.params.get(f"variable_graph_{n}") or "").strip()
            base = param.split("(", 1)[0].strip() or f"Graph {n}"
            zf.writestr(f"Tier1_Charts/{base}.png", _png_bytes(uri))

        # BG Chloride scatter plots: {Y}_{X}.png per the naming convention.
        for n in (1, 2, 3):
            uri = ctx.charts.get(f"bg_chloride_plot_{n}")
            if not uri:
                continue
            x_args = (
                ctx.params.get(f"plot{n}_x_axis_metric1"),
                ctx.params.get(f"plot{n}_x_axis_metric2"),
                ctx.params.get(f"plot{n}_x_operation") or "A only",
            )
            y_args = (
                ctx.params.get(f"plot{n}_y_axis_metric1"),
                ctx.params.get(f"plot{n}_y_axis_metric2"),
                ctx.params.get(f"plot{n}_y_operation") or "A only",
            )
            zf.writestr(f"BG_Chloride/{_bg_figure_name(x_args, y_args)}", _png_bytes(uri))

    buf.seek(0)
    return buf