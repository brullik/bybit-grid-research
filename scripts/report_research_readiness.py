from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl


def _read(path: str) -> pl.DataFrame:
    return pl.read_parquet(path) if Path(path).exists() else pl.DataFrame()


def compute_metrics(eligible: pl.DataFrame, manifest: pl.DataFrame, quality: pl.DataFrame) -> dict[str, object]:
    manifest_symbols = set(manifest["symbol"].to_list()) if (not manifest.is_empty() and "symbol" in manifest.columns) else set()
    manifest_count = len(manifest_symbols)

    def ok_symbols(dataset: str) -> set[str]:
        if quality.is_empty():
            return set()
        q = quality.filter((pl.col("dataset") == dataset) & (pl.col("rows") > 0))
        if dataset in {"klines", "mark_klines"}:
            q = q.filter((pl.col("duplicate_candles") == 0) & (pl.col("bad_ohlc") == 0))
        return set(q["symbol"].to_list())

    normal_ok = ok_symbols("klines")
    mark_ok = ok_symbols("mark_klines")
    funding_ok = ok_symbols("funding")
    downloaded = len((normal_ok | mark_ok | funding_ok) & manifest_symbols) if manifest_symbols else 0
    ready_symbols = normal_ok & mark_ok & manifest_symbols

    gap = int(quality["missing_gaps"].sum()) if (not quality.is_empty() and "missing_gaps" in quality.columns) else 0
    dup = int(quality["duplicate_candles"].sum()) if (not quality.is_empty() and "duplicate_candles" in quality.columns) else 0
    bad = int(quality["bad_ohlc"].sum()) if (not quality.is_empty() and "bad_ohlc" in quality.columns) else 0
    zero = int(quality["zero_volume_rows"].sum()) if (not quality.is_empty() and "zero_volume_rows" in quality.columns) else 0
    disk_gb = float(quality["disk_bytes"].sum() / 1_000_000_000) if (not quality.is_empty() and "disk_bytes" in quality.columns) else 0.0
    symbols_excluded = max(0, manifest_count - len(ready_symbols))
    def rate(symbols: set[str]) -> float:
        return round(len(symbols & manifest_symbols) / max(1, manifest_count) * 100, 3)
    metrics: dict[str, object] = {
        "eligible_symbols_count": eligible.height,
        "manifest_symbols_count": manifest_count,
        "downloaded_symbols_count": downloaded,
        "normal_kline_success_rate": rate(normal_ok),
        "mark_kline_success_rate": rate(mark_ok),
        "funding_success_rate": rate(funding_ok),
        "gap_count_total": gap,
        "duplicate_count_total": dup,
        "bad_ohlc_count_total": bad,
        "zero_volume_rows_total": zero,
        "disk_usage_gb": round(disk_gb, 6),
        "symbols_ready_for_sprint_03": len(ready_symbols),
        "symbols_excluded_quality": symbols_excluded,
    }
    passed = (manifest_count >= 50 and metrics["normal_kline_success_rate"] >= 98 and metrics["mark_kline_success_rate"] >= 95 and dup == 0 and bad == 0 and len(ready_symbols) >= 50)
    metrics["recommendation"] = "pass" if passed else "fail"
    metrics["failed_symbols"] = ",".join(sorted(manifest_symbols - ready_symbols)[:50])
    metrics["missing_klines"] = ",".join(sorted(manifest_symbols - normal_ok)[:50])
    metrics["missing_mark_klines"] = ",".join(sorted(manifest_symbols - mark_ok)[:50])
    return metrics


def main() -> None:
    eligible = _read("data/processed/research_eligible_universe.parquet")
    quality = _read("data/processed/universe_quality_summary.parquet")
    manifest = _read("data/processed/research_download_manifest.parquet")
    metrics = compute_metrics(eligible, manifest, quality)
    Path("reports").mkdir(exist_ok=True)
    lines = ["# Sprint 02 Research Readiness Report", "", "Fast local rerun path:", "", "```powershell", "python scripts/report_universe_quality.py --manifest data/processed/research_download_manifest.parquet --fast", "python scripts/report_research_readiness.py", "```", ""] + [f"- {k}: {v}" for k, v in metrics.items()]
    Path("reports/sprint_02_research_readiness_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(" ".join(f"{k}={v}" for k, v in metrics.items()))

if __name__ == "__main__":
    main()
