from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from bybit_grid.backtest.neutral_grid.geometry import geometric_grid_levels_decimal
from bybit_grid.backtest.neutral_grid.serialization import canonical_json_bytes
from bybit_grid.backtest.ohlc_replay.evidence import (
    EvidenceError,
    build_records,
    check_zip,
    derive_scenario_audit,
    read_jsonl_from_bytes,
)
from bybit_grid.backtest.ohlc_replay.scenarios import (
    GUARDRAILS,
    OhlcReplayScenario,
    SCENARIO_CATALOG,
    SCENARIO_VERSION,
    ScenarioMode,
)


def _levels(low: str, high: str, cells: int) -> list[str]:
    return [str(x) for x in geometric_grid_levels_decimal(Decimal(low), Decimal(high), cells).levels]


def test_reported_levels_are_exact_geometric_not_arithmetic():
    audit = derive_scenario_audit()
    assert audit["scenario_checks_by_id"]["01_flat_no_ambiguity"]["canonical_levels"] == _levels("90", "110", 4)
    assert "95" not in audit["scenario_checks_by_id"]["01_flat_no_ambiguity"]["canonical_levels"]
    assert audit["scenario_checks_by_id"]["07_equal_pnl_different_nested_ledger"]["canonical_levels"] == _levels("80", "120", 6)
    assert audit["scenario_checks_by_id"]["11_low_price_grid"]["canonical_levels"] == _levels("0.008", "0.012", 4)
    assert audit["scenario_checks_by_id"]["12_tight_high_price_grid"]["canonical_levels"] == _levels("49900", "50100", 20)
    assert all(c["all_assignments_share_exact_geometry_bool"] for c in audit["scenario_checks_by_id"].values())


def test_arithmetic_and_rounded_level_substitution_rejected():
    s = SCENARIO_CATALOG[0]
    good = build_records()
    rows = read_jsonl_from_bytes(good["fixed_replay_results.jsonl"])
    bad = rows[0]["normalized_result"]
    bad["state_machine_result"]["levels"] = ["90", "95", "100", "105", "110"]
    audit = derive_scenario_audit(replay_records={s.scenario_id: [bad]})
    assert audit["scenario_audit_ok"] is False
    bad2 = json.loads(json.dumps(rows[0]["normalized_result"]))
    bad2["state_machine_result"]["levels"][1] = str(Decimal(bad2["state_machine_result"]["levels"][1]).quantize(Decimal("0.01")))
    audit2 = derive_scenario_audit(replay_records={s.scenario_id: [bad2]})
    assert audit2["scenario_audit_ok"] is False


@pytest.mark.parametrize("value", [True, 0, 1, "false"])
def test_guardrail_aliases_rejected(value):
    s = SCENARIO_CATALOG[0]
    expected = dict(s.expected)
    expected["risk_budget_proven_bool"] = value
    with pytest.raises(ValueError):
        OhlcReplayScenario(s.scenario_id, SCENARIO_VERSION, ScenarioMode.fixed_replay, s.config, s.entry_time_ms, s.candles, s.funding_observations, s.path_policies, None, expected)


def test_guardrails_derived_not_expected_identity():
    audit = derive_scenario_audit()
    guardrails = audit["scenario_checks_by_id"]["01_flat_no_ambiguity"]["guardrails"]
    assert guardrails == GUARDRAILS
    assert all(v is False for v in guardrails.values())


def test_termination_prefix_and_tampers_rejected():
    audit = derive_scenario_audit()
    c20 = audit["scenario_checks_by_id"]["20_termination_ignores_later_candles"]
    assert c20["consumed_event_prefix_exact_bool"] is True
    assert c20["later_price_or_funding_events_absent_bool"] is True
    assert c20["ignored_candle_count_reconciled_bool"] is True
    row = [r for r in read_jsonl_from_bytes(build_records()["fixed_replay_results.jsonl"]) if r["scenario_id"] == "20_termination_ignores_later_candles"][0]
    bad = row["normalized_result"]
    bad["generated_events"].append({**bad["generated_events"][-1], "price": "100"})
    assert derive_scenario_audit(replay_records={row["scenario_id"]: [bad]})["scenario_audit_ok"] is False
    bad2 = json.loads(json.dumps(row["normalized_result"]))
    bad2["candles_not_processed_after_termination"] = 0
    assert derive_scenario_audit(replay_records={row["scenario_id"]: [bad2]})["scenario_audit_ok"] is False


def test_scenario_04_and_07_fingerprints():
    audit = derive_scenario_audit()["scenario_checks_by_id"]
    assert audit["04_single_candle_path_insensitive"]["path_sensitive_bool"] is False
    assert audit["04_single_candle_path_insensitive"]["material_path_outcome_differs_bool"] is False
    assert audit["04_single_candle_path_insensitive"]["trace_sensitive_bool"] is True
    assert audit["07_equal_pnl_different_nested_ledger"]["exact_equal_pnl_bool"] is True
    assert audit["07_equal_pnl_different_nested_ledger"]["economic_fingerprint_equal_bool"] is True
    assert audit["07_equal_pnl_different_nested_ledger"]["ledger_differs_bool"] is True
    assert audit["08_two_candle_four_assignments"]["assignment_keys"] == ["00", "01", "10", "11"]
    assert audit["21_cycle_count_envelope_one_to_two"]["completed_cycle_count_min"] == 1
    assert audit["21_cycle_count_envelope_one_to_two"]["completed_cycle_count_max"] == 2


def _write_zip(tmp_path: Path, run_id="custom_run") -> Path:
    files = build_records(run_id)
    zpath = tmp_path / "pack.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return zpath


def _rezip_with(tmp_path: Path, src: Path, member: str, obj_or_bytes) -> Path:
    out = tmp_path / f"tampered-{member.replace('/', '_')}.zip"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        names = zin.namelist()
        payload = obj_or_bytes if isinstance(obj_or_bytes, bytes) else canonical_json_bytes(obj_or_bytes)
        for name in names:
            zout.writestr(name, payload if name == member else zin.read(name))
    return out


def test_custom_run_id_and_mismatched_report_rejected(tmp_path):
    zpath = _write_zip(tmp_path, "custom_run")
    with zipfile.ZipFile(zpath) as z:
        assert json.loads(z.read("review_pack_manifest.json"))["run_id"] == "custom_run"
        assert json.loads(z.read("ohlc_replay_run_status.json"))["run_id"] == "custom_run"
        assert b"run_id: custom_run" in z.read("ohlc_replay_report.md")
    assert check_zip(zpath, "custom_run")["review_pack_ok"] is True
    tampered = _rezip_with(tmp_path, zpath, "ohlc_replay_report.md", b"# OHLC Replay Synthetic Evidence Report\n\nrun_id: wrong\n")
    with pytest.raises(EvidenceError):
        check_zip(tampered, "custom_run")


def test_v2_schema_and_contract_audit_tamper_rejected(tmp_path):
    zpath = _write_zip(tmp_path)
    with zipfile.ZipFile(zpath) as z:
        manifest = json.loads(z.read("review_pack_manifest.json"))
        contract = json.loads(z.read("ohlc_replay_contract_audit.json"))
    manifest["review_pack_schema_version"] = "ohlc_minimal_path_review_pack_v2_semantic_replay"
    with pytest.raises(EvidenceError):
        check_zip(_rezip_with(tmp_path, zpath, "review_pack_manifest.json", manifest), "custom_run")
    contract["contract_audit_ok"] = False
    with pytest.raises(EvidenceError):
        check_zip(_rezip_with(tmp_path, zpath, "ohlc_replay_contract_audit.json", contract), "custom_run")


def test_no_private_live_telegram_code_additions():
    result = subprocess.run([sys.executable, "scripts/check_no_live_execution.py"], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
