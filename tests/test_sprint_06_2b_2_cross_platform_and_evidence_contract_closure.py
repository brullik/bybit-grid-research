from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from types import MappingProxyType

import pytest

from bybit_grid.backtest.ohlc_replay.evidence import (
    EvidenceError,
    MEMBERS,
    build_records,
    build_zip,
    check_zip,
    derive_reproducibility_audit_from_core,
    derive_scenario_audit,
    find_source_hygiene_violations,
    read_json,
    write_run,
)
from bybit_grid.backtest.ohlc_replay.scenarios import GUARDRAILS, SCENARIO_CATALOG, OhlcReplayScenario


def test_windows_posix_hygiene_and_uppercase_suffixes(tmp_path):
    (tmp_path / "operator.zip").write_text("ignored")
    (tmp_path / "operator.JSONL").write_text("ignored")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "bad.zip").write_text("x")
    assert find_source_hygiene_violations(tmp_path) == ["src/bad.zip"]
    (tmp_path / "src" / "BAD.JsonL").write_text("x")
    (tmp_path / "src" / "cache.PYC").write_text("x")
    assert find_source_hygiene_violations(tmp_path) == ["src/BAD.JsonL", "src/bad.zip", "src/cache.PYC"]


def test_run_status_lifecycle_and_no_review_pack_ok(tmp_path):
    out_root = tmp_path / "out"
    rep_root = tmp_path / "rep"
    with pytest.raises(EvidenceError):
        write_run(out_root, rep_root, fail_after_building=True)
    failed = read_json(out_root / "ohlc_minimal_v2_synthetic_audit_v3" / "ohlc_replay_run_status.json")
    assert failed["status"] == "failed" and "review_pack_ok" not in failed and "evidence_run_audit_ok" not in failed
    shutil.rmtree(out_root)
    shutil.rmtree(rep_root)
    with pytest.raises(EvidenceError):
        write_run(out_root, rep_root, fail_after_artifacts_test_hook=True)
    failed = read_json(out_root / "ohlc_minimal_v2_synthetic_audit_v3" / "ohlc_replay_run_status.json")
    assert failed["status"] == "failed" and "evidence_run_audit_ok" not in failed
    shutil.rmtree(out_root)
    shutil.rmtree(rep_root)
    res = write_run(out_root, rep_root)
    status = read_json(out_root / "ohlc_minimal_v2_synthetic_audit_v3" / "ohlc_replay_run_status.json")
    assert res["status"] == status["status"] == "complete"
    assert set(status) == {"run_id", "status", "scenario_count", "fixed_replay_result_count", "envelope_result_count", "evidence_run_audit_ok"}


def test_reproducibility_is_derived_and_fails_closed_on_byte_change():
    core = {k: v for k, v in build_records().items() if k.endswith(".jsonl")}
    ok = derive_reproducibility_audit_from_core(core)
    assert ok["reproducibility_audit_ok"] is True
    def mutate(second):
        second = dict(second)
        second["fixed_replay_results.jsonl"] = second["fixed_replay_results.jsonl"].replace(b'"scenario_id":"01_flat_no_ambiguity"', b'"scenario_id":"01_flat_no_ambiguity_X"', 1)
        return second
    bad = derive_reproducibility_audit_from_core(core, mutate_second=mutate)
    assert bad["reproducibility_audit_ok"] is False


def test_named_scenario_semantics_and_guardrails():
    a = derive_scenario_audit()
    c = a["scenario_checks_by_id"]
    assert c["05_single_candle_path_sensitive_long"]["positive_long_exposure_observed_bool"] is True
    assert c["05_single_candle_path_sensitive_long"]["all_final_positions_non_negative_bool"] is True
    assert c["06_single_candle_path_sensitive_short"]["all_final_positions_negative_bool"] is True
    assert c["09_gap_up_preserved"]["gap_direction"] == "up" and c["09_gap_up_preserved"]["gap_preserved_bool"] is True
    assert c["10_gap_down_preserved"]["gap_direction"] == "down" and c["10_gap_down_preserved"]["gap_preserved_bool"] is True
    assert c["11_low_price_grid"]["canonical_levels_preserved_bool"] is True
    assert c["12_tight_high_price_grid"]["canonical_level_count"] == 21
    assert c["13_positive_funding_long"]["cumulative_funding_pnl_sign"] == "negative"
    assert c["14_positive_funding_short"]["cumulative_funding_pnl_sign"] == "positive"
    assert c["15_negative_funding_long"]["cumulative_funding_pnl_sign"] == "positive"
    assert c["16_flat_position_funding_zero"]["cumulative_funding_pnl_sign"] == "zero"
    assert c["17_two_funding_boundaries"]["funding_event_count"] == 2
    assert c["20_termination_ignores_later_candles"]["candles_not_processed_after_termination"] >= 1
    assert c["22_bybit_source_enum_contract"]["synthetic_fixture_of_source_contract_bool"] is True
    assert c["23_lower_only_termination_guardrail"]["lower_termination_side_configured_bool"] is True
    assert c["24_upper_only_termination_guardrail"]["upper_termination_side_configured_bool"] is True
    assert all(v is False for v in c["01_flat_no_ambiguity"]["guardrails"].values())


def test_expected_contract_rejects_unknown_and_nested_mutable():
    s = SCENARIO_CATALOG[0]
    with pytest.raises(ValueError):
        OhlcReplayScenario(**{**s.__dict__, "expected": MappingProxyType({**GUARDRAILS, "unknown": True})})
    with pytest.raises(ValueError):
        OhlcReplayScenario(**{**s.__dict__, "expected": MappingProxyType({**GUARDRAILS, "path_sensitive_bool": []})})


def _write_pack(tmp_path):
    out_root = tmp_path / "out"
    rep_root = tmp_path / "rep"
    write_run(out_root, rep_root)
    z = tmp_path / "pack.zip"
    run = "ohlc_minimal_v2_synthetic_audit_v3"
    build_zip(out_root / run, rep_root / run, z)
    return z


@pytest.mark.parametrize("member", [
    "scenario_inputs.jsonl", "fixed_replay_results.jsonl", "generated_replay_events.jsonl",
    "state_machine_ledger.jsonl", "completed_cycles.jsonl", "envelope_results.jsonl",
    "review_pack_manifest.json", "ohlc_replay_report.md", "reproducibility_audit.json",
])
def test_semantic_tamper_rejected_after_rehash(tmp_path, member):
    z = _write_pack(tmp_path)
    tampered = tmp_path / f"tampered-{member.replace('/', '_')}.zip"
    with zipfile.ZipFile(z) as zin:
        data = {n: zin.read(n) for n in zin.namelist()}
    if member == "review_pack_manifest.json":
        manifest = json.loads(data["review_pack_manifest.json"])
        manifest["risk_budget_proven_bool"] = True
        data["review_pack_manifest.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    else:
        data[member] = data[member].replace(b"true", b"false", 1) if b"true" in data[member] else data[member] + b"x"
    manifest = json.loads(data["review_pack_manifest.json"])
    import hashlib
    manifest["sha256"][member] = hashlib.sha256(data[member]).hexdigest()
    data["review_pack_manifest.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with zipfile.ZipFile(tampered, "w") as zout:
        for n in MEMBERS:
            zout.writestr(n, data[n])
    with pytest.raises(Exception):
        check_zip(tampered)


def test_builder_refuses_incomplete_and_verifies_tmp(tmp_path):
    out = tmp_path / "out"
    rep = tmp_path / "rep"
    run = "ohlc_minimal_v2_synthetic_audit_v3"
    write_run(out, rep)
    (out / run / "ohlc_replay_run_status.json").write_text('{"run_id":"x","status":"building"}\n')
    with pytest.raises(Exception):
        build_zip(out / run, rep / run, tmp_path / "bad.zip")
    write_run(out, rep)
    dest = tmp_path / "ok.zip"
    build_zip(out / run, rep / run, dest)
    assert check_zip(dest)["review_pack_ok"] is True
    assert not (tmp_path / "ok.zip.tmp").exists()


def test_missing_zip_cli_strict_json_no_traceback(tmp_path):
    r = subprocess.run([sys.executable, "scripts/check_ohlc_replay_review_pack.py", "--zip", str(tmp_path / "missing.zip")], text=True, capture_output=True, check=False)
    assert r.returncode == 1 and r.stderr == ""
    assert json.loads(r.stdout)["review_pack_ok"] is False


def test_no_live_private_api_or_telegram_additions():
    r = subprocess.run([sys.executable, "scripts/check_no_live_execution.py"], text=True, capture_output=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
