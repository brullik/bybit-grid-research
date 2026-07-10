from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl
from bybit_grid.research.outcome_store import read_outcomes


def fail(msgs, msg):
    msgs.append(msg)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome-run-id", required=True)
    args = ap.parse_args()
    root = Path("data/processed/outcome_runs") / args.outcome_run_id
    df = read_outcomes(root)
    failures: list[str] = []
    if df.is_empty():
        fail(failures, "no outcome rows")
    cols = set(df.columns)
    required = {"outcome_id","range_action_event_id","future_horizon_minutes","grid_count","sl_atr_buffer","atr_14_abs_used","sl_proxy_valid_bool","first_exit_side","first_exit_ambiguous_bool","first_sl_side","first_sl_ambiguous_bool"}
    missing = sorted(required - cols)
    if missing:
        fail(failures, "missing columns: " + ",".join(missing))
    if not failures:
        dup_composite = df.height - df.select(["range_action_event_id","future_horizon_minutes","grid_count","sl_atr_buffer"]).unique().height
        if df["outcome_id"].n_unique() != df.height:
            fail(failures, "outcome_id is not unique")
        if dup_composite != 0:
            fail(failures, f"composite duplicates={dup_composite}")
        valid = df.filter(pl.col("sl_proxy_valid_bool"))
        nonzero = valid.filter(pl.col("sl_atr_buffer") > 0)
        for r in nonzero.select(["sl_atr_buffer","atr_14_abs_used","sl_distance_lower_abs","sl_distance_upper_abs","lower_sl_price","upper_sl_price","range_low","range_high"]).iter_rows(named=True):
            exp = float(r["sl_atr_buffer"]) * float(r["atr_14_abs_used"])
            if not (math.isclose(float(r["sl_distance_lower_abs"]), exp, rel_tol=1e-8, abs_tol=1e-8) and math.isclose(float(r["sl_distance_upper_abs"]), exp, rel_tol=1e-8, abs_tol=1e-8)):
                fail(failures, "SL distance is not buffer*ATR")
                break
            if not (float(r["upper_sl_price"]) > float(r["range_high"]) and float(r["lower_sl_price"]) < float(r["range_low"])):
                fail(failures, "SL boundary direction invalid")
                break
        bad_atr = valid.filter((~pl.col("atr_14_abs_used").is_finite()) | (pl.col("atr_14_abs_used") <= 0)).height
        if bad_atr:
            fail(failures, "finite/nonpositive ATR accepted")
        bad_exit = df.filter((pl.col("first_exit_side") == "ambiguous_both") != pl.col("first_exit_ambiguous_bool")).height
        bad_sl = df.filter((pl.col("first_sl_side") == "ambiguous_both") != pl.col("first_sl_ambiguous_bool")).height
        if bad_exit or bad_sl:
            fail(failures, "ambiguity fields inconsistent")
        for c in ["future_close_level_cross_count","future_intrabar_level_touch_count","future_unique_grid_levels_touched_count","fill_activity_lower_bound_proxy","fill_activity_upper_bound_proxy"]:
            if c not in cols:
                fail(failures, f"missing activity proxy {c}")
        if "grid_step_fee_multiple_proxy" in cols and df.filter(pl.col("grid_step_fee_multiple_proxy").is_not_null()).height:
            fail(failures, "hardcoded fee proxy remains populated")
    result = {"ok": not failures, "outcome_run_id": args.outcome_run_id, "rows": df.height, "failures": failures}
    print(json.dumps(result, separators=(",", ":")))
    raise SystemExit(0 if not failures else 1)

if __name__ == "__main__":
    main()
