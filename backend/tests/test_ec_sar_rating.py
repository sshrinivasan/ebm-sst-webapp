"""Regression test: the EC/SAR rating report matches the Hex reference output
(table_56 export) for the sample Soil Analytical File."""
from pathlib import Path

import pandas as pd
import pytest

from app.context import InputValidationError
from app.pipeline import run
from conftest import EXTENDED_TOPSOIL_DEPTHS

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample_soil_table.xlsm"
EXPECTED = FIXTURES / "ec_sar_category_report_expected.csv"

STR_COLS = ["Sample ID", "Comments", "EC Category", "SAR Category"]
NUM_COLS = ["Z", "Chloride (mg/kg)", "Chloride (mg/L)"]


def _norm_str(s: pd.Series) -> pd.Series:
    return s.map(lambda v: None if (v is None or (isinstance(v, float) and pd.isna(v))
                                    or str(v).strip() in ("", "nan", "None")) else str(v).strip())


def test_ec_sar_category_report_matches_hex():
    ctx = run(str(SAMPLE), {"sheet_name": "Soil Table", "topsoil_depths": EXTENDED_TOPSOIL_DEPTHS})
    got = ctx.frames["ec_sar_category_report_df"].reset_index(drop=True)
    exp = pd.read_csv(EXPECTED)

    assert got.shape == exp.shape
    got = got[exp.columns]

    for c in STR_COLS:
        g, e = _norm_str(got[c]), _norm_str(exp[c])
        assert ((g == e) | (g.isna() & e.isna())).all(), f"mismatch in column {c!r}"

    for c in NUM_COLS:
        g = pd.to_numeric(got[c], errors="coerce")
        e = pd.to_numeric(exp[c], errors="coerce")
        assert ((g.sub(e).abs() < 1e-6) | (g.isna() & e.isna())).all(), f"mismatch in column {c!r}"


def test_topsoil_depths_must_cover_deepest_sample():
    """A depth table that stops above the deepest sample must be rejected."""
    shallow_depths = [
        {"top": "0", "bottom": "0.3", "type": "Topsoil"},
        {"top": "0.3", "bottom": "1", "type": "Subsoil"},
        {"top": "1", "bottom": "1.5", "type": "Subsoil"},
    ]
    with pytest.raises(InputValidationError, match="deepest sample"):
        run(str(SAMPLE), {"sheet_name": "Soil Table", "topsoil_depths": shallow_depths})


def test_topsoil_depths_covering_deepest_sample_passes():
    """A depth table that extends to the deepest sample (15 m) passes."""
    ctx = run(str(SAMPLE), {"sheet_name": "Soil Table", "topsoil_depths": EXTENDED_TOPSOIL_DEPTHS})
    assert "topsoil_depths_validated" in ctx.frames
