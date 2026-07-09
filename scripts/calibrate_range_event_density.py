from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl

from bybit_grid.research.range_candidate_summary import read_candidates


def stats(df: pl.DataFrame) -> tuple[float, float, float, float]:
    if df.is_empty():
        return 0.0, 0.0, 0.0, 0.0
    per = df.with_columns((pl.col("signal_time_ms") // 86_400_000).alias("day")).group_by(["symbol", "day"]).len()["len"]
    return float(per.mean()), float(per.quantile(0.5)), float(per.quantile(0.9)), float(per.quantile(0.99))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="auto")
    ap.add_argument("--symbols-limit", type=int)
    ap.add_argument("--days-limit", type=int)
    ap.add_argument("--fast-max", action="store_true")
    ap.add_argument("--confirm-large-run", action="store_true")
    ap.add_argument("--dry-run-plan", action="store_true")
    args = ap.parse_args()
    run_id = args.run_id if args.run_id != "auto" else time.strftime("cal_%Y%m%d_%H%M%S")
    print(f"dry_run_plan run_id={run_id} symbols_limit={args.symbols_limit} days_limit={args.days_limit} variants=12")
    if args.dry_run_plan:
        return
    root = Path("data/processed/range_runs") / run_id
    (root / "summary").mkdir(parents=True, exist_ok=True)
    latest = Path("data/processed/range_runs/latest_run.txt")
    source_run = latest.read_text().strip() if latest.exists() else run_id
    source = Path("data/processed/range_runs") / source_run / "actionable_events"
    base = read_candidates(source) if source.exists() else pl.DataFrame()
    rows: list[dict[str, object]] = []
    variants = [(m, t, a, b) for m in [3, 4, 5, 6] for t in [1, 2, 3] for a in [2, 3, 4, 5] for b in [25, 50, 100]][:12]
    for idx, (mid, touch, atr, bps) in enumerate(variants, 1):
        df = base
        if not df.is_empty():
            if "midline_crosses" in df.columns:
                df = df.filter(pl.col("midline_crosses") >= mid)
            if "min_touches_lower_zone" in df.columns:
                df = df.filter((pl.col("min_touches_lower_zone") >= touch) & (pl.col("min_touches_upper_zone") >= touch))
            if "range_height_atr_14" in df.columns:
                df = df.filter(pl.col("range_height_atr_14") >= atr)
        avg, p50, p90, p99 = stats(df)
        raw_total = int(df["raw_candidates_in_regime"].sum()) if not df.is_empty() and "raw_candidates_in_regime" in df.columns else df.height
        ratio = raw_total / df.height if df.height else 0.0
        rows.append(
            {
                "profile_variant": f"v{idx}_mid{mid}_touch{touch}_atr{atr}_bps{bps}",
                "raw_candidates_total": raw_total,
                "actionable_events_total": df.height,
                "raw_to_actionable_compression_ratio": ratio,
                "actionable_events_per_symbol_day_avg": avg,
                "actionable_events_per_symbol_day_p50": p50,
                "actionable_events_per_symbol_day_p90": p90,
                "actionable_events_per_symbol_day_p99": p99,
                "symbols_with_actionable_events": df["symbol"].n_unique() if not df.is_empty() else 0,
                "lookbacks_with_actionable_events": df["best_lookback_minutes"].n_unique() if not df.is_empty() and "best_lookback_minutes" in df.columns else 0,
                "pass_density_gate": bool(df.height > 0 and ratio >= 10 and 1 <= p50 <= 50 and p90 <= 100 and p99 <= 200),
            }
        )
    out = pl.DataFrame(rows)
    out.write_parquet(root / "summary" / "range_density_calibration.parquet")
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(run_id)
    Path("reports").mkdir(exist_ok=True)
    lines = ["# Sprint 03.2 Density Calibration", ""]
    for row in rows[:5]:
        lines += [f"## {row['profile_variant']}"] + [f"- {k}: {v}" for k, v in row.items() if k != "profile_variant"] + [""]
    Path(f"reports/sprint_03_2_density_calibration_{run_id}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"run_id={run_id} variants={len(rows)} output={root / 'summary' / 'range_density_calibration.parquet'}")


if __name__ == "__main__":
    main()
