"""Loader tests for the SST app.

Runs the loader on a fixed Soil Analytical File and asserts the parsed
`soil_data_filtered` dataframe matches the Hex app's exported output for the
same file (extracted_soil_data_2026-08-21T1353.csv) — Hex is the source of truth.
"""
from pathlib import Path

from app.context import Context
from app.params import defaults
from app.loader import load

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample_soil_table.xlsm"


def _run_loader():
    ctx = Context(excel_path=str(SAMPLE), params={**defaults(), "sheet_name": "Soil Table"})
    return load(ctx).frames["soil_data_filtered"]


def test_soil_data_filtered_shape_and_columns():
    df = _run_loader()
    assert df.shape == (164, 110)
    assert list(df.columns[:5]) == ["sample_id", "depth_m", "date", "lab_id", "x"]
    assert "soluble_ions_chloride_mg_l" in df.columns


# Values taken from the Hex app's exported `soil_data_filtered` for this file.
# Confirms our loader reproduces Hex, including the tricky rows (14-B* top/bottom
# depths, BH25-13's Z offset from Depth, "<9"->9 numeric cleaning).
HEX_SPOT_CHECKS = [
    ("BH25-01", 0.225, "general_inorganics_ph", 6.6),
    ("BH25-01", 0.225, "general_inorganics_ec_ds_m", 0.35),
    ("BH25-01", 0.225, "soluble_ions_chloride_mg_l", 9.0),
    ("BH25-02", 1.25, "particle_size_soil_texture", "Clay Loam"),
    ("BH25-02", 1.25, "particle_size_fine_coarse", "Fine"),
    ("BH25-05", 0.1, "apec", "Outside Modelled Area"),
    ("14-B5", 0.225, "general_inorganics_ph", 5.1),
    ("14-B5", 0.225, "soluble_ions_chloride_mg_l", 1090.0),
    ("14-B5", 0.225, "apec", "Flare Pit"),
    ("14-B5", 0.225, "subarea", "SA2"),
    ("14-B5", 0.225, "x", 0.15),
    ("14-B6", 1.25, "soluble_ions_chloride_mg_l", 9370.0),
    ("14-B12", 0.8, "apec", "DWDA"),
    ("14-B12", 0.8, "subarea", "SA3"),
    ("BH25-13", 1.0, "apec", "Flare Pit"),
    ("BH25-14", 2.0, "general_inorganics_ec_ds_m", 6.55),
]


def test_matches_hex_output():
    df = _run_loader()
    for sid, z, col, expected in HEX_SPOT_CHECKS:
        rows = df[(df["sample_id"] == sid) & (df["z"] == z)]
        assert len(rows) == 1, f"expected exactly one row for {sid}@z{z}"
        got = rows.iloc[0][col]
        if isinstance(got, str):
            got = got.strip()
        if isinstance(expected, float):
            assert abs(got - expected) < 1e-6, f"{sid}@z{z} {col}: {got} != {expected}"
        else:
            assert got == expected, f"{sid}@z{z} {col}: {got!r} != {expected!r}"
