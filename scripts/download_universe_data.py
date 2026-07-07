from __future__ import annotations

import argparse
import time

import polars as pl

from bybit_grid.bybit.client import BybitClient
from bybit_grid.config import load_settings
from bybit_grid.data.funding import download_funding_history
from bybit_grid.data.klines import download_kline_range
from bybit_grid.data.mark_klines import download_mark_kline_range


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/processed/download_manifest.parquet")
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    manifest = pl.read_parquet(args.manifest)
    print(manifest)
    if args.dry_run:
        return
    with BybitClient(load_settings()) as client:
        for row in manifest.to_dicts():
            for downloader in (
                download_kline_range,
                download_mark_kline_range,
                download_funding_history,
            ):
                for attempt in range(3):
                    try:
                        downloader(client, row["symbol"], int(row["start_ms"]), int(row["end_ms"]))
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(2**attempt)
                time.sleep(args.sleep_sec)


if __name__ == "__main__":
    main()
