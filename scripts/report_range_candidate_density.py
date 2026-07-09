from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl

from bybit_grid.research.range_candidate_summary import read_candidates


def resolve_run(run_id: str) -> str:
    if run_id == "latest":
        p = Path("data/processed/range_runs/latest_run.txt")
        if not p.exists():
            raise SystemExit("latest range run pointer not found")
        return p.read_text(encoding="utf-8").strip()
    return run_id


def per_day_stats(df: pl.DataFrame) -> tuple[float, float, float, float]:
    if df.is_empty():
        return 0.0, 0.0, 0.0, 0.0
    per = df.with_columns((pl.col("signal_time_ms") // 86_400_000).alias("day")).group_by(["symbol", "day"]).len()["len"]
    return float(per.mean()), float(per.quantile(0.5)), float(per.quantile(0.9)), float(per.quantile(0.99))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="latest")
    args = ap.parse_args()
    run_id = resolve_run(args.run_id)
    root = Path("data/processed/range_runs") / run_id
    raw = read_candidates(root / "raw_candidates")
    event = read_candidates(root / "event_candidates")
    actionable = read_candidates(root / "actionable_events")
    avg, p50, p90, p99 = per_day_stats(actionable)
    perf_path = root / "summary" / "range_candidate_perf.json"
    perf = json.loads(perf_path.read_text(encoding="utf-8")) if perf_path.exists() else {}
    raw_total = raw.height if raw.height else int(perf.get("raw_candidate_rows_written") or 0)
    event_total = event.height if event.height else int(perf.get("event_candidate_rows_written") or 0)
    action_total = actionable.height if actionable.height else int(perf.get("actionable_event_rows_written") or 0)
    compression = (raw_total / action_total) if action_total else None
    row = {
        "run_id": run_id,
        "raw_candidates_total": raw_total,
        "event_candidates_total": event_total,
        "actionable_events_total": action_total,
        "raw_to_event_compression_ratio": raw_total / event_total if event_total else 0.0,
        "raw_to_actionable_compression_ratio": compression,
        "actionable_events_per_symbol_day_avg": avg,
        "actionable_events_per_symbol_day_p50": p50,
        "actionable_events_per_symbol_day_p90": p90,
        "actionable_events_per_symbol_day_p99": p99,
        "symbols_with_actionable_events": actionable["symbol"].n_unique() if not actionable.is_empty() else 0,
        "lookbacks_with_actionable_events": actionable["best_lookback_minutes"].n_unique() if not actionable.is_empty() and "best_lookback_minutes" in actionable.columns else 0,
        "duplicate_action_event_id_count": action_total - actionable["range_action_event_id"].n_unique() if not actionable.is_empty() and "range_action_event_id" in actionable.columns else 0,
        "acceptance_density_status": "pass" if action_total > 0 and compression is not None and compression >= 10 and p50 <= 50 and p90 <= 100 and p99 <= 200 else "fail",
    }
    out = pl.DataFrame([row])
    (root / "summary").mkdir(parents=True, exist_ok=True)
    out.write_parquet(root / "summary" / "range_density_summary.parquet")
    report_dir = Path("reports/range_runs") / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "range_candidate_density_report.md").write_text("# Sprint 03.2 Range Density Report\n\n" + "\n".join(f"- {k}: {v}" for k, v in row.items()) + "\n\n## Recommendation\n- Proceed only if acceptance_density_status is pass.\n", encoding="utf-8")
    print(" ".join(f"{k}={v}" for k, v in row.items()))


if __name__ == "__main__":
    main()
