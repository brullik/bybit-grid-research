from __future__ import annotations

import json
import zipfile
from dataclasses import replace
from types import MappingProxyType

import pytest

from bybit_grid.backtest.ohlc_replay.evidence import (
    ALLOWED_GUARDRAIL_SOURCES,
    MEMBERS,
    build_contract_audit,
    build_records,
    check_zip,
    derive_scenario_audit,
    jsonl_bytes,
    sha_bytes,
)
from bybit_grid.backtest.ohlc_replay.replay import replay_ohlc_minimal_path
from bybit_grid.backtest.ohlc_replay.scenarios import (
    SCENARIO_CATALOG,
    REVIEW_PACK_SCHEMA_VERSION,
)
from bybit_grid.backtest.neutral_grid.serialization import canonical_json_bytes


def _fixed_scenario(sid="01_flat_no_ambiguity"):
    return next(s for s in SCENARIO_CATALOG if s.scenario_id == sid)


def _result_with_flag(scenario, key, value):
    r = replay_ohlc_minimal_path(
        scenario.config, scenario.entry_time_ms, scenario.candles, scenario.path_policies, scenario.funding_observations
    )
    flags = dict(r.state_machine_result.proof_flags)
    flags[key] = value
    sm = replace(r.state_machine_result, proof_flags=MappingProxyType(flags))
    return replace(r, state_machine_result=sm)


def test_nested_risk_budget_true_is_not_masked_and_fails():
    s = _fixed_scenario()
    audit = derive_scenario_audit(replay_records={s.scenario_id: [_result_with_flag(s, "risk_budget_proven_bool", True)]})
    check = audit["scenario_checks_by_id"][s.scenario_id]
    assert check["guardrails"]["risk_budget_proven_bool"] is True
    assert "risk_budget_proven_bool" in check["unexpected_true_guardrail_keys"]
    assert audit["scenario_audit_ok"] is False


@pytest.mark.parametrize("key", ["live_execution_present_bool", "profitability_claims_present_bool"])
def test_nested_live_profitability_true_is_not_masked(key):
    s = _fixed_scenario()
    audit = derive_scenario_audit(replay_records={s.scenario_id: [_result_with_flag(s, key, True)]})
    assert audit["scenario_checks_by_id"][s.scenario_id]["guardrails"][key] is True
    assert audit["scenario_audit_ok"] is False


@pytest.mark.parametrize("bad", [1, "false"])
def test_nested_proof_non_exact_bool_fails_closed(bad):
    s = _fixed_scenario()
    audit = derive_scenario_audit(replay_records={s.scenario_id: [_result_with_flag(s, "risk_budget_proven_bool", bad)]})
    check = audit["scenario_checks_by_id"][s.scenario_id]
    assert check["all_guardrails_exact_bool_bool"] is False
    assert audit["scenario_audit_ok"] is False


def test_proof_flags_disagree_across_envelope_assignments_fails():
    s = next(x for x in SCENARIO_CATALOG if x.scenario_id == "08_two_candle_four_assignments")
    from bybit_grid.backtest.ohlc_replay.envelope import enumerate_minimal_path_ambiguity_envelope

    env = enumerate_minimal_path_ambiguity_envelope(s.config, s.entry_time_ms, s.candles, s.funding_observations, s.max_exact_ambiguous_candles)
    results = list(env.assignment_results)
    flags = dict(results[0].state_machine_result.proof_flags)
    flags["risk_budget_proven_bool"] = True
    results[0] = replace(results[0], state_machine_result=replace(results[0].state_machine_result, proof_flags=MappingProxyType(flags)))
    audit = derive_scenario_audit(replay_records={s.scenario_id: results})
    assert audit["scenario_checks_by_id"][s.scenario_id]["nested_proof_flags_consistent_bool"] is False
    assert audit["scenario_audit_ok"] is False


def test_guardrail_sources_are_complete_and_allowed():
    audit = derive_scenario_audit()
    for check in audit["scenario_checks_by_id"].values():
        assert set(check["guardrails"]) == set(check["guardrail_sources_by_key"])
        assert set(check["guardrail_sources_by_key"].values()) <= ALLOWED_GUARDRAIL_SOURCES


def test_empty_and_partial_and_false_repro_contract_audits_fail():
    assert build_contract_audit({"scenario_checks_by_id": {}, "scenario_audit_ok": True})["contract_audit_ok"] is False
    audit = derive_scenario_audit()
    partial = {**audit, "scenario_checks_by_id": dict(list(audit["scenario_checks_by_id"].items())[:23])}
    assert build_contract_audit(partial)["contract_audit_ok"] is False
    assert build_contract_audit(audit, {"reproducibility_audit_ok": False})["contract_audit_ok"] is False


def test_every_contract_success_field_is_evidence_linked():
    ca = build_contract_audit(derive_scenario_audit())
    expected = {
        "closed_contiguous_1m_enforced_bool", "minimal_path_policies_frozen_bool", "funding_before_price_enforced_bool",
        "funding_source_provenance_enforced_bool", "strict_snapshot_identity_enforced_bool", "fresh_nested_replay_enforced_bool",
        "exact_cartesian_enumeration_enforced_bool", "canonical_geometric_levels_enforced_bool", "canonical_byte_identity_enforced_bool",
        "all_scenario_guardrails_derived_bool", "all_termination_prefixes_reconciled_bool", "all_scenario_audits_pass_bool", "no_live_execution_bool",
    }
    assert expected <= set(ca)
    assert ca["scenario_check_count"] == 24
    assert all(ca[k] is True for k in expected)


def test_termination_prefix_evidence_and_tamper_failures():
    audit = derive_scenario_audit()
    term = audit["scenario_checks_by_id"]["20_termination_ignores_later_candles"]["termination_prefix_evidence_by_assignment"][0]
    assert term["consumed_event_prefix_exact_bool"] is True
    assert term["unconsumed_event_count"] > 0
    assert term["termination_trigger_matches_last_consumed_event_bool"] is True
    s = _fixed_scenario("20_termination_ignores_later_candles")
    r = replay_ohlc_minimal_path(s.config, s.entry_time_ms, s.candles, s.path_policies, s.funding_observations)
    assert derive_scenario_audit(replay_records={s.scenario_id: [replace(r, generated_events=r.generated_events + r.generated_events[-1:])]})["scenario_audit_ok"] is False
    assert derive_scenario_audit(replay_records={s.scenario_id: [replace(r, generated_events=tuple(reversed(r.generated_events)))]})["scenario_audit_ok"] is False
    bad_sm = replace(r.state_machine_result, ledger=tuple(replace(e, sequence_id=e.sequence_id + 1) if e.event_type.value == "termination_trigger" else e for e in r.state_machine_result.ledger))
    assert derive_scenario_audit(replay_records={s.scenario_id: [replace(r, state_machine_result=bad_sm)]})["scenario_audit_ok"] is False
    assert derive_scenario_audit(replay_records={s.scenario_id: [replace(r, candles_not_processed_after_termination=r.candles_not_processed_after_termination + 1)]})["scenario_audit_ok"] is False


def test_non_terminated_scenario_consumes_full_schedule():
    term = derive_scenario_audit()["scenario_checks_by_id"]["01_flat_no_ambiguity"]["termination_prefix_evidence_by_assignment"][0]
    assert term["unconsumed_event_count"] == 0
    assert term["consumed_event_prefix_exact_bool"] is True


def _write_pack(tmp_path, files):
    zp = tmp_path / "pack.zip"
    with zipfile.ZipFile(zp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in MEMBERS:
            z.writestr(name, files[name])
    return zp


def test_persisted_input_first_detects_changed_members_after_rehash(tmp_path):
    files = build_records()
    fixed = [json.loads(line) for line in files["fixed_replay_results.jsonl"].splitlines()]
    fixed[0]["normalized_result"]["final_total_pnl_usdt"] = "999"
    files["fixed_replay_results.jsonl"] = jsonl_bytes(fixed)
    manifest = json.loads(files["review_pack_manifest.json"])
    manifest["sha256"]["fixed_replay_results.jsonl"] = sha_bytes(files["fixed_replay_results.jsonl"])
    files["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    with pytest.raises(Exception):
        check_zip(_write_pack(tmp_path, files))


def test_changed_frozen_input_and_v3_schema_rejected(tmp_path):
    files = build_records()
    rows = [json.loads(line) for line in files["scenario_inputs.jsonl"].splitlines()]
    rows[0]["scenario"]["scenario_id"] = "mutated"
    rows[0]["scenario_input_sha256"] = "0" * 64
    files["scenario_inputs.jsonl"] = jsonl_bytes(rows)
    manifest = json.loads(files["review_pack_manifest.json"])
    manifest["sha256"]["scenario_inputs.jsonl"] = sha_bytes(files["scenario_inputs.jsonl"])
    files["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    with pytest.raises(Exception):
        check_zip(_write_pack(tmp_path, files))
    files = build_records()
    manifest = json.loads(files["review_pack_manifest.json"])
    manifest["review_pack_schema_version"] = REVIEW_PACK_SCHEMA_VERSION.replace("v4", "v3")
    files["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    with pytest.raises(Exception):
        check_zip(_write_pack(tmp_path, files))


def test_custom_run_id_reconciles_and_no_private_live_telegram():
    files = build_records("custom_run")
    assert b"custom_run" in files["ohlc_replay_run_status.json"]
    assert b"custom_run" in files["review_pack_manifest.json"]
    assert b"run_id: custom_run" in files["ohlc_replay_report.md"]
    blob = b"\n".join(files.values()).lower()
    assert b"telegram" not in blob and b"private" not in blob and b"api_key" not in blob
    assert json.loads(files["review_pack_manifest.json"])["run_id"] == "custom_run"
