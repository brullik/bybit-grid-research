from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_scoring_review_pack import REQUIRED, check_zip
from scripts.report_cost_and_scoring import generate_cost_and_scoring_reports


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SystemExit(
            json.dumps(
                {"review_pack_ok": False, "error": "missing_required_preflight", "path": str(path)}
            )
        )
    return json.loads(path.read_text())


def _preflight_complete_scoring(scoring_run_id: str, data: Path, rep: Path) -> None:
    status = _load_json(data / "scoring_run_status.json")
    if status.get("status") != "complete" or status.get("scoring_run_id") != scoring_run_id:
        raise SystemExit(
            json.dumps(
                {
                    "review_pack_ok": False,
                    "error": "scoring_run_not_complete",
                    "scoring_run_id": scoring_run_id,
                    "status": status,
                },
                sort_keys=True,
            )
        )
    cost = _load_json(data / "cost_summary_audit.json")
    sem = _load_json(data / "scoring_semantics_audit.json")
    cat = _load_json(data / "outcome_category_normalization_audit.json")
    fee_join = _load_json(data / "fee_join_context_audit.json")
    if cost.get("cost_summary_audit_ok") is not True:
        raise SystemExit(
            json.dumps(
                {
                    "review_pack_ok": False,
                    "error": "cost_summary_audit_not_ok",
                    "scoring_run_id": scoring_run_id,
                },
                sort_keys=True,
            )
        )
    if sem.get("scoring_semantics_audit_ok") is not True:
        raise SystemExit(
            json.dumps(
                {
                    "review_pack_ok": False,
                    "error": "scoring_semantics_audit_not_ok",
                    "scoring_run_id": scoring_run_id,
                },
                sort_keys=True,
            )
        )
    if cat.get("category_normalization_ok") is not True:
        raise SystemExit(
            json.dumps(
                {
                    "review_pack_ok": False,
                    "error": "category_normalization_audit_not_ok",
                    "scoring_run_id": scoring_run_id,
                },
                sort_keys=True,
            )
        )
    if set(fee_join) != {"expanded_scoring_input", "cost_summary_event_horizon_grid"} or any(
        v.get("fee_join_ok") is not True for v in fee_join.values()
    ):
        raise SystemExit(
            json.dumps(
                {
                    "review_pack_ok": False,
                    "error": "fee_join_context_audit_not_ok",
                    "scoring_run_id": scoring_run_id,
                },
                sort_keys=True,
            )
        )
    required_cost = [
        data / "cost_summary_audit.json",
        rep / "cost_scenario_summary.parquet",
        rep / "cost_scenario_report.md",
        rep / "cost_model_audit.json",
    ]
    missing = [str(p) for p in required_cost if not p.exists()]
    if missing:
        raise SystemExit(
            json.dumps(
                {
                    "review_pack_ok": False,
                    "error": "missing_cost_artifacts",
                    "missing": missing,
                    "scoring_run_id": scoring_run_id,
                },
                sort_keys=True,
            )
        )


def make_pack(scoring_run_id: str) -> dict[str, object]:
    rep = Path("reports/scoring_runs") / scoring_run_id
    data = Path("data/processed/scoring_runs") / scoring_run_id
    rep.mkdir(parents=True, exist_ok=True)
    _preflight_complete_scoring(scoring_run_id, data, rep)
    before = {
        p: p.read_bytes()
        for p in [rep / "cost_model_config_resolved.yml", rep / "cost_model_audit.json"]
        if p.exists()
    }
    generate_cost_and_scoring_reports(scoring_run_id)
    for p, b in before.items():
        if p.read_bytes() != b:
            raise RuntimeError(f"canonical provenance overwritten: {p}")
    for name in REQUIRED:
        if name == "review_pack_manifest.json":
            continue
        if not (rep / name).exists() and (data / name).exists():
            shutil.copyfile(data / name, rep / name)
    missing = [n for n in REQUIRED if n != "review_pack_manifest.json" and not (rep / n).exists()]
    if missing:
        raise SystemExit(json.dumps({"review_pack_ok": False, "missing_members": missing}))
    cost = json.loads((rep / "cost_model_audit.json").read_text())
    fee = json.loads((data / "fee_coverage_audit.json").read_text())
    manifest = {
        "review_pack_schema_version": "scoring_review_pack_v4_audit_complete",
        "manifest_hash_policy": "self_excluded_v1",
        "review_phase": "state_machine_engineering_ready",
        "parameter_selection_authorized_bool": False,
        "live_authorized_bool": False,
        "scoring_run_id": scoring_run_id,
        "source_outcome_run_id": json.loads((data / "outcome_source_audit.json").read_text()).get(
            "source_outcome_run_id"
        )
        if (data / "outcome_source_audit.json").exists()
        else None,
        "fee_snapshot_id_resolved": fee.get("fee_snapshot_id_resolved"),
        "cost_formula_version": cost.get("cost_formula_version"),
        "grain_contract_version": "grain_contract_v3_whole_row",
        "canonical_score_version": "v3",
        "risk_budget_proven_bool": False,
        "members": sorted(REQUIRED),
        "sha256": {},
    }
    for name in sorted(REQUIRED - {"review_pack_manifest.json"}):
        manifest["sha256"][name] = hashlib.sha256((rep / name).read_bytes()).hexdigest()
    (rep / "review_pack_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    zip_path = Path(f"pm_review_pack_scoring_{scoring_run_id}.zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(REQUIRED):
            z.write(rep / name, arcname=name)
    res = check_zip(str(zip_path), scoring_run_id)
    if not res["review_pack_ok"]:
        zip_path.unlink(missing_ok=True)
        raise SystemExit(json.dumps(res, sort_keys=True))
    return {"review_pack_zip": str(zip_path), "review_pack_ok": True, "members": sorted(REQUIRED)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--scoring-run-id", required=True)
    a = p.parse_args()
    print(json.dumps(make_pack(a.scoring_run_id), sort_keys=True))
# Mandatory RED probe for issue #156 (5/8); behavior intentionally unchanged.
