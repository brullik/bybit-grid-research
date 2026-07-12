from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.backtest.neutral_grid.serialization import canonical_json_bytes
from bybit_grid.backtest.ohlc_replay.evidence import write_run
from bybit_grid.backtest.ohlc_replay.scenarios import RUN_ID


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=RUN_ID)
    p.add_argument("--output-root", default="data/processed/ohlc_replay_runs")
    p.add_argument("--report-root", default="reports/ohlc_replay_runs")
    p.add_argument("--fail-after-building-test-hook", action="store_true")
    a = p.parse_args(argv)
    out = Path(a.output_root) / a.run_id
    try:
        res = write_run(
            Path(a.output_root), Path(a.report_root), a.run_id, a.fail_after_building_test_hook
        )
        print(json.dumps(res, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as e:
        out.mkdir(parents=True, exist_ok=True)
        fail = {
            "run_id": a.run_id,
            "status": "failed",
            "error_type": type(e).__name__,
            "error_message": str(e),
        }
        (out / "ohlc_replay_run_status.json").write_bytes(canonical_json_bytes(fail))
        print(json.dumps(fail, sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    sys.exit(main())
