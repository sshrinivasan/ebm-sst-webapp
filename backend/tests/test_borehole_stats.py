"""Regression test: the borehole characteristics table matches the Hex
reference export for the sample Soil Analytical File."""
from pathlib import Path

import pandas as pd

from app.pipeline import run

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample_soil_table.xlsm"
EXPECTED = FIXTURES / "borehole_characteristics_expected.csv"


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


def test_borehole_characteristics_matches_hex():
    got = run(str(SAMPLE), {"sheet_name": "Soil Table"}).frames["borehole_characteristics"].reset_index(drop=True)
    exp = pd.read_csv(EXPECTED)
    assert list(got.columns) == list(exp.columns)
    assert got.shape == exp.shape
    for r in range(len(exp)):
        for c in exp.columns:
            assert _cell_eq(got.iloc[r][c], exp.iloc[r][c]), \
                f"[{got.iloc[r]['Location']}][{c!r}]: {got.iloc[r][c]!r} != {exp.iloc[r][c]!r}"
