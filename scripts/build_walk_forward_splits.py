from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.research.walk_forward.splits import write_splits

p = argparse.ArgumentParser()
p.add_argument("--scoring-run-id", required=True)
p.add_argument("--profile", default="prototype_90d")
a = p.parse_args()
print(json.dumps(write_splits(a.scoring_run_id, a.profile), sort_keys=True))
