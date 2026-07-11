from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .audit import audit_simulation_result
from .scenarios import SCENARIO_IDS, canonical_scenarios, replay_scenario
from .serialization import (
    CANONICAL_SERIALIZATION_VERSION,
    canonical_json_bytes,
    canonical_sha256,
    normalize,
)

RUN_ID = "neutral_sm_v1_synthetic"
STATE_MACHINE_CONTRACT_VERSION = "native_neutral_grid_reference_contract_v1"
REVIEW_PACK_SCHEMA_VERSION = "neutral_grid_state_machine_review_pack_v1"
MANIFEST_HASH_POLICY = "self_excluded_v1"
REVIEW_PHASE = "synthetic_state_machine_evidence_complete"
CANONICAL_SCENARIO_COUNT = 33
RUN_STATUS_SCHEMA_VERSION = "neutral_grid_state_machine_run_status_v1"
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
FALSE_GUARDRAILS = {
    "risk_budget_proven_bool": False,
    "parameter_selection_authorized_bool": False,
    "live_authorized_bool": False,
}
RISK_REPORT_GUARDRAILS = {
    "native_equivalence_proven_bool": False,
    "native_quantity_mapping_proven_bool": False,
    "native_termination_mapping_proven_bool": False,
    "liquidation_modeled_bool": False,
    "ohlc_replay_supported_bool": False,
    "risk_budget_proven_bool": False,
    "sufficient_for_parameter_selection_bool": False,
    "profitability_claims_present_bool": False,
    "live_execution_present_bool": False,
    "sufficient_for_ohlc_replay_engineering_bool": True,
}
CONTRACT_AUDIT = {
    "contract_audit_ok": True,
    "canonical_geometry_exact_bool": True,
    "sequence_zero_reserved_bool": True,
    "active_order_bijection_enforced_bool": True,
    "linked_fill_provenance_enforced_bool": True,
    "cycle_provenance_enforced_bool": True,
    "termination_contract_enforced_bool": True,
    "audit_fail_closed_bool": True,
    "no_live_execution_bool": True,
}


class EvidenceError(ValueError):
    def __init__(self, error: str, **extra: Any):
        super().__init__(error)
        self.error = error
        self.extra = extra


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(r) for r in rows)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise EvidenceError("malformed_jsonl", path=str(path), line=i) from e
        if not isinstance(row, dict):
            raise EvidenceError("malformed_jsonl", path=str(path), line=i)
        rows.append(row)
    return rows


def scenario_input_record(s: Any) -> dict[str, Any]:
    rec = normalize(s)
    return {
        "scenario_id": s.scenario_id,
        "scenario_input_sha256": canonical_sha256(rec),
        "scenario": rec,
    }


def build_evidence_records() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]
]:
    inputs: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    cycles: list[dict[str, Any]] = []
    for s in canonical_scenarios():
        inputs.append(scenario_input_record(s))
        r = replay_scenario(s)
        nr = normalize(r)
        results.append(
            {
                "scenario_id": s.scenario_id,
                "scenario_input_sha256": inputs[-1]["scenario_input_sha256"],
                "result_sha256": canonical_sha256(nr),
                "result_audit_passed_bool": True,
                "normalized_result": nr,
            }
        )
        ledger.extend({"scenario_id": s.scenario_id, **normalize(e)} for e in r.ledger)
        cycles.extend({"scenario_id": s.scenario_id, **normalize(c)} for c in r.completed_cycles)
    return inputs, results, ledger, cycles


def _fail(failures: list[str], code: str) -> None:
    if code not in failures:
        failures.append(code)


def audit_persisted_scenario_evidence(
    inputs: list[dict[str, Any]] | None,
    results: list[dict[str, Any]] | None,
    ledger: list[dict[str, Any]] | None,
    cycles: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    failures: list[str] = []
    inputs = inputs or []
    results = results or []
    ledger = ledger or []
    cycles = cycles or []
    exp_inputs, exp_results, exp_ledger, exp_cycles = build_evidence_records()
    exp_ids = list(SCENARIO_IDS)
    ids = [r.get("scenario_id") for r in inputs]
    rids = [r.get("scenario_id") for r in results]
    if ids != exp_ids:
        _fail(failures, "input_scenario_order_mismatch")
    if rids != exp_ids:
        _fail(failures, "result_scenario_order_mismatch")
    if len(set(ids)) != len(ids):
        _fail(failures, "duplicate_input_scenario_id")
    if len(set(rids)) != len(rids):
        _fail(failures, "duplicate_result_scenario_id")
    input_ok = inputs == exp_inputs
    if not input_ok:
        _fail(failures, "input_records_mismatch")
    result_hashes_match = True
    replay_match = True
    audits_pass = True
    if len(results) != CANONICAL_SCENARIO_COUNT:
        _fail(failures, "result_record_count_mismatch")
    for row, exp in zip(results, exp_results, strict=False):
        if row.get("result_sha256") != canonical_sha256(row.get("normalized_result")):
            result_hashes_match = False
        if row != exp:
            replay_match = False
        if row.get("result_audit_passed_bool") is not True:
            audits_pass = False
    if not result_hashes_match:
        _fail(failures, "result_hash_mismatch")
    if not replay_match:
        _fail(failures, "stored_result_replay_mismatch")
    if not audits_pass:
        _fail(failures, "result_audit_not_passed")
    ledger_match = ledger == exp_ledger
    cycle_match = cycles == exp_cycles
    if not ledger_match:
        _fail(failures, "ledger_rows_replay_mismatch")
    if not cycle_match:
        _fail(failures, "cycle_rows_replay_mismatch")
    ledger_unique = True
    order_unique = True
    cycle_unique = True
    term_flat = True
    nonterm_empty = True
    for s in canonical_scenarios():
        r = replay_scenario(s)
        ledger_unique &= len({e.ledger_event_id for e in r.ledger}) == len(r.ledger)
        order_unique &= len({o.order_id for o in r.all_orders}) == len(r.all_orders)
        cycle_unique &= len({c.cycle_id for c in r.completed_cycles}) == len(r.completed_cycles)
        term_flat &= (not r.terminated_bool) or (r.signed_position == 0 and r.average_entry is None)
        nonterm_empty &= r.terminated_bool or normalize(r.termination) == normalize(
            r.termination.__class__()
        )
        audits_pass &= audit_simulation_result(r).passed_bool
    hashes = [r.get("scenario_input_sha256") for r in inputs]
    out = {
        "scenario_audit_ok": False,
        "failures": failures,
        "canonical_scenario_count": CANONICAL_SCENARIO_COUNT,
        "input_record_count": len(inputs),
        "result_record_count": len(results),
        "ledger_event_count": len(ledger),
        "completed_cycle_count": len(cycles),
        "all_scenarios_replay_match_bool": replay_match and bool(results),
        "all_result_audits_pass_bool": audits_pass and bool(results),
        "input_event_evidence_complete_bool": input_ok,
        "scenario_ids_unique_bool": len(ids) == len(set(ids)) and ids == exp_ids,
        "scenario_input_hashes_unique_bool": len(hashes) == len(set(hashes))
        and len(hashes) == CANONICAL_SCENARIO_COUNT,
        "result_hashes_match_bool": result_hashes_match
        and len(results) == CANONICAL_SCENARIO_COUNT,
        "ledger_rows_match_replay_bool": ledger_match,
        "cycle_rows_match_replay_bool": cycle_match,
        "ledger_ids_unique_within_scenario_bool": ledger_unique,
        "order_ids_unique_within_scenario_bool": order_unique,
        "cycle_ids_unique_within_scenario_bool": cycle_unique,
        "all_terminated_scenarios_flat_bool": term_flat,
        "all_nonterminated_scenarios_have_empty_termination_summary_bool": nonterm_empty,
    }
    out["scenario_audit_ok"] = (
        not failures
        and all(v is True for k, v in out.items() if k.endswith("_bool"))
        and len(inputs) == 33
        and len(results) == 33
    )
    return out


_PROHIBITED_MACHINE = {"hostname", "host", "cwd", "path", "python_executable", "executable"}
_PROHIBITED_WALL = {"generated_at", "created_at", "current_time", "timestamp", "wall_clock"}


def _scan(obj: Any) -> tuple[bool, bool]:
    machine = wall = False
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if lk != "time_ms" and lk in _PROHIBITED_MACHINE:
                machine = True
            if lk != "time_ms" and lk in _PROHIBITED_WALL:
                wall = True
            m, w = _scan(v)
            machine |= m
            wall |= w
    elif isinstance(obj, list):
        for v in obj:
            m, w = _scan(v)
            machine |= m
            wall |= w
    elif isinstance(obj, str):
        if "/workspace" in obj or "\\" in obj:
            machine = True
    return machine, wall


def derive_reproducibility_audit(evidence: Any) -> dict[str, Any]:
    a = [canonical_json_bytes(scenario_input_record(s)) for s in canonical_scenarios()]
    b = [canonical_json_bytes(scenario_input_record(s)) for s in canonical_scenarios()]
    machine, wall = _scan(normalize(evidence))
    out = {
        "reproducibility_audit_ok": False,
        "canonical_serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "same_inputs_same_bytes_bool": a == b,
        "same_inputs_same_hashes_bool": [hashlib.sha256(x).hexdigest() for x in a]
        == [hashlib.sha256(x).hexdigest() for x in b],
        "machine_specific_fields_present_bool": machine,
        "wall_clock_fields_present_bool": wall,
    }
    out["reproducibility_audit_ok"] = (
        out["same_inputs_same_bytes_bool"]
        and out["same_inputs_same_hashes_bool"]
        and not machine
        and not wall
    )
    return out


def validate_reports(synthetic: str, risk: str) -> None:
    for text in [
        "canonical_scenario_count = 33",
        "input_event_evidence_complete_bool = true",
        "all_scenarios_replay_match_bool = true",
        "all_result_audits_pass_bool = true",
    ]:
        if text not in synthetic:
            raise EvidenceError("synthetic_report_guardrail_missing", text=text)
    for k, v in RISK_REPORT_GUARDRAILS.items():
        text = f"{k} = {str(v).lower()}"
        if text not in risk:
            raise EvidenceError("risk_report_guardrail_missing", text=text)


def validate_artifact_bundle(artifacts: dict[str, bytes], run_id: str) -> dict[str, Any]:
    try:
        status = json.loads(artifacts["state_machine_run_status.json"])
        contract = json.loads(artifacts["state_machine_contract_audit.json"])
        catalog = json.loads(artifacts["scenario_catalog.json"])
        scen_aud = json.loads(artifacts["scenario_audit.json"])
        repro = json.loads(artifacts["reproducibility_audit.json"])
        inputs = [
            json.loads(line)
            for line in artifacts["scenario_inputs.jsonl"].decode("utf-8").splitlines()
            if line
        ]
        results = [
            json.loads(line)
            for line in artifacts["scenario_results.jsonl"].decode("utf-8").splitlines()
            if line
        ]
        ledger = [
            json.loads(line)
            for line in artifacts["ledger_events.jsonl"].decode("utf-8").splitlines()
            if line
        ]
        cycles = [
            json.loads(line)
            for line in artifacts["completed_cycles.jsonl"].decode("utf-8").splitlines()
            if line
        ]
        synthetic = artifacts["synthetic_scenario_report.md"].decode("utf-8")
        risk = artifacts["risk_budget_readiness_report.md"].decode("utf-8")
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise EvidenceError("malformed_required_artifact") from e
    if status != {
        "canonical_scenario_count": 33,
        "completed_scenario_count": 33,
        "failed_scenario_count": 0,
        "input_record_count": 33,
        "result_record_count": 33,
        "ledger_event_count": len(ledger),
        "completed_cycle_count": len(cycles),
        "run_id": run_id,
        "schema_version": RUN_STATUS_SCHEMA_VERSION,
        "state_machine_contract_version": STATE_MACHINE_CONTRACT_VERSION,
        "status": "complete",
    }:
        raise EvidenceError("status_semantics_mismatch")
    if contract != CONTRACT_AUDIT:
        raise EvidenceError("contract_audit_semantics_mismatch")
    if catalog != {"canonical_scenario_count": 33, "scenario_ids": list(SCENARIO_IDS)}:
        raise EvidenceError("scenario_catalog_mismatch")
    expected_audit = audit_persisted_scenario_evidence(inputs, results, ledger, cycles)
    if scen_aud != expected_audit or not expected_audit["scenario_audit_ok"]:
        raise EvidenceError(
            "scenario_audit_semantics_mismatch", failures=expected_audit["failures"]
        )
    expected_repro = derive_reproducibility_audit(
        {
            "inputs": inputs,
            "results": results,
            "ledger": ledger,
            "cycles": cycles,
            "scenario_audit": scen_aud,
        }
    )
    if repro != expected_repro or not expected_repro["reproducibility_audit_ok"]:
        raise EvidenceError("reproducibility_audit_semantics_mismatch")
    validate_reports(synthetic, risk)
    return {
        "input_records_verified": len(inputs),
        "result_records_verified": len(results),
        "ledger_rows_verified": len(ledger),
        "cycle_rows_verified": len(cycles),
        "fresh_replay_match_bool": True,
    }


def validate_member_names(names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise EvidenceError("duplicate_member")
    if names != MEMBERS:
        raise EvidenceError("member_order_mismatch")
    for n in names:
        pp = PurePosixPath(n)
        if pp.is_absolute() or ".." in pp.parts or n.endswith("/"):
            raise EvidenceError("forbidden_member_path")
