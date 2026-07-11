from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.research.scoring.score_builder import build_scoring_dataset

p = argparse.ArgumentParser()
p.add_argument("--outcome-run-id")
p.add_argument("--scoring-run-id", required=True)
p.add_argument("--fee-snapshot-id")
p.add_argument("--cost-config")
p.add_argument("--fast-max", action="store_true")
a = p.parse_args()
inp = Path("data/processed/scoring_runs") / a.scoring_run_id / "expanded_scoring_input.parquet"
print(json.dumps(build_scoring_dataset(inp, a.scoring_run_id, fee_snapshot_id=a.fee_snapshot_id, cost_config=a.cost_config), sort_keys=True))
