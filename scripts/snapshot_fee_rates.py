from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.research.cost_model.fee_snapshot import fetch_account_fee_rates, write_fee_snapshot

p = argparse.ArgumentParser()
p.add_argument("--category", default="linear")
p.add_argument("--symbols-from-outcome-run")
p.add_argument("--all-linear", action="store_true")
p.add_argument("--offline-scenario")
args = p.parse_args()
if args.offline_scenario:
    raise SystemExit(
        "offline manual scenarios are supported via config/cost_scenarios.yml; they are source=manual_scenario and not account_actual"
    )
sid, rows = fetch_account_fee_rates(args.category)
paths = write_fee_snapshot(rows, sid)
print(
    json.dumps(
        {"fee_snapshot_id": sid, "symbols_with_fee_rates": len(rows), "paths": paths},
        sort_keys=True,
    )
)
