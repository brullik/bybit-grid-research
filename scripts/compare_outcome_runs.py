from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl
from bybit_grid.research.outcome_core.outcome_numpy import outcome_match_key
from bybit_grid.research.outcome_store import read_outcomes

INVARIANTS = [
    "range_action_event_id", "future_horizon_minutes", "sl_atr_buffer", "entry_time_ms", "future_rows_available",
    "future_data_complete_bool", "first_exit_side", "first_exit_time_ms", "first_exit_ambiguous_bool",
    "inside_range_candle_count", "inside_range_ratio", "atr_14_abs_used", "lower_sl_price", "upper_sl_price",
    "first_sl_side", "first_sl_time_ms", "first_sl_ambiguous_bool", "funding_rows_in_horizon", "funding_rate_sum", "funding_source_status",
]


def ensure_key(df: pl.DataFrame) -> pl.DataFrame:
    if "outcome_match_key" in df.columns:
        return df
    return df.with_columns(
        pl.struct(["range_action_event_id", "future_horizon_minutes", "grid_count", "sl_atr_buffer"]).map_elements(
            lambda r: outcome_match_key(str(r["range_action_event_id"]), int(r["future_horizon_minutes"]), int(r["grid_count"]), float(r["sl_atr_buffer"])),
            return_dtype=pl.String,
        ).alias("outcome_match_key")
    )


def eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=1e-8, abs_tol=1e-8)
    return a == b


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--expect-change", choices=["grid_only"], default="grid_only")
    args = ap.parse_args()
    base = ensure_key(read_outcomes(Path("data/processed/outcome_runs") / args.baseline))
    cand = ensure_key(read_outcomes(Path("data/processed/outcome_runs") / args.candidate))
    if base.is_empty() or cand.is_empty():
        raise SystemExit("baseline or candidate has no rows")
    joined = base.join(cand, on="outcome_match_key", how="inner", suffix="_candidate")
    failures = []
    if joined.height != min(base.height, cand.height):
        failures.append(f"joined_rows={joined.height} baseline_rows={base.height} candidate_rows={cand.height}")
    for field in INVARIANTS:
        if field not in joined.columns or f"{field}_candidate" not in joined.columns:
            continue
        for r in joined.select([field, f"{field}_candidate"]).iter_rows():
            if not eq(r[0], r[1]):
                failures.append(f"invariant changed: {field}")
                break
    result = {"comparison_ok": not failures, "baseline": args.baseline, "candidate": args.candidate, "rows_compared": joined.height, "failures": failures}
    print(json.dumps(result, separators=(",", ":")))
    raise SystemExit(0 if not failures else 1)


if __name__ == "__main__":
    main()
