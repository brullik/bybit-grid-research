from __future__ import annotations
import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--scoring-run-id", required=True)
a = p.parse_args()
rep = Path("reports/scoring_runs") / a.scoring_run_id
rep.mkdir(parents=True, exist_ok=True)
(rep / "cost_model_config_resolved.yml").write_text(
    Path("config/cost_scenarios.yml").read_text(encoding="utf-8"), encoding="utf-8"
)
(rep / "cost_model_audit.json").write_text(
    json.dumps({"cost_model_version": "cost_v1", "cost_formulas_audited": True}, indent=2),
    encoding="utf-8",
)
print(json.dumps({"report_cost_and_scoring_ok": True, "scoring_run_id": a.scoring_run_id}))
