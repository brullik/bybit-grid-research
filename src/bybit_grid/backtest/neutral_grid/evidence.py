from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .audit import audit_simulation_result
from .geometry import geometric_grid_levels_decimal
from .models import OrderSide
from .scenarios import SCENARIO_IDS, SCENARIO_VERSION, canonical_scenarios, replay_scenario
from .serialization import (
    CANONICAL_SERIALIZATION_VERSION,
    canonical_json_bytes,
    canonical_sha256,
    normalize,
)

RUN_ID = "neutral_sm_v1_synthetic_v2"
DEFAULT_PACK = "pm_review_pack_state_machine_neutral_sm_v1_synthetic_v2.zip"
STATE_MACHINE_CONTRACT_VERSION = "native_neutral_grid_reference_contract_v1"
REVIEW_PACK_SCHEMA_VERSION = "neutral_grid_state_machine_review_pack_v2"
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

MANIFEST_KEYS = {
    "review_pack_schema_version",
    "manifest_hash_policy",
    "review_phase",
    "run_id",
    "state_machine_contract_version",
    "canonical_serialization_version",
    "scenario_version",
    "canonical_scenario_count",
    "risk_budget_proven_bool",
    "parameter_selection_authorized_bool",
    "live_authorized_bool",
    "members",
    "sha256",
}
JSON_MEMBERS = {
    "state_machine_run_status.json",
    "state_machine_contract_audit.json",
    "scenario_catalog.json",
    "scenario_audit.json",
    "reproducibility_audit.json",
    "review_pack_manifest.json",
}
JSONL_MEMBERS = {
    "scenario_inputs.jsonl",
    "scenario_results.jsonl",
    "ledger_events.jsonl",
    "completed_cycles.jsonl",
}
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


def _no_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError("duplicate_json_key", key=key)
        out[key] = value
    return out


def strict_json_loads(data: bytes | str, *, member: str = "<memory>") -> Any:
    try:
        text = data.decode("utf-8") if isinstance(data, bytes) else data
        return json.loads(text, object_pairs_hook=_no_duplicate_object_pairs)
    except EvidenceError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise EvidenceError("malformed_json", member=member) from e


def strict_jsonl_loads(data: bytes, *, member: str) -> list[dict[str, Any]]:
    text = data.decode("utf-8")
    if text and not text.endswith("\n"):
        raise EvidenceError("noncanonical_jsonl_bytes", member=member)
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line:
            raise EvidenceError("noncanonical_jsonl_bytes", member=member, line=i)
        row = strict_json_loads(line, member=member)
        if not isinstance(row, dict):
            raise EvidenceError("malformed_jsonl", member=member, line=i)
        rows.append(row)
    return rows


def read_json(path: Path) -> Any:
    return strict_json_loads(path.read_bytes(), member=str(path))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return strict_jsonl_loads(path.read_bytes(), member=str(path))


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


def _termination_reason(result: Any) -> str | None:
    if not result.terminated_bool:
        return None
    reason = result.termination.termination_reason
    return None if reason is None else reason.value


def derive_catalog_semantic_flags(results: list[dict[str, Any]] | None = None) -> tuple[dict[str, bool], list[str]]:
    failures: list[str] = []
    scenarios = {s.scenario_id: s for s in canonical_scenarios()}
    exact = scenarios["01_initial_exact_base"]
    exact_levels = geometric_grid_levels_decimal(
        exact.config.lower_price, exact.config.upper_price, exact.config.grid_cell_number
    ).levels
    exact_result = replay_scenario(exact)
    exact_matches = [i for i, level in enumerate(exact_levels) if level == exact.config.base_price]
    exact_orders = [o for o in exact_result.all_orders if o.activation_sequence_id == 0]
    exact_configured = len(exact_matches) == 1 and tuple(exact_result.levels) == tuple(exact_levels)
    exact_no_order = (
        exact_configured
        and exact_matches[0] not in exact_result.active_orders
        and len(exact_orders) == exact.config.grid_cell_number
        and all(
            exact_result.active_orders.get(i) is not None
            and exact_result.active_orders[i].side is OrderSide.buy
            for i, level in enumerate(exact_levels)
            if level < exact.config.base_price
        )
        and all(
            exact_result.active_orders.get(i) is not None
            and exact_result.active_orders[i].side is OrderSide.sell
            for i, level in enumerate(exact_levels)
            if level > exact.config.base_price
        )
    )
    between = scenarios["02_initial_between_levels"]
    between_levels = geometric_grid_levels_decimal(
        between.config.lower_price, between.config.upper_price, between.config.grid_cell_number
    ).levels
    between_result = replay_scenario(between)
    between_configured = (
        between.config.base_price not in between_levels
        and tuple(between_result.levels) == tuple(between_levels)
        and all(
            between_result.active_orders.get(i) is not None
            and between_result.active_orders[i].side is OrderSide.buy
            for i, level in enumerate(between_levels)
            if level < between.config.base_price
        )
        and all(
            between_result.active_orders.get(i) is not None
            and between_result.active_orders[i].side is OrderSide.sell
            for i, level in enumerate(between_levels)
            if level > between.config.base_price
        )
    )
    expected_term = True
    by_id = {r.get("scenario_id"): r for r in (results or [])}
    for s in canonical_scenarios():
        actual = _termination_reason(replay_scenario(s))
        expected = None if s.expected_termination_reason is None else s.expected_termination_reason.value
        if actual != expected:
            expected_term = False
        if by_id:
            stored = by_id.get(s.scenario_id, {}).get("normalized_result", {}).get("termination", {}).get("termination_reason")
            if stored != expected:
                expected_term = False
    low = scenarios["03_low_price_initial"]
    low_ok = tuple(replay_scenario(low).levels) == tuple(
        geometric_grid_levels_decimal(low.config.lower_price, low.config.upper_price, low.config.grid_cell_number).levels
    )
    tight = scenarios["04_tight_high_price_initial"]
    tight_ok = tuple(replay_scenario(tight).levels) == tuple(
        geometric_grid_levels_decimal(tight.config.lower_price, tight.config.upper_price, tight.config.grid_cell_number).levels
    )
    flags = {
        "exact_base_scenario_configured_bool": exact_configured,
        "exact_base_level_has_no_order_bool": exact_no_order,
        "between_level_scenario_configured_bool": between_configured,
        "expected_termination_reasons_match_bool": expected_term,
        "low_price_scenario_preserves_canonical_levels_bool": low_ok,
        "tight_high_price_scenario_preserves_canonical_levels_bool": tight_ok,
    }
    for key, value in flags.items():
        if value is not True:
            failures.append(key.replace("_bool", "_failed"))
    return flags, failures


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
    semantic_flags, semantic_failures = derive_catalog_semantic_flags(results)
    for code in semantic_failures:
        _fail(failures, code)
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
        **semantic_flags,
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


def build_synthetic_scenario_report(scenario_audit: dict[str, Any]) -> bytes:
    keys = [
        "canonical_scenario_count",
        "input_record_count",
        "result_record_count",
        "ledger_event_count",
        "completed_cycle_count",
        "input_event_evidence_complete_bool",
        "all_scenarios_replay_match_bool",
        "all_result_audits_pass_bool",
        "exact_base_scenario_configured_bool",
        "exact_base_level_has_no_order_bool",
        "between_level_scenario_configured_bool",
        "expected_termination_reasons_match_bool",
        "low_price_scenario_preserves_canonical_levels_bool",
        "tight_high_price_scenario_preserves_canonical_levels_bool",
    ]
    lines = ["# Synthetic scenario report", ""]
    lines.extend(f"{k} = {str(scenario_audit[k]).lower()}" for k in keys)
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_risk_budget_readiness_report() -> bytes:
    lines = ["# Risk budget readiness"]
    lines.extend(f"{k} = {str(v).lower()}" for k, v in RISK_REPORT_GUARDRAILS.items())
    return ("\n".join(lines) + "\n").encode("utf-8")


def validate_reports(synthetic: bytes, risk: bytes, scenario_audit: dict[str, Any]) -> None:
    if synthetic != build_synthetic_scenario_report(scenario_audit):
        raise EvidenceError("synthetic_report_bytes_mismatch")
    if risk != build_risk_budget_readiness_report():
        raise EvidenceError("risk_report_bytes_mismatch")

def _require_canonical_json(member: str, data: bytes) -> Any:
    obj = strict_json_loads(data, member=member)
    if data != canonical_json_bytes(obj):
        raise EvidenceError("noncanonical_json_bytes", member=member)
    return obj


def _require_canonical_jsonl(member: str, data: bytes) -> list[dict[str, Any]]:
    rows = strict_jsonl_loads(data, member=member)
    if data != jsonl_bytes(rows):
        raise EvidenceError("noncanonical_jsonl_bytes", member=member)
    return rows


def validate_manifest(manifest_bytes: bytes, data: dict[str, bytes], run_id: str) -> dict[str, Any]:
    man = _require_canonical_json("review_pack_manifest.json", manifest_bytes)
    if not isinstance(man, dict):
        raise EvidenceError("manifest_type_mismatch")
    if set(man) != MANIFEST_KEYS:
        missing = sorted(MANIFEST_KEYS - set(man))
        extra = sorted(set(man) - MANIFEST_KEYS)
        raise EvidenceError("manifest_key_set_mismatch", missing=missing, extra=extra)
    expected = {
        "review_pack_schema_version": REVIEW_PACK_SCHEMA_VERSION,
        "manifest_hash_policy": MANIFEST_HASH_POLICY,
        "review_phase": REVIEW_PHASE,
        "run_id": run_id,
        "state_machine_contract_version": STATE_MACHINE_CONTRACT_VERSION,
        "canonical_serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "scenario_version": SCENARIO_VERSION,
        "canonical_scenario_count": CANONICAL_SCENARIO_COUNT,
        **FALSE_GUARDRAILS,
        "members": MEMBERS,
    }
    for key, value in expected.items():
        if man.get(key) != value:
            raise EvidenceError("manifest_semantics_mismatch", field=key)
    sha = man.get("sha256")
    if not isinstance(sha, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in sha.items()):
        raise EvidenceError("manifest_sha256_type_mismatch")
    if MEMBERS[0] in sha:
        raise EvidenceError("manifest_self_hash_forbidden")
    if set(sha) != set(MEMBERS[1:]):
        raise EvidenceError("hash_key_set_mismatch")
    for member in MEMBERS[1:]:
        if hashlib.sha256(data[member]).hexdigest() != sha[member]:
            raise EvidenceError("hash_mismatch", member=member)
    return man


def validate_artifact_bundle(artifacts: dict[str, bytes], run_id: str) -> dict[str, Any]:
    try:
        status = _require_canonical_json("state_machine_run_status.json", artifacts["state_machine_run_status.json"])
        contract = _require_canonical_json("state_machine_contract_audit.json", artifacts["state_machine_contract_audit.json"])
        catalog = _require_canonical_json("scenario_catalog.json", artifacts["scenario_catalog.json"])
        scen_aud = _require_canonical_json("scenario_audit.json", artifacts["scenario_audit.json"])
        repro = _require_canonical_json("reproducibility_audit.json", artifacts["reproducibility_audit.json"])
        inputs = _require_canonical_jsonl("scenario_inputs.jsonl", artifacts["scenario_inputs.jsonl"])
        results = _require_canonical_jsonl("scenario_results.jsonl", artifacts["scenario_results.jsonl"])
        ledger = _require_canonical_jsonl("ledger_events.jsonl", artifacts["ledger_events.jsonl"])
        cycles = _require_canonical_jsonl("completed_cycles.jsonl", artifacts["completed_cycles.jsonl"])
        synthetic = artifacts["synthetic_scenario_report.md"]
        risk = artifacts["risk_budget_readiness_report.md"]
    except KeyError as e:
        raise EvidenceError("malformed_required_artifact") from e
    if status != {
        "canonical_scenario_count": CANONICAL_SCENARIO_COUNT,
        "completed_scenario_count": CANONICAL_SCENARIO_COUNT,
        "failed_scenario_count": 0,
        "input_record_count": CANONICAL_SCENARIO_COUNT,
        "result_record_count": CANONICAL_SCENARIO_COUNT,
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
    if catalog != {"canonical_scenario_count": CANONICAL_SCENARIO_COUNT, "scenario_ids": list(SCENARIO_IDS), "scenario_version": SCENARIO_VERSION}:
        raise EvidenceError("scenario_catalog_mismatch")
    if any(row.get("scenario", {}).get("scenario_version") != SCENARIO_VERSION for row in inputs):
        raise EvidenceError("scenario_version_mismatch")
    expected_audit = audit_persisted_scenario_evidence(inputs, results, ledger, cycles)
    if scen_aud != expected_audit or not expected_audit["scenario_audit_ok"]:
        raise EvidenceError("scenario_audit_semantics_mismatch", failures=expected_audit["failures"])
    expected_repro = derive_reproducibility_audit({"inputs": inputs, "results": results, "ledger": ledger, "cycles": cycles, "scenario_audit": scen_aud})
    if repro != expected_repro or not expected_repro["reproducibility_audit_ok"]:
        raise EvidenceError("reproducibility_audit_semantics_mismatch")
    validate_reports(synthetic, risk, scen_aud)
    return {"input_records_verified": len(inputs), "result_records_verified": len(results), "ledger_rows_verified": len(ledger), "cycle_rows_verified": len(cycles), "fresh_replay_match_bool": True}

def validate_member_names(names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise EvidenceError("duplicate_member")
    if names != MEMBERS:
        raise EvidenceError("member_order_mismatch")
    for n in names:
        pp = PurePosixPath(n)
        if pp.is_absolute() or ".." in pp.parts or n.endswith("/"):
            raise EvidenceError("forbidden_member_path")
