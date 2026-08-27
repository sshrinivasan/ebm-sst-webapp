"""Dev CLI: run the pipeline without the frontend.

Takes an Excel workbook path and runs the pipeline silently. Prints nothing
unless you ask for it (--list / --frame / --repl); insert prints in your own
code as needed.

Examples:
    python dev.py table.xlsm                       # run, print nothing
    python dev.py table.xlsm --list                # list all frames + shapes
    python dev.py table.xlsm --frame soil_data_filtered
    python dev.py table.xlsm --frame ec_sar_category_report_df --rows 20
    python dev.py table.xlsm --sheet "Soil Table"
    python dev.py table.xlsm --repl                # shell with `c` bound

Any --param key=value pairs pass through to ctx.params (JSON-parsed when
possible, else kept as strings):
    python dev.py table.xlsm --param sst_flag=false --param input_water_table_depth=2.0
"""
from __future__ import annotations

import argparse
import json
import warnings

import pandas as pd

from app.pipeline import run


def _parse_param(kv: str):
    key, _, raw = kv.partition("=")
    try:
        return key, json.loads(raw)
    except json.JSONDecodeError:
        return key, raw


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the SST pipeline from the CLI.")
    ap.add_argument("file", help="path to the .xlsm workbook")
    ap.add_argument("--sheet", default="Soil Table", help="sheet name")
    ap.add_argument("--list", action="store_true", help="list all frames + shapes")
    ap.add_argument("--frame", help="print this frame (head + shape)")
    ap.add_argument("--rows", type=int, default=10, help="rows to show with --frame")
    ap.add_argument("--param", action="append", default=[], help="key=value passed to ctx.params")
    ap.add_argument("--repl", action="store_true", help="drop into a shell with `c` bound")
    args = ap.parse_args()

    params = {"sheet_name": args.sheet, **dict(_parse_param(kv) for kv in args.param)}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        c = run(args.file, params)

    if args.list:
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 200)
        for name, df in c.frames.items():
            print(f"  {name:40s} {getattr(df, 'shape', None)}")
        print(f"\nctx.options keys: {list(c.options)}")
        print(f"ctx.exports keys: {list(c.exports)}")
        print(f"ctx.outputs keys: {list(c.outputs)}")

    if args.frame:
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 200)
        df = c.frames[args.frame]
        print(f"{args.frame}: shape={df.shape}")
        print(f"columns: {list(df.columns)}\n")
        print(df.head(args.rows).to_string())

    if args.repl:
        import code
        code.interact(local={"c": c, "pd": pd}, banner="\n`c` = Context, `pd` = pandas. Ctrl-D to exit.")


if __name__ == "__main__":
    main()
