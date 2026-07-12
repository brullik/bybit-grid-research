from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.backtest.ohlc_replay.evidence import build_zip
from bybit_grid.backtest.ohlc_replay.scenarios import DEFAULT_PACK, RUN_ID


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=RUN_ID)
    p.add_argument("--output-root", default="data/processed/ohlc_replay_runs")
    p.add_argument("--report-root", default="reports/ohlc_replay_runs")
    p.add_argument("--output")
    p.add_argument("--pack-path", dest="pack_path")
    a = p.parse_args(argv)
    dest = Path(a.output or a.pack_path or DEFAULT_PACK)
    try:
        build_zip(Path(a.output_root) / a.run_id, Path(a.report_root) / a.run_id, dest, a.run_id)
        print(
            json.dumps(
                {"review_pack_ok": True, "zip": str(dest)}, sort_keys=True, separators=(",", ":")
            )
        )
        return 0
    except Exception as e:
        print(
            json.dumps(
                {"review_pack_ok": False, "error_type": type(e).__name__, "error_message": str(e)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
