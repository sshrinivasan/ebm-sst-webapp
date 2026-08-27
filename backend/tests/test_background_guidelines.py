"""Regression test: the SCARG background/guideline tables match the Hex
reference exports for the sample Soil Analytical File."""
from pathlib import Path

import pandas as pd
import pytest

from app.pipeline import run

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample_soil_table.xlsm"

CASES = [
    ("scarg_rating_guideline_summary_df", "scarg_rating_guideline_summary_expected.csv"),
    ("ec_report_data_display_df_hex", "ec_report_summary_expected.csv"),
    ("sar_report_data_display_df_hex", "sar_report_summary_expected.csv"),
]


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan", "None")


def _cell_eq(a, b) -> bool:
    if _blank(a) and _blank(b):
        return True
    if _blank(a) or _blank(b):
        return False
    try:
        return abs(float(a) - float(b)) < 0.005  # values are rounded to 2 dp
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


@pytest.fixture(scope="module")
def frames():
    return run(str(SAMPLE), {"sheet_name": "Soil Table"}).frames


@pytest.mark.parametrize("frame_key,fixture", CASES)
def test_scarg_table_matches_hex(frames, frame_key, fixture):
    got = frames[frame_key].reset_index(drop=True)
    exp = pd.read_csv(FIXTURES / fixture)
    assert list(got.columns) == list(exp.columns)
    assert got.shape == exp.shape
    for r in range(len(exp)):
        for c in exp.columns:
            assert _cell_eq(got.iloc[r][c], exp.iloc[r][c]), \
                f"{frame_key} [{r},{c}]: {got.iloc[r][c]!r} != {exp.iloc[r][c]!r}"
