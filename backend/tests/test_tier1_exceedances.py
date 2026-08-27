"""Regression test: the Tier 1 exceedances table matches the reference export
for the sample Soil Analytical File.

Every ``(sample_id, z, exceedance_parameter, exceedance_value)`` row must match
as a unit, so an exceedance attributed to the wrong sample/depth fails the test.
"""
from collections import Counter
from pathlib import Path

import pandas as pd

from app.pipeline import run

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample_soil_table.xlsm"
EXPECTED = FIXTURES / "tier1_exceedances_expected.csv"


def _rows(df):
    """Multiset of (sample_id, z, exceedance_parameter, exceedance_value) rows,
    floats rounded to absorb representation noise."""
    return Counter(
        (str(s), round(float(z), 3), str(p), round(float(v), 3))
        for s, z, p, v in zip(
            df["sample_id"], df["z"], df["exceedance_parameter"], df["exceedance_value"]
        )
    )


def test_tier1_exceedances_match():
    got = run(str(SAMPLE), {"sheet_name": "Soil Table"}).frames["tier1_exceedances_df"]
    exp = pd.read_csv(EXPECTED)
    assert _rows(got) == _rows(exp)
