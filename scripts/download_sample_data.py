import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import argparse
import time

import polars as pl

from bybit_grid.bybit.client import BybitClient
from bybit_grid.config import load_settings
from bybit_grid.data.funding import download_funding_history
from bybit_grid.data.klines import download_kline_range
from bybit_grid.data.mark_klines import download_mark_kline_range
from bybit_grid.data.quality import build_quality_report, save_gap_report
from bybit_grid.logging import setup_logging
from bybit_grid.reporting import write_sprint_report

ONE_MINUTE_MS = 60_000


def sample_time_bounds(days: int, now_ms: int | None = None) -> tuple[int, int]:
    now = int(time.time() * 1000) if now_ms is None else now_ms
    end = (now // ONE_MINUTE_MS) * ONE_MINUTE_MS - ONE_MINUTE_MS
    start = end - days * 24 * 60 * ONE_MINUTE_MS + ONE_MINUTE_MS
    return start, end


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()
    settings = load_settings()
    setup_logging(settings.log_level)
    start, end = sample_time_bounds(args.days)
    all_k = []
    kline_rows = 0
    mark_kline_rows = 0
    funding_rows = 0
    with BybitClient(settings) as c:
        for s in args.symbols:
            k = download_kline_range(c, s, start, end)
            m = download_mark_kline_range(c, s, start, end)
            f = download_funding_history(c, s, start, end)
            kline_rows += k.height
            mark_kline_rows += m.height
            funding_rows += f.height
            if not k.is_empty():
                all_k.append(k)
    kline_df = pl.concat(all_k) if all_k else pl.DataFrame()
    gaps = save_gap_report(settings.data_dir, kline_df, start, end)
    quality = build_quality_report(kline_df, start, end)
    output_paths = [
        str(settings.data_dir / "raw" / "klines"),
        str(settings.data_dir / "raw" / "mark_klines"),
        str(settings.data_dir / "raw" / "funding"),
        str(settings.data_dir / "quality"),
    ]
    write_sprint_report(
        settings.data_dir,
        {
            "command": "python scripts/download_sample_data.py",
            "env": settings.bybit_env,
            "symbols": args.symbols,
            "requested_days": args.days,
            "counts": {
                "kline_rows": kline_rows,
                "mark_kline_rows": mark_kline_rows,
                "funding_rows": funding_rows,
                "gap_count": quality["gap_count"],
                "duplicate_count": quality["duplicate_count"],
                "bad_ohlc_count": quality["bad_ohlc_count"],
            },
            "kline_rows": kline_rows,
            "mark_kline_rows": mark_kline_rows,
            "funding_rows": funding_rows,
            "gap_count": quality["gap_count"],
            "duplicate_count": quality["duplicate_count"],
            "bad_ohlc_count": quality["bad_ohlc_count"],
            "gap summary": gaps.to_dicts(),
            "output_paths": output_paths,
            "blockers": "none for public data",
        },
    )
    print(
        f"ok symbols={args.symbols} kline_rows={kline_rows} mark_kline_rows={mark_kline_rows} "
        f"funding_rows={funding_rows} gaps={gaps.height} duplicates={quality['duplicate_count']} "
        f"bad_ohlc={quality['bad_ohlc_count']}"
    )


if __name__ == "__main__":
    main()
