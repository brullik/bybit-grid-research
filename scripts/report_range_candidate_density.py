from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl

from bybit_grid.research.range_candidate_summary import read_candidates


def _safe_read(path: Path) -> pl.DataFrame:
    return read_candidates(path)


def main() -> None:
    raw = _safe_read(Path("data/processed/range_raw_candidates"))
    event = _safe_read(Path("data/processed/range_event_candidates"))
    rows = []
    profiles = sorted(set((raw["profile_name"].to_list() if "profile_name" in raw.columns else []) + (event["profile_name"].to_list() if "profile_name" in event.columns else [])))
    for profile in profiles:
        r = raw.filter(pl.col("profile_name") == profile) if not raw.is_empty() and "profile_name" in raw.columns else pl.DataFrame()
        e = event.filter(pl.col("profile_name") == profile) if not event.is_empty() and "profile_name" in event.columns else pl.DataFrame()
        raw_total, event_total = r.height, e.height
        compression = raw_total / event_total if event_total else 0.0
        if not e.is_empty():
            per = e.with_columns((pl.col("signal_time_ms") // 86_400_000).alias("day")).group_by(["symbol", "day"]).len()["len"]
            avg, p50, p90, p99 = float(per.mean()), float(per.quantile(0.5)), float(per.quantile(0.9)), float(per.quantile(0.99))
        else:
            avg = p50 = p90 = p99 = 0.0
        rows.append({
            "profile_name": profile,
            "raw_candidates_total": raw_total,
            "event_candidates_total": event_total,
            "raw_to_event_compression_ratio": compression,
            "candidates_per_10k_candles_raw": 0.0,
            "candidates_per_10k_candles_event": 0.0,
            "event_candidates_per_symbol_day_avg": avg,
            "event_candidates_per_symbol_day_p50": p50,
            "event_candidates_per_symbol_day_p90": p90,
            "event_candidates_per_symbol_day_p99": p99,
            "symbols_with_events": e["symbol"].n_unique() if not e.is_empty() else 0,
            "windows_with_events": e["lookback_minutes"].n_unique() if not e.is_empty() else 0,
            "gap_affected_raw_candidates": int(r["missing_candles_in_window"].sum()) if not r.is_empty() and "missing_candles_in_window" in r.columns else 0,
            "gap_affected_event_candidates": int(e["missing_candles_in_window"].sum()) if not e.is_empty() and "missing_candles_in_window" in e.columns else 0,
            "zero_volume_affected_candidates": int(r["zero_volume_candles_in_window"].sum()) if not r.is_empty() and "zero_volume_candles_in_window" in r.columns else 0,
        })
    out = pl.DataFrame(rows) if rows else pl.DataFrame()
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    out.write_parquet("data/processed/range_candidate_density_summary.parquet")
    Path("reports").mkdir(exist_ok=True)
    lines = ["# Sprint 03.1 Range Event Calibration Report", ""]
    for row in rows:
        lines += [f"## {row['profile_name']}"] + [f"- {k}: {v}" for k, v in row.items() if k != "profile_name"]
        if row["profile_name"] == "balanced_research":
            ok = row["raw_to_event_compression_ratio"] >= 10 and row["event_candidates_per_symbol_day_p99"] <= 200 and 0.2 <= row["event_candidates_per_symbol_day_p50"] <= 50
            lines.append(f"- acceptance_density_status: {'pass' if ok else 'fail_too_loose_or_tight'}")
        lines.append("")
    Path("reports/sprint_03_1_range_event_calibration_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(" ".join(f"{r['profile_name']}_raw={r['raw_candidates_total']} {r['profile_name']}_event={r['event_candidates_total']}" for r in rows))


if __name__ == "__main__":
    main()
