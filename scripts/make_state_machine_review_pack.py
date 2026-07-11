from __future__ import annotations
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
MEMBERS = [
    "review_pack_manifest.json",
    "state_machine_run_status.json",
    "state_machine_contract_audit.json",
    "scenario_catalog.json",
    "scenario_inputs.jsonl",
    "scenario_results.jsonl",
    "ledger_events.jsonl",
    "completed_cycles.jsonl",
    "scenario_audit.json",
    "reproducibility_audit.json",
    "synthetic_scenario_report.md",
    "risk_budget_readiness_report.md",
]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default="neutral_sm_v1_synthetic")
    p.add_argument("--output-root", default="data/processed/state_machine_runs")
    p.add_argument("--report-root", default="reports/state_machine_runs")
    p.add_argument(
        "--pack-path", default="pm_review_pack_state_machine_neutral_sm_v1_synthetic.zip"
    )
    a = p.parse_args(argv)
    out = Path(a.output_root) / a.run_id
    rep = Path(a.report_root) / a.run_id
    status = json.loads((out / "state_machine_run_status.json").read_text())
    if status.get("status") != "complete":
        raise SystemExit("run status is not complete")
    src = {m: (out / m) for m in MEMBERS[1:10]} | {m: (rep / m) for m in MEMBERS[10:]}
    miss = [m for m, pth in src.items() if not pth.exists()]
    if miss:
        raise SystemExit(f"missing required artifact: {miss[0]}")
    sha = {
        m: hashlib.sha256(src[m].read_bytes()).hexdigest()
        for m in MEMBERS
        if m != "review_pack_manifest.json"
    }
    man = {
        "review_pack_schema_version": "neutral_grid_state_machine_review_pack_v1",
        "manifest_hash_policy": "self_excluded_v1",
        "review_phase": "synthetic_state_machine_evidence_complete",
        "run_id": a.run_id,
        "state_machine_contract_version": "native_neutral_grid_reference_contract_v1",
        "canonical_serialization_version": "neutral_grid_canonical_json_v1",
        "canonical_scenario_count": 33,
        "risk_budget_proven_bool": False,
        "parameter_selection_authorized_bool": False,
        "live_authorized_bool": False,
        "members": MEMBERS,
        "sha256": sha,
    }
    mb = (json.dumps(man, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with zipfile.ZipFile(a.pack_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("review_pack_manifest.json", mb)
        for m in MEMBERS[1:]:
            z.write(src[m], m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
