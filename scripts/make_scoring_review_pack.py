from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_scoring_review_pack import (
    GRAIN_CONTRACT_VERSION,
    OUTCOME_BOUNDARY_SEMANTICS_VERSION,
    REQUIRED,
    REVIEW_PACK_SCHEMA_VERSION,
    check_zip,
)
from scripts.report_cost_and_scoring import generate_cost_and_scoring_reports

PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_CONTRACT = (
    "persisted-exclusive-outcome-end-walk-forward-v1"
)


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
    grain = _load_json(data / "outcome_grain_contract_audit.json")
    coverage = _load_json(data / "walk_forward_coverage_audit.json")
    temporal = _load_json(data / "walk_forward_temporal_leakage_audit.json")
    leakage_summary = _load_json(data / "walk_forward_leakage_audit_summary.json")
    if (
        grain.get("grain_contract_audit_ok") is not True
        or grain.get("grain_contract_version") != GRAIN_CONTRACT_VERSION
        or grain.get("outcome_boundary_semantics_version")
        != OUTCOME_BOUNDARY_SEMANTICS_VERSION
        or grain.get("persisted_outcome_end_required_bool") is not True
        or type(grain.get("derived_outcome_end_count")) is not int
        or grain.get("derived_outcome_end_count") != 0
        or grain.get("legacy_outcome_end_column_allowed_bool") is not False
    ):
        raise SystemExit(
            json.dumps(
                {
                    "review_pack_ok": False,
                    "error": "persisted_outcome_grain_contract_not_ok",
                    "scoring_run_id": scoring_run_id,
                },
                sort_keys=True,
            )
        )
    for name, audit, ok_key in [
        ("walk_forward_coverage_audit.json", coverage, "walk_forward_coverage_audit_ok"),
        (
            "walk_forward_temporal_leakage_audit.json",
            temporal,
            "temporal_leakage_audit_ok",
        ),
        ("walk_forward_leakage_audit_summary.json", leakage_summary, "leakage_audit_ok"),
    ]:
        if (
            audit.get(ok_key) is not True
            or audit.get("outcome_boundary_semantics_version")
            != OUTCOME_BOUNDARY_SEMANTICS_VERSION
            or audit.get("persisted_outcome_end_required_bool") is not True
            or type(audit.get("derived_outcome_end_count")) is not int
            or audit.get("derived_outcome_end_count") != 0
            or audit.get("legacy_outcome_end_column_allowed_bool") is not False
        ):
            raise SystemExit(
                json.dumps(
                    {
                        "review_pack_ok": False,
                        "error": "persisted_outcome_boundary_audit_not_ok",
                        "member": name,
                        "scoring_run_id": scoring_run_id,
                    },
                    sort_keys=True,
                )
            )
    boundary_artifacts = [
        data / "walk_forward_event_eligibility.parquet",
        data / "walk_forward_splits.parquet",
        data / "walk_forward_fold_summary.parquet",
        data / "walk_forward_exclusion_reason_summary.parquet",
    ]
    missing_boundary = [str(path) for path in boundary_artifacts if not path.exists()]
    if missing_boundary:
        raise SystemExit(
            json.dumps(
                {
                    "review_pack_ok": False,
                    "error": "missing_walk_forward_boundary_artifacts",
                    "missing": missing_boundary,
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
    canonical_boundary_members = {
        "walk_forward_event_eligibility.parquet",
        "walk_forward_splits.parquet",
        "walk_forward_fold_summary.parquet",
        "walk_forward_exclusion_reason_summary.parquet",
        "walk_forward_coverage_audit.json",
        "walk_forward_temporal_leakage_audit.json",
        "walk_forward_leakage_audit_summary.json",
    }
    for name in canonical_boundary_members:
        shutil.copyfile(data / name, rep / name)
    for name in REQUIRED:
        if name == "review_pack_manifest.json":
            continue
        if name in canonical_boundary_members:
            continue
        if not (rep / name).exists() and (data / name).exists():
            shutil.copyfile(data / name, rep / name)
    missing = [n for n in REQUIRED if n != "review_pack_manifest.json" and not (rep / n).exists()]
    if missing:
        raise SystemExit(json.dumps({"review_pack_ok": False, "missing_members": missing}))
    cost = json.loads((rep / "cost_model_audit.json").read_text())
    fee = json.loads((data / "fee_coverage_audit.json").read_text())
    manifest = {
        "review_pack_schema_version": REVIEW_PACK_SCHEMA_VERSION,
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
        "grain_contract_version": GRAIN_CONTRACT_VERSION,
        "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
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
