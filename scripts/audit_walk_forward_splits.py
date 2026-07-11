from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.research.walk_forward.leakage_audit import write_leakage_audit

p = argparse.ArgumentParser()
p.add_argument("--scoring-run-id", required=True)
a = p.parse_args()
print(json.dumps(write_leakage_audit(a.scoring_run_id), sort_keys=True))
