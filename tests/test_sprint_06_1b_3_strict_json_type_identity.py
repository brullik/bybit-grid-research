from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from bybit_grid.backtest.neutral_grid.evidence import (
    EVIDENCE_TYPE_CONTRACT_VERSION,
    MEMBERS,
    REVIEW_PACK_SCHEMA_VERSION,
    build_evidence_records,
    canonical_json_bytes,
)
from bybit_grid.backtest.neutral_grid.scenarios import SCENARIO_IDS

RUN = "neutral_sm_v1_synthetic_v2"


def _run_build(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    rep = tmp_path / "rep"
    pack = tmp_path / "pack.zip"
    r = subprocess.run(
        [sys.executable, "scripts/run_neutral_grid_synthetic_matrix.py", "--run-id", RUN, "--output-root", str(out), "--report-root", str(rep)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    b = subprocess.run(
        [sys.executable, "scripts/make_state_machine_review_pack.py", "--run-id", RUN, "--output-root", str(out), "--report-root", str(rep), "--pack-path", str(pack)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert b.returncode == 0, b.stdout + b.stderr
    return pack


def _check(pack: Path) -> dict[str, object]:
    r = subprocess.run([sys.executable, "scripts/check_state_machine_review_pack.py", "--zip", str(pack), "--run-id", RUN], text=True, capture_output=True, check=False)
    out = json.loads(r.stdout)
    out["returncode"] = r.returncode
    return out


def _files(pack: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(pack) as z:
        return {n: z.read(n) for n in z.namelist()}


def _write(dst: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(dst, "w") as w:
        for name in MEMBERS:
            w.writestr(name, files[name])
    return dst


def _rehash(files: dict[str, bytes], member: str) -> None:
    man = json.loads(files["review_pack_manifest.json"])
    man["sha256"][member] = hashlib.sha256(files[member]).hexdigest()
    files["review_pack_manifest.json"] = canonical_json_bytes(man)


def _mutate_json_member(pack: Path, tmp_path: Path, member: str, replacements: list[tuple[bytes, bytes]], name: str) -> Path:
    files = _files(pack)
    payload = files[member]
    for old, new in replacements:
        assert old in payload
        payload = payload.replace(old, new, 1)
    files[member] = payload
    if member != "review_pack_manifest.json":
        _rehash(files, member)
    return _write(tmp_path / f"{name}.zip", files)


def _mutate_manifest(pack: Path, tmp_path: Path, mutator, name: str) -> Path:
    files = _files(pack)
    man = json.loads(files["review_pack_manifest.json"])
    mutator(man)
    files["review_pack_manifest.json"] = canonical_json_bytes(man)
    return _write(tmp_path / f"{name}.zip", files)


def _expect_error(pack: Path, error: str) -> None:
    out = _check(pack)
    assert out["returncode"] == 1
    assert out["error"] == error
    assert error != "hash_mismatch"


def test_manifest_strict_types_and_v3_contract(tmp_path: Path):
    pack = _run_build(tmp_path)
    assert _check(pack)["review_pack_ok"] is True
    cases = [
        (lambda m: m.__setitem__("risk_budget_proven_bool", 0), "manifest_type_mismatch"),
        (lambda m: m.__setitem__("parameter_selection_authorized_bool", 0), "manifest_type_mismatch"),
        (lambda m: m.__setitem__("live_authorized_bool", 0), "manifest_type_mismatch"),
        (lambda m: m.__setitem__("sha256", {**m["sha256"], "state_machine_run_status.json": m["sha256"]["state_machine_run_status.json"].upper()}), "manifest_sha256_format_mismatch"),
        (lambda m: m.__setitem__("sha256", {**m["sha256"], "state_machine_run_status.json": "0" * 63}), "manifest_sha256_format_mismatch"),
        (lambda m: m.pop("evidence_type_contract_version"), "manifest_key_set_mismatch"),
        (lambda m: m.__setitem__("evidence_type_contract_version", "wrong"), "manifest_semantics_mismatch"),
        (lambda m: m.__setitem__("review_pack_schema_version", "neutral_grid_state_machine_review_pack_v2"), "manifest_semantics_mismatch"),
    ]
    for i, (mutator, error) in enumerate(cases):
        _expect_error(_mutate_manifest(pack, tmp_path, mutator, f"manifest-{i}"), error)
    bad = _mutate_json_member(pack, tmp_path, "review_pack_manifest.json", [(b'"canonical_scenario_count":33', b'"canonical_scenario_count":33.0')], "manifest-float")
    _expect_error(bad, "json_float_forbidden")


def test_json_document_bool_int_and_int_float_substitutions_rejected(tmp_path: Path):
    pack = _run_build(tmp_path)
    cases = [
        ("state_machine_contract_audit.json", [(b'"contract_audit_ok":true', b'"contract_audit_ok":1')], "contract_audit_semantics_mismatch"),
        ("reproducibility_audit.json", [(b'"reproducibility_audit_ok":true', b'"reproducibility_audit_ok":1')], "reproducibility_audit_semantics_mismatch"),
        ("scenario_audit.json", [(b'"scenario_audit_ok":true', b'"scenario_audit_ok":1')], "scenario_audit_semantics_mismatch"),
        ("state_machine_run_status.json", [(b'"canonical_scenario_count":33', b'"canonical_scenario_count":33.0')], "json_float_forbidden"),
        ("state_machine_run_status.json", [(b'"canonical_scenario_count":33', b'"canonical_scenario_count":true')], "status_semantics_mismatch"),
    ]
    for i, (member, repl, error) in enumerate(cases):
        _expect_error(_mutate_json_member(pack, tmp_path, member, repl, f"doc-{i}"), error)


def test_jsonl_strict_type_identity_rejections_are_semantic(tmp_path: Path):
    pack = _run_build(tmp_path)
    cases = [
        ("scenario_inputs.jsonl", [(b'"sequence_id":1', b'"sequence_id":true')], "input_records_mismatch"),
        ("scenario_inputs.jsonl", [(b'"time_ms":1', b'"time_ms":1.0')], "json_float_forbidden"),
        ("scenario_inputs.jsonl", [(b'"grid_cell_number":4', b'"grid_cell_number":4.0')], "json_float_forbidden"),
        ("scenario_inputs.jsonl", [(b'"expected_termination_reason":null', b'"expected_termination_reason":false')], "input_records_mismatch"),
        ("scenario_results.jsonl", [(b'"result_audit_passed_bool":true', b'"result_audit_passed_bool":1')], "stored_result_replay_mismatch"),
        ("ledger_events.jsonl", [(b'"sequence_id":1', b'"sequence_id":true')], "ledger_rows_replay_mismatch"),
        ("ledger_events.jsonl", [(b'"time_ms":1', b'"time_ms":1.0')], "json_float_forbidden"),
        ("ledger_events.jsonl", [(b'"level_index":0', b'"level_index":0.0')], "json_float_forbidden"),
        ("completed_cycles.jsonl", [(b'"open_level_index":0', b'"open_level_index":0.0')], "json_float_forbidden"),
        ("completed_cycles.jsonl", [(b'"close_level_index":1', b'"close_level_index":true')], "cycle_rows_replay_mismatch"),
    ]
    for i, (member, repl, error) in enumerate(cases):
        _expect_error(_mutate_json_member(pack, tmp_path, member, repl, f"jsonl-{i}"), error)


def test_nonstandard_numbers_duplicate_keys_and_canonical_syntax(tmp_path: Path):
    pack = _run_build(tmp_path)
    for token, error in [(b"NaN", "nonfinite_json_number_forbidden"), (b"Infinity", "nonfinite_json_number_forbidden"), (b"1e0", "json_float_forbidden")]:
        bad = _mutate_json_member(pack, tmp_path, "state_machine_run_status.json", [(b'"failed_scenario_count":0', b'"failed_scenario_count":' + token)], token.decode("ascii", "ignore") or "nan")
        _expect_error(bad, error)
    dup = _mutate_json_member(pack, tmp_path, "scenario_catalog.json", [(b'{"canonical_scenario_count":33', b'{"canonical_scenario_count":33,"canonical_scenario_count":33')], "dup")
    _expect_error(dup, "duplicate_json_key")
    space = _mutate_json_member(pack, tmp_path, "scenario_catalog.json", [(b'{"canonical_scenario_count":33', b'{ "canonical_scenario_count":33')], "space")
    _expect_error(space, "noncanonical_json_bytes")


def test_happy_path_counts_guardrails_and_no_live_audit(tmp_path: Path):
    pack = _run_build(tmp_path)
    out = _check(pack)
    assert out["review_pack_ok"] is True
    assert out["input_records_verified"] == 33
    assert out["result_records_verified"] == 33
    assert out["ledger_rows_verified"] == 112
    assert out["cycle_rows_verified"] == 20
    assert len(SCENARIO_IDS) == 33
    inputs, results, ledger, cycles = build_evidence_records()
    assert (len(inputs), len(results), len(ledger), len(cycles)) == (33, 33, 112, 20)
    with zipfile.ZipFile(pack) as z:
        man = json.loads(z.read("review_pack_manifest.json"))
    assert man["review_pack_schema_version"] == REVIEW_PACK_SCHEMA_VERSION
    assert man["evidence_type_contract_version"] == EVIDENCE_TYPE_CONTRACT_VERSION
    assert man["risk_budget_proven_bool"] is False
    assert man["parameter_selection_authorized_bool"] is False
    assert man["live_authorized_bool"] is False
    r = subprocess.run([sys.executable, "scripts/check_no_live_execution.py"], text=True, capture_output=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
