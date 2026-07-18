from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import polars as pl
import pytest

from scripts.check_scoring_review_pack import REQUIRED, check_zip


def _write_member(root: Path, name: str, payload: object) -> None:
    path = root / name
    if name.endswith(".parquet"):
        pl.DataFrame(payload).write_parquet(path)
    elif name.endswith(".json"):
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    else:
        path.write_text(str(payload), encoding="utf-8")


def _valid_pack(tmp_path: Path, run_id: str = "run_x") -> Path:
    root = tmp_path / "members"
    root.mkdir()
    jsons = {
        "fee_coverage_audit.json": {
            "fee_coverage_ok": True,
            "fee_coverage_rate": 1.0,
            "fee_snapshot_id_resolved": "snap",
            "fee_source": "account_actual",
        },
        "cost_model_audit.json": {
            "cost_model_audit_ok": True,
            "fee_snapshot_id_resolved": "snap",
            "fee_source": "account_actual",
            "cost_formula_version": "cost_formula_v2_asymmetric_slippage",
            "risk_budget_proven_bool": False,
        },
        "cost_summary_audit.json": {
            "cost_summary_audit_ok": True,
            "cost_summary_grain": "event_horizon_grid",
            "cost_summary_duplicate_key_count": 0,
            "cost_summary_dimension_multiplication_detected_bool": False,
            "cost_summary_source_rows": 1,
        },
        "scoring_run_status.json": {
            "status": "complete",
            "scoring_run_id": run_id,
            "source_outcome_run_id": "outcome_x",
        },
        "outcome_source_audit.json": {"source_audit_ok": True, "source_outcome_run_id": "outcome_x"},
        "outcome_grain_audit.json": {"grain_audit_ok": True, "rows": {"expanded_scoring_input": 2}},
        "outcome_cartesian_completeness_audit.json": {"cartesian_completeness_ok": True},
        "outcome_grain_contract_audit.json": {
            "grain_contract_audit_ok": True,
            "synthetic_row_risk_detected_bool": False,
            "grain_contract_version": "grain_contract_v3_whole_row",
            "category_present_by_grain": {},
            "category_values_by_grain": {},
            "null_required_column_counts_by_grain": {},
        },
        "scoring_semantics_audit.json": {
            "scoring_semantics_audit_ok": True,
            "canonical_score_version": "v3",
            "source_outcome_run_id": "outcome_x",
            "risk_budget_proven_bool": False,
        },
        "walk_forward_coverage_audit.json": {
            "walk_forward_coverage_audit_ok": True,
            "coverage_reconciliation_ok": True,
            "sufficient_for_parameter_selection_bool": False,
        },
        "walk_forward_leakage_audit_summary.json": {"leakage_audit_ok": True},
        "walk_forward_temporal_leakage_audit.json": {"temporal_leakage_audit_ok": True},
        "outcome_category_normalization_audit.json": {
            "category_normalization_ok": True,
            "rows_before": 2,
            "rows_after": 2,
            "normalized_categories": ["linear"],
            "default_category": "linear",
            "category_source": "source_column",
            "source_categories": [" Linear "],
        },
        "fee_join_context_audit.json": {
            "expanded_scoring_input": {
                "fee_join_ok": True,
                "input_rows": 2,
                "output_rows": 2,
                "scoring_categories": ["linear"],
                "missing_fee_row_count": 0,
                "symbols_missing_fee_rates": [],
                "scoring_symbol_count": 1,
                "fee_symbol_count": 1,
            },
            "cost_summary_event_horizon_grid": {
                "fee_join_ok": True,
                "input_rows": 1,
                "output_rows": 1,
                "scoring_categories": ["linear"],
                "missing_fee_row_count": 0,
                "symbols_missing_fee_rates": [],
                "scoring_symbol_count": 1,
                "fee_symbol_count": 1,
            },
        },
        "score_correlation_report.json": {"score_correlation_report_ok": True},
    }
    for g in ["event_horizon", "event_horizon_sl", "event_horizon_grid", "expanded_scoring_input"]:
        jsons["outcome_grain_contract_audit.json"]["category_present_by_grain"][g] = True
        jsons["outcome_grain_contract_audit.json"]["category_values_by_grain"][g] = ["linear"]
        jsons["outcome_grain_contract_audit.json"]["null_required_column_counts_by_grain"][g] = {
            "category": 0
        }
    parquets = {
        "cost_scenario_summary.parquet": {"x": [1]},
        "score_component_summary.parquet": {"x": [1]},
        "outcome_scoring_summary.parquet": {"x": [1]},
        "walk_forward_exclusion_reason_summary.parquet": {"x": [1]},
        "walk_forward_fold_summary.parquet": {
            "coverage_reconciliation_ok": [True],
            "coverage_reconciliation_delta": [0],
            "unassigned_event_count": [0],
            "train_events": [1],
            "validation_events": [1],
            "test_events": [1],
            "actual_train_days": [10],
            "configured_train_days": [10],
            "purge_gap_minutes": [2880],
            "embargo_gap_minutes": [2880],
            "sufficient_for_parameter_selection_bool": [False],
            "sufficient_for_state_machine_engineering_bool": [True],
        },
    }
    for name in REQUIRED - {"review_pack_manifest.json"}:
        if name in jsons:
            _write_member(root, name, jsons[name])
        elif name in parquets:
            _write_member(root, name, parquets[name])
        else:
            _write_member(root, name, "account_actual")
    sha = {
        n: hashlib.sha256((root / n).read_bytes()).hexdigest()
        for n in REQUIRED - {"review_pack_manifest.json"}
    }
    manifest = {
        "review_pack_schema_version": "scoring_review_pack_v4_audit_complete",
        "manifest_hash_policy": "self_excluded_v1",
        "review_phase": "state_machine_engineering_ready",
        "parameter_selection_authorized_bool": False,
        "live_authorized_bool": False,
        "scoring_run_id": run_id,
        "source_outcome_run_id": "outcome_x",
        "fee_snapshot_id_resolved": "snap",
        "cost_formula_version": "cost_formula_v2_asymmetric_slippage",
        "grain_contract_version": "grain_contract_v3_whole_row",
        "canonical_score_version": "v3",
        "risk_budget_proven_bool": False,
        "members": sorted(REQUIRED),
        "sha256": sha,
    }
    _write_member(root, "review_pack_manifest.json", manifest)
    zpath = tmp_path / "pack.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        for name in sorted(REQUIRED):
            z.write(root / name, name)
    return zpath


def _mutate_manifest(zpath: Path, tmp_path: Path, field: str, value: object) -> Path:
    tampered = tmp_path / f"tampered_{field}.zip"
    with zipfile.ZipFile(zpath) as src, zipfile.ZipFile(tampered, "w") as dst:
        manifest = json.loads(src.read("review_pack_manifest.json"))
        manifest[field] = value
        for name in src.namelist():
            if name == "review_pack_manifest.json":
                dst.writestr(name, json.dumps(manifest, sort_keys=True).encode())
            else:
                dst.writestr(name, src.read(name))
    return tampered


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("risk_budget_proven_bool", True, "manifest_risk_budget_proven_bool"),
        ("canonical_score_version", "v999", "manifest_canonical_score_version"),
        ("grain_contract_version", "wrong", "manifest_grain_contract_version"),
        ("source_outcome_run_id", "other", "manifest_source_outcome_run_id"),
        ("fee_snapshot_id_resolved", "other", "manifest_fee_snapshot_id_resolved"),
        ("cost_formula_version", "other", "manifest_cost_formula_version"),
        ("parameter_selection_authorized_bool", True, "parameter_selection_authorized_bool"),
        ("live_authorized_bool", True, "live_authorized_bool"),
    ],
)
def test_checker_rejects_self_excluded_manifest_tampering(
    tmp_path: Path, field: str, value: object, error: str
):
    zpath = _valid_pack(tmp_path)
    tampered = _mutate_manifest(zpath, tmp_path, field, value)

    res = check_zip(str(tampered), "run_x")

    assert res["review_pack_ok"] is False
    assert error in res["consistency_errors"]
    assert res["hash_mismatches"] == []


def test_checker_requires_and_validates_new_audits_and_manifest_hashes(tmp_path: Path):
    zpath = _valid_pack(tmp_path)
    res = check_zip(str(zpath), "run_x")
    assert res["review_pack_ok"] is True
    assert len(res["members"]) == 29


def test_checker_detects_tampered_required_member_by_hash(tmp_path: Path):
    zpath = _valid_pack(tmp_path)
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(zpath) as src, zipfile.ZipFile(tampered, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, b"changed" if n == "fee_snapshot_report.md" else src.read(n))
    res = check_zip(str(tampered), "run_x")
    assert res["review_pack_ok"] is False
    assert "fee_snapshot_report.md" in res["hash_mismatches"]


def test_manifest_has_no_self_hash_and_complete_other_hashes(tmp_path: Path):
    zpath = _valid_pack(tmp_path)
    with zipfile.ZipFile(zpath) as z:
        manifest = json.loads(z.read("review_pack_manifest.json"))
    assert "review_pack_manifest.json" not in manifest["sha256"]
    assert set(manifest["sha256"]) == REQUIRED - {"review_pack_manifest.json"}


def test_make_pack_refuses_building_failed_and_missing_new_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.make_scoring_review_pack import make_pack

    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data/processed/scoring_runs/run_x"
    data.mkdir(parents=True)
    for status in ["building", "failed"]:
        (data / "scoring_run_status.json").write_text(
            json.dumps({"status": status, "scoring_run_id": "run_x"})
        )
        with pytest.raises(SystemExit):
            make_pack("run_x")
    (data / "scoring_run_status.json").write_text(
        json.dumps({"status": "complete", "scoring_run_id": "run_x"})
    )
    (data / "cost_summary_audit.json").write_text(json.dumps({"cost_summary_audit_ok": True}))
    (data / "scoring_semantics_audit.json").write_text(
        json.dumps({"scoring_semantics_audit_ok": True})
    )
    with pytest.raises(SystemExit):
        make_pack("run_x")


def test_build_scoring_dataset_writes_failed_status_after_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import bybit_grid.research.scoring.score_builder as sb

    monkeypatch.chdir(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("deliberate")

    monkeypatch.setattr(sb, "_build_scoring_dataset_impl", boom)
    with pytest.raises(RuntimeError):
        sb.build_scoring_dataset(Path("in.parquet"), "run_fail")
    status = json.loads(
        Path("data/processed/scoring_runs/run_fail/scoring_run_status.json").read_text()
    )
    assert status["status"] == "failed"
    assert status["error_summary"] == "deliberate"


def test_no_live_create_close_order_telegram_additions():
    from bybit_grid.common.source_safety_audit import audit_source_tree

    assert audit_source_tree(Path.cwd()).ok



def test_make_pack_refuses_missing_fee_join_when_category_audit_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.make_scoring_review_pack import make_pack

    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data/processed/scoring_runs/run_x"
    data.mkdir(parents=True)
    (data / "scoring_run_status.json").write_text(
        json.dumps({"status": "complete", "scoring_run_id": "run_x"})
    )
    (data / "cost_summary_audit.json").write_text(json.dumps({"cost_summary_audit_ok": True}))
    (data / "scoring_semantics_audit.json").write_text(
        json.dumps({"scoring_semantics_audit_ok": True})
    )
    (data / "outcome_category_normalization_audit.json").write_text(
        json.dumps({"category_normalization_ok": True})
    )

    with pytest.raises(SystemExit) as exc:
        make_pack("run_x")

    payload = json.loads(str(exc.value))
    assert payload["error"] == "missing_required_preflight"
    assert payload["path"].endswith("fee_join_context_audit.json")


def test_make_pack_refuses_missing_category_audit_when_fee_join_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.make_scoring_review_pack import make_pack

    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data/processed/scoring_runs/run_x"
    data.mkdir(parents=True)
    (data / "scoring_run_status.json").write_text(
        json.dumps({"status": "complete", "scoring_run_id": "run_x"})
    )
    (data / "cost_summary_audit.json").write_text(json.dumps({"cost_summary_audit_ok": True}))
    (data / "scoring_semantics_audit.json").write_text(
        json.dumps({"scoring_semantics_audit_ok": True})
    )
    (data / "fee_join_context_audit.json").write_text(
        json.dumps(
            {
                "expanded_scoring_input": {"fee_join_ok": True},
                "cost_summary_event_horizon_grid": {"fee_join_ok": True},
            }
        )
    )

    with pytest.raises(SystemExit) as exc:
        make_pack("run_x")

    payload = json.loads(str(exc.value))
    assert payload["error"] == "missing_required_preflight"
    assert payload["path"].endswith("outcome_category_normalization_audit.json")


def test_build_scoring_dataset_writes_complete_only_after_required_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import bybit_grid.research.scoring.score_builder as sb

    monkeypatch.chdir(tmp_path)

    def controlled_impl(*args, **kwargs):
        root = Path("data/processed/scoring_runs/run_ok")
        status = json.loads((root / "scoring_run_status.json").read_text())
        assert status["status"] == "building"
        assert not (root / "outcome_scoring_dataset.parquet").exists()
        pl.DataFrame({"x": [1]}).write_parquet(root / "outcome_scoring_dataset.parquet")
        for name in [
            "fee_coverage_audit.json",
            "scoring_semantics_audit.json",
            "cost_summary_audit.json",
            "fee_join_context_audit.json",
        ]:
            (root / name).write_text(json.dumps({"ok": True}))
        return {"rows": 1, "risk_budget_proven_bool": False}

    monkeypatch.setattr(sb, "_build_scoring_dataset_impl", controlled_impl)

    result = sb.build_scoring_dataset(Path("in.parquet"), "run_ok")

    status = json.loads(Path("data/processed/scoring_runs/run_ok/scoring_run_status.json").read_text())
    assert result["rows"] == 1
    assert status["status"] == "complete"
    assert status["scoring_run_id"] == "run_ok"


def test_build_scoring_dataset_failed_status_never_remains_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import bybit_grid.research.scoring.score_builder as sb

    monkeypatch.chdir(tmp_path)

    def writes_complete_then_boom(*args, **kwargs):
        root = Path("data/processed/scoring_runs/run_fail")
        sb._write_status(root, {"status": "complete", "scoring_run_id": "run_fail"})
        raise RuntimeError("deliberate")

    monkeypatch.setattr(sb, "_build_scoring_dataset_impl", writes_complete_then_boom)

    with pytest.raises(RuntimeError):
        sb.build_scoring_dataset(Path("in.parquet"), "run_fail")

    status = json.loads(
        Path("data/processed/scoring_runs/run_fail/scoring_run_status.json").read_text()
    )
    assert status["status"] == "failed"
    assert status["error_summary"] == "deliberate"
# Mandatory RED probe for issue #156 (7/8); behavior intentionally unchanged.
