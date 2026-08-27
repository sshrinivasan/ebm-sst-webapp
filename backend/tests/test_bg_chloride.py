"""Regression test: the BG Chloride data table matches the reference export
(table_194) for the 2026_small_npp Soil Analytical File.

The reference CSV was exported from the Hex app for the same input file. Every
cell must match (with blank handling and a small float tolerance), so a value
attributed to the wrong sample/depth or a unit-conversion drift fails the test.
"""
from pathlib import Path

import pandas as pd

from app.pipeline import run

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample_soil_table.xlsm"
EXPECTED = FIXTURES / "bg_chloride_df_expected.csv"


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan", "None", "NA", "<NA>")


def _cell_eq(a, b) -> bool:
    if _blank(a) and _blank(b):
        return True
    if _blank(a) or _blank(b):
        return False
    try:
        return abs(float(a) - float(b)) < 0.005
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def test_bg_chloride_df_matches_hex():
    got = run(str(SAMPLE), {"sheet_name": "Soil Table"}).frames["bg_chloride_df"].reset_index(drop=True)
    exp = pd.read_csv(EXPECTED)
    assert list(got.columns) == list(exp.columns)
    assert got.shape == exp.shape
    for r in range(len(exp)):
        for c in exp.columns:
            assert _cell_eq(got.iloc[r][c], exp.iloc[r][c]), \
                f"[{got.iloc[r]['Location']}][{c!r}]: {got.iloc[r][c]!r} != {exp.iloc[r][c]!r}"