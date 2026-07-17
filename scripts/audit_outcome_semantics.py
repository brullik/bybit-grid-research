from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl
from bybit_grid.research.outcome_store import read_outcomes
from bybit_grid.research.outcome_core.grid_crossings import GRID_LEVELS_SERIALIZATION_VERSION
from bybit_grid.research.outcome_semantics import (
    OUTCOME_SEMANTICS_VERSION,
    OUTCOME_WINDOW_SEMANTICS_VERSION,
    fail,
    validate_outcome_window_semantics,
)

GRID_GEOMETRY_SEMANTICS_VERSION = "v1_n_cells_n_plus_1_levels"
OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT = (
    "outcome-window-completeness-provenance-v1"
)




def write_artifacts(run_id: str, result: dict) -> None:
    summary_dir = Path("data/processed/outcome_runs") / run_id / "summary"
    report_dir = Path("reports/outcome_runs") / run_id
    summary_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "outcome_semantic_audit.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    lines = ["# Outcome Semantic Audit", "", f"- outcome_run_id: `{run_id}`", f"- semantic_audit_ok: `{result['semantic_audit_ok']}`", f"- rows_checked: `{result['rows_checked']}`", "", "## Failures"]
    lines += [f"- {x}" for x in result["failures"]] or ["- none"]
    (report_dir / "outcome_semantic_audit.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome-run-id", required=True)
    args = ap.parse_args()
    root = Path("data/processed/outcome_runs") / args.outcome_run_id
    df = read_outcomes(root)
    failures: list[str] = []
    checks: dict[str, object] = {}
    if df.is_empty():
        fail(failures, "no outcome rows")
    cols = set(df.columns)
    required = {
        "outcome_id", "outcome_match_key", "outcome_semantics_version", "grid_geometry_semantics_version",
        "range_action_event_id", "future_horizon_minutes", "grid_count", "grid_cell_number",
        "grid_price_level_count", "grid_interval_count", "grid_interval_ratio", "grid_interval_pct",
        "grid_interval_bps", "grid_count_semantics", "sl_atr_buffer", "atr_14_abs_used",
        "sl_proxy_valid_bool", "first_exit_side", "first_exit_ambiguous_bool", "first_sl_side",
        "first_sl_ambiguous_bool", "geometric_grid_levels_json", "range_low", "range_high",
        "grid_levels_serialization_version",
    }
    missing = sorted(required - cols)
    if missing:
        fail(failures, "missing columns: " + ",".join(missing))
    if not failures:
        checks["outcome_semantics_version"] = df["outcome_semantics_version"].unique().to_list()
        if set(checks["outcome_semantics_version"]) != {OUTCOME_SEMANTICS_VERSION}:
            fail(failures, "outcome_semantics_version is not v5_exact_outcome_window_provenance")
        window_audit = validate_outcome_window_semantics(df)
        checks["outcome_window_semantic_audit_ok"] = window_audit[
            "outcome_window_semantic_audit_ok"
        ]
        for window_failure in window_audit["failures"]:
            fail(failures, str(window_failure))
        if set(df["grid_geometry_semantics_version"].unique().to_list()) != {GRID_GEOMETRY_SEMANTICS_VERSION}:
            fail(failures, "grid_geometry_semantics_version invalid")
        dup_composite = df.height - df.select(["range_action_event_id", "future_horizon_minutes", "grid_count", "sl_atr_buffer"]).unique().height
        checks["duplicate_composite_rows"] = dup_composite
        if df["outcome_id"].n_unique() != df.height:
            fail(failures, "outcome_id is not unique")
        if dup_composite != 0:
            fail(failures, f"composite duplicates={dup_composite}")
        bad_counts = df.filter((pl.col("grid_price_level_count") != pl.col("grid_cell_number") + 1) | (pl.col("grid_interval_count") != pl.col("grid_cell_number")) | (pl.col("grid_count") != pl.col("grid_cell_number"))).height
        checks["grid_count_rows_failed"] = bad_counts
        if bad_counts:
            fail(failures, "grid count/level semantics invalid")
        if set(df["grid_levels_serialization_version"].unique().to_list()) != {GRID_LEVELS_SERIALIZATION_VERSION}:
            fail(failures, "grid_levels_serialization_version invalid")
        geometry_failure = None
        for r in df.select([c for c in ["symbol", "outcome_id", "geometric_grid_levels_json", "grid_cell_number", "range_low", "range_high", "grid_interval_ratio", "grid_interval_pct", "grid_interval_bps"] if c in cols]).iter_rows(named=True):
            levels = [float(x) for x in json.loads(r["geometric_grid_levels_json"])]
            n = int(r["grid_cell_number"])
            low = float(r["range_low"])
            high = float(r["range_high"])
            ratio = (high / low) ** (1.0 / n)
            base_detail = {"symbol": r.get("symbol"), "outcome_id": r.get("outcome_id"), "range_low": low, "range_high": high, "grid_cell_number": n, "expected_ratio": ratio}
            if len(levels) != n + 1 or not math.isclose(levels[0], low, rel_tol=0.0, abs_tol=max(1e-15, abs(low) * 1e-14)) or not math.isclose(levels[-1], high, rel_tol=0.0, abs_tol=max(1e-15, abs(high) * 1e-14)):
                geometry_failure = base_detail | {"reason": "grid levels length/endpoints invalid"}
                fail(failures, "grid levels length/endpoints invalid")
                break
            if any(not math.isfinite(x) or x <= 0 for x in levels) or any(levels[i + 1] <= levels[i] for i in range(n)):
                geometry_failure = base_detail | {"reason": "grid levels not strictly monotonic"}
                fail(failures, "grid levels not strictly monotonic")
                break
            expected_log_ratio = math.log(high / low) / n
            actual_log_ratios = [math.log(levels[i + 1] / levels[i]) for i in range(n)]
            log_errors = [abs(x - expected_log_ratio) for x in actual_log_ratios]
            max_abs_error = max(log_errors) if log_errors else 0.0
            max_rel_error = max_abs_error / abs(expected_log_ratio) if expected_log_ratio else max_abs_error
            if max_abs_error > 1e-12 and max_rel_error > 1e-10:
                geometry_failure = base_detail | {"reason": "adjacent grid ratio is not constant", "max_adjacent_ratio_abs_error": max_abs_error, "max_adjacent_ratio_rel_error": max_rel_error}
                fail(failures, "adjacent grid ratio is not constant")
                break
            pct = (ratio - 1.0) * 100.0
            if not (math.isclose(float(r["grid_interval_ratio"]), ratio, rel_tol=1e-10) and math.isclose(float(r["grid_interval_pct"]), pct, rel_tol=1e-10) and math.isclose(float(r["grid_interval_bps"]), pct * 100, rel_tol=1e-10)):
                geometry_failure = base_detail | {"reason": "stored interval ratio/pct/bps mismatch"}
                fail(failures, "stored interval ratio/pct/bps mismatch")
                break
        if geometry_failure:
            checks["first_geometry_failure"] = geometry_failure
        valid = df.filter(pl.col("sl_proxy_valid_bool"))
        bad_atr = valid.filter((~pl.col("atr_14_abs_used").is_finite()) | (pl.col("atr_14_abs_used") <= 0)).height
        if bad_atr:
            fail(failures, "finite/nonpositive ATR accepted")
        nonzero = valid.filter(pl.col("sl_atr_buffer") > 0)
        for r in nonzero.select(["sl_atr_buffer", "atr_14_abs_used", "sl_distance_lower_abs", "sl_distance_upper_abs", "lower_sl_price", "upper_sl_price", "range_low", "range_high"]).iter_rows(named=True):
            exp = float(r["sl_atr_buffer"]) * float(r["atr_14_abs_used"])
            if not (math.isclose(float(r["sl_distance_lower_abs"]), exp, rel_tol=1e-8, abs_tol=1e-8) and math.isclose(float(r["sl_distance_upper_abs"]), exp, rel_tol=1e-8, abs_tol=1e-8)):
                fail(failures, "SL distance is not buffer*ATR")
                break
            if not (float(r["upper_sl_price"]) > float(r["range_high"]) and float(r["lower_sl_price"]) < float(r["range_low"])):
                fail(failures, "SL boundary direction invalid")
                break
        if df.filter((pl.col("first_exit_side") == "ambiguous_both") != pl.col("first_exit_ambiguous_bool")).height or df.filter((pl.col("first_sl_side") == "ambiguous_both") != pl.col("first_sl_ambiguous_bool")).height:
            fail(failures, "ambiguity fields inconsistent")
        for c in ["future_close_level_cross_count", "future_intrabar_level_touch_count", "future_unique_grid_levels_touched_count", "fill_activity_lower_bound_proxy", "fill_activity_upper_bound_proxy"]:
            if c not in cols:
                fail(failures, f"missing activity proxy {c}")

        invariant_checks = [
            (("future_coverage_minutes", "future_horizon_minutes"), pl.col("future_coverage_minutes") <= pl.col("future_horizon_minutes"), "future_coverage_minutes > horizon"),
            (("inside_range_candle_count", "future_rows_available"), pl.col("inside_range_candle_count") <= pl.col("future_rows_available"), "inside_range_candle_count > future_rows_available"),
            (("future_bad_ohlc_count", "future_rows_available"), pl.col("future_bad_ohlc_count") <= pl.col("future_rows_available"), "future_bad_ohlc_count > future_rows_available"),
            (("future_zero_volume_count", "future_rows_available"), pl.col("future_zero_volume_count") <= pl.col("future_rows_available"), "future_zero_volume_count > future_rows_available"),
        ]
        for needed_cols, expr, msg in invariant_checks:
            if all(c in cols for c in needed_cols) and df.filter(~expr).height:
                fail(failures, msg)
        hygiene_path = root / "summary" / "outcome_input_hygiene.json"
        if not hygiene_path.exists():
            fail(failures, "missing outcome_input_hygiene.json")
        else:
            hygiene = json.loads(hygiene_path.read_text())
            checks["input_hygiene_ok"] = hygiene.get("input_hygiene_ok")
            checks["funding_duplicate_timestamps_removed"] = hygiene.get("funding_duplicate_timestamps_removed")
            if hygiene.get("input_hygiene_ok") is not True:
                fail(failures, "input_hygiene_ok is not true")
            if hygiene.get("kline_duplicate_timestamps_removed", 0) and not hygiene.get("input_hygiene_ok"):
                fail(failures, "duplicated candle timestamps detected")

        if "grid_step_fee_multiple_proxy" in cols and df.filter(pl.col("grid_step_fee_multiple_proxy").is_not_null()).height:
            fail(failures, "hardcoded fee proxy remains populated")
    result = {"semantic_audit_ok": not failures, "outcome_run_id": args.outcome_run_id, "outcome_semantics_version": OUTCOME_SEMANTICS_VERSION, "outcome_window_semantics_version": OUTCOME_WINDOW_SEMANTICS_VERSION, "rows_checked": df.height, "failures": failures, "checks": checks}
    write_artifacts(args.outcome_run_id, result)
    print(json.dumps(result, separators=(",", ":")))
    raise SystemExit(0 if not failures else 1)


if __name__ == "__main__":
    main()
