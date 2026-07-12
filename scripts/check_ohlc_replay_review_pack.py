from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.backtest.ohlc_replay.evidence import check_zip
from bybit_grid.backtest.ohlc_replay.scenarios import RUN_ID


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("positional_zip", nargs="?")
    p.add_argument("--zip", dest="zip_path")
    p.add_argument("--run-id", default=RUN_ID)
    a = p.parse_args(argv)
    zp = a.zip_path or a.positional_zip
    try:
        if not zp:
            raise ValueError("zip_missing")
        print(json.dumps(check_zip(Path(zp), a.run_id), sort_keys=True, separators=(",", ":")))
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
