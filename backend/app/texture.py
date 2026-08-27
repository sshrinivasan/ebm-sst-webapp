import base64
import io
import math

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
import matplotlib.pyplot as plt
from .context import Context


def _clean_scalar(v):
    """JSON-safe scalar: NaN/Inf/None -> None, numpy scalars -> python."""
    if v is None or v is pd.NA:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _df_to_records(df: pd.DataFrame) -> dict:
    """JSON-safe {columns, rows} for the frontend (mirrors pipeline.df_to_records)."""
    columns = [str(c) for c in df.columns]
    rows = [
        {str(col): _clean_scalar(val) for col, val in zip(columns, row)}
        for row in df.itertuples(index=False, name=None)
    ]
    return {"columns": columns, "rows": rows}

wanted_columns = [
    "sample_id",
    "depth_m",
    "z",
    "comments",
    "particle_size_sand",
    "particle_size_silt",
    "particle_size_clay",
    "particle_size_75_micron_sieve_ret",
    "particle_size_fine_coarse",
    "particle_size_soil_texture",
    "general_inorganics_saturation",
]

texture_split_depth_columns = [
    "sample_id",
    "depth_m",
    "particle_size_sand",
    "particle_size_silt",
    "particle_size_clay",
    "particle_size_soil_texture",
    "particle_size_75_micron_sieve_ret",
    "particle_size_fine_coarse",
    "clay_content",
]

# Create statistics row
def make_row_with_means(df):
    mean_values = df[
        [
            "particle_size_sand",
            "particle_size_silt",
            "particle_size_clay",
            "particle_size_75_micron_sieve_ret",
        ]
    ].mean(axis=0)
    
    new_row = {col: None for col in df.columns}
    
    for col in mean_values.index:
        new_row[col] = mean_values[col]
    
    new_row["sample_id"] = "AVERAGE"
    new_row["z"] = None
    
    # Set Fine/Coarse for the average row
    if new_row["particle_size_75_micron_sieve_ret"] is not None:
        if new_row["particle_size_75_micron_sieve_ret"] <= 50.0:
            new_row["particle_size_fine_coarse"] = "Fine"
        else:
            new_row["particle_size_fine_coarse"] = "Coarse"

    new_row["particle_size_soil_texture"] = None
    
    # Set clay content for the average row
    if new_row["particle_size_clay"] < 18.0:
        new_row["clay_content"] = "Low"
    elif new_row["particle_size_clay"] >= 36.0:
        new_row["clay_content"] = "High"
    else:
        new_row["clay_content"] = "Medium"

    return new_row


def texture_analysis(ctx: Context) -> Context:
    soil_data_filtered = ctx.frames.get("soil_data_filtered")
    texture_df = soil_data_filtered[
        soil_data_filtered[["particle_size_sand", "particle_size_silt", "particle_size_clay", "particle_size_75_micron_sieve_ret"]].notna().any(axis=1)
    ]
    texture_df = texture_df[wanted_columns]
    # TODO: Update this to keep all samples where any ctexture column has a number
    texture_df.sort_values(by=['z'], inplace=True)

    texture_df["clay_content"] = pd.cut(
    texture_df["particle_size_clay"],
    bins=[-float("inf"), 18, 36, float("inf")],
    labels=["Low", "Medium", "High"],
    right=False,
    )
    bins = [-float("inf"), 20, 50, 70, 90, 120, 130, float("inf")]
    labels = [
        "Below range",
        "Potentially coarse by sieve",
        "Likely fine",
        "Very likely fine",
        "Possibly fine or coarse",
        "Very likely coarse",
        "Above range",
    ]
    texture_df["texture_by_sat_pc"] = pd.cut(
        texture_df["general_inorganics_saturation"],
        bins=bins,
        labels=labels,
        right=False,  # left-inclusive/exclusive right
        include_lowest=True,
    )
    texture_df_display_headers = {
        "sample_id": "Location",
        "depth_m": "Depth (m)",
        "z": "Z",
        "comments": "Comments",
        "general_inorganics_saturation": "Sat (%)",
        "particle_size_sand": "Sand (%)",
        "particle_size_silt": "Silt (%)",
        "particle_size_clay": "Clay (%)",
        "particle_size_soil_texture": "Classification",
        "particle_size_75_micron_sieve_ret": "> 75um (% ret)",
        "particle_size_fine_coarse": "Grain Size",
        "clay_content": "Clay Content",
        "texture_by_sat_pc": "Texture by Sat %"
    }
    texture_df_display = texture_df.rename(columns=texture_df_display_headers).copy()
    texture_text_cols = ["Location", "Depth (m)", "Comments", "Grain Size", "Classification", "Clay Content", "Texture by Sat %"]
    texture_numeric_cols = texture_df_display.columns.difference(texture_text_cols)
    texture_df_display[texture_numeric_cols] = texture_df_display[texture_numeric_cols].apply(pd.to_numeric, errors="coerce")
    texture_df_display[texture_text_cols] = texture_df_display[texture_text_cols].astype("object").where(texture_df_display[texture_text_cols].notna(), "-").replace({"None": "-", "nan": "-"})
    texture_df_display = texture_df_display.round(3)
    ctx.frames["texture_analysis"] = texture_df_display
    
    # User-defined texture depth intervals (input table on the "Texture" tab).
    # Defaults to a single row at 1.5 m when not provided.
    texture_depth_user = pd.DataFrame(ctx.params.get("texture_depth_user") or [{"depth": 1.5}])
    ranges = []
    start = 0.0
    for td in texture_depth_user["depth"]:
        end = float(td)
        ranges.append((start, end))
        start = end
    
    ranges.append((start, 100.0))


    # Split texture_df into a list of DataFrames by 'z' ranges. Each split is
    # stored under a dynamic key `texture_split_{start}-{end}` so the frontend
    # can render one subtab per depth range with a human-readable label
    # (see manifest.py / App.tsx prefix convention).
    for start_val, end_val in ranges:
        # Filter texture_df for current range (inclusive start, exclusive end)
        mask = (texture_df["z"] >= start_val) & (texture_df["z"] < end_val)
        split_texture_df = texture_df.loc[mask].copy()
        # Only choose the columns of interest for the split depth display
        split_texture_df = split_texture_df[texture_split_depth_columns]
        # For each split, get a statistics row.
        mean_row_1 = make_row_with_means(split_texture_df)
        split_texture_df = pd.concat([split_texture_df, pd.DataFrame([mean_row_1], columns=split_texture_df.columns)], ignore_index=True)
        split_texture_df = split_texture_df.round(2)
        split_texture_df = split_texture_df.where(pd.notnull(split_texture_df), '-')
        split_texture_df = split_texture_df.rename(columns=texture_df_display_headers)

        key = f"texture_split_{start_val:g}-{end_val:g}"
        ctx.frames[key] = split_texture_df
        ctx.outputs[key] = _df_to_records(split_texture_df)

    return ctx


def render_saturation_profile(df, samples):
    profile_type_map = {
        "Saturation": "general_inorganics_saturation",
    }

    fig, ax = plt.subplots(figsize=(4, 6))

    for idx, (profile_type, colname) in enumerate(profile_type_map.items()):
        for sample in samples:
            sample_data = df.loc[
                df["sample_id"] == sample,
                ["z", colname],
            ].apply(pd.to_numeric, errors="coerce").dropna()
            sample_data = (
                sample_data
                .groupby("z", as_index=False)[colname]
                .mean()
                .sort_values("z")
            )
            x_data = sample_data["z"].to_numpy()
            y_data = sample_data[colname].to_numpy()

            if len(x_data) > 5:
                xnew = np.linspace(x_data.min(), x_data.max(), num=200, endpoint=True)

                # Plot and interpolate the data
                cspline = PchipInterpolator(x_data, y_data)
                interp_plot = ax.plot(cspline(xnew), xnew, '-', label=sample)
                ax.plot(y_data, x_data, 'o', color=interp_plot[0].get_color())
            elif len(x_data) > 0:
                ax.plot(y_data, x_data, 's', label=sample)

    ax.invert_yaxis()
    ax.set_ylim(top=0)
    ax.axhline(y=1.0, linestyle="--", color="black", label="1.0m")
    ax.xaxis.set_label_position('top')
    ax.set_xlabel("{0} (%)".format(profile_type))
    ax.set_ylabel("Depth (mbgs)")
    ax.grid(which='major', color='#DDDDDD', linewidth=0.8)
    # Minor grid as well
    ax.grid(which='minor', color='#DDDDDD', linestyle=':', linewidth=0.8)
    ax.minorticks_on()
    plt.tight_layout()
    fig.legend(loc='upper left', bbox_to_anchor=(0, 0), ncol=4, frameon=False)
    return fig

def _fig_to_data_uri(fig) -> str:
    """Serialize a matplotlib figure to a base64 PNG data URI and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def saturation_profile(ctx: Context) -> Context:
    soil_data_filtered = ctx.frames.get("soil_data_filtered")
    saturation_profile_df = soil_data_filtered[soil_data_filtered["general_inorganics_saturation"].notnull() & (soil_data_filtered["general_inorganics_saturation"] != "")]
    # Samples come from the saturation_profile_samples multiselect (seeded from
    # sample_ids). Default to all available samples when not provided.
    samples = ctx.params.get("saturation_profile_samples") or list(saturation_profile_df["sample_id"].unique())
    fig = render_saturation_profile(saturation_profile_df, samples)
    ctx.charts["saturation_profile"] = _fig_to_data_uri(fig)

    scatter_fig, scatter_ax = plt.subplots(figsize=(3, 3))
    scatter_ax.scatter(
        soil_data_filtered["particle_size_sand"],
        soil_data_filtered["particle_size_clay"],
        alpha=0.7,
    )
    scatter_ax.set_xlabel("Percent Sand")
    scatter_ax.set_ylabel("Percent Clay")
    scatter_ax.set_title("Soil Texture")
    scatter_ax.grid(True, which='both', axis='both', linestyle='--', linewidth=0.5)
    scatter_ax.set_xticks(range(0, 101, 10))
    scatter_ax.set_yticks(range(0, 101, 10))
    scatter_ax.set_xlim(0, 100)
    scatter_ax.set_ylim(0, 100)
    scatter_fig.tight_layout()
    ctx.charts["sand_clay_scatter"] = _fig_to_data_uri(scatter_fig)

    return ctx
