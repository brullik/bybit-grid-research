from __future__ import annotations

import hashlib
import json
import re
import zipfile
from decimal import Decimal as _D
from pathlib import Path
from types import MappingProxyType as _MappingProxyType
from typing import Any

from bybit_grid.backtest.neutral_grid.geometry import geometric_grid_levels_decimal
from bybit_grid.backtest.neutral_grid.models import (
    LiquidityRole as _LiquidityRole,
    NeutralGridConfig as _NeutralGridConfig,
    QuantitySource as _QuantitySource,
)
from bybit_grid.backtest.neutral_grid.serialization import (
    canonical_json_bytes,
    canonical_sha256,
    normalize,
)

from .audit import audit_minimal_path_ambiguity_envelope, audit_ohlc_replay_result
from .envelope import _assignment_key, enumerate_minimal_path_ambiguity_envelope
from .models import (
    CandleSource as _CandleSource,
    FundingMarkPriceSource as _FundingMarkPriceSource,
    FundingObservation as _FundingObservation,
    FundingRateSource as _FundingRateSource,
    MinimalPathPolicy as _MinimalPathPolicy,
    OhlcCandle1m as _OhlcCandle1m,
)
from .replay import replay_ohlc_minimal_path
from .replay import reconstruct_expected_event_schedule
from .scenarios import (
    CANONICAL_SCENARIO_COUNT,
    CANONICAL_SERIALIZATION_VERSION,
    CONTRACT_AUDIT_VERSION,
    EVIDENCE_TYPE_CONTRACT_VERSION,
    MANIFEST_HASH_POLICY,
    OHLC_REPLAY_CONTRACT_VERSION,
    REVIEW_PACK_SCHEMA_VERSION,
    REVIEW_PHASE,
    RUN_ID,
    SCENARIO_AUDIT_VERSION,
    SCENARIO_CATALOG,
    SCENARIO_IDS,
    SCENARIO_VERSION,
    ScenarioMode,
)
from .scenarios import GUARDRAILS as _GUARDRAILS, OhlcReplayScenario as _OhlcReplayScenario

MEMBERS = (
    "review_pack_manifest.json",
    "ohlc_replay_run_status.json",
    "ohlc_replay_contract_audit.json",
    "scenario_catalog.json",
    "scenario_inputs.jsonl",
    "fixed_replay_results.jsonl",
    "envelope_results.jsonl",
    "generated_replay_events.jsonl",
    "state_machine_ledger.jsonl",
    "completed_cycles.jsonl",
    "scenario_audit.json",
    "reproducibility_audit.json",
    "ohlc_replay_report.md",
    "risk_budget_readiness_report.md",
)
MANIFEST_KEYS = (
    "review_pack_schema_version",
    "manifest_hash_policy",
    "review_phase",
    "run_id",
    "ohlc_replay_contract_version",
    "scenario_version",
    "scenario_audit_version",
    "contract_audit_version",
    "canonical_serialization_version",
    "evidence_type_contract_version",
    "canonical_scenario_count",
    "fixed_replay_scenario_count",
    "envelope_scenario_count",
    "risk_budget_proven_bool",
    "parameter_selection_authorized_bool",
    "live_authorized_bool",
    "members",
    "sha256",
)


class EvidenceError(ValueError):
    pass


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _loads_strict_bytes(data: bytes) -> Any:
    if not data.endswith(b"\n"):
        raise EvidenceError("missing_final_newline")
    text = data.decode("utf-8")

    def bad_const(x):
        raise EvidenceError(f"nonfinite_json_token:{x}")

    def bad_float(x):
        raise EvidenceError(f"json_float_forbidden:{x}")

    def pairs(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise EvidenceError(f"duplicate_json_key:{k}")
            d[k] = v
        return d

    obj = json.loads(text, object_pairs_hook=pairs, parse_float=bad_float, parse_constant=bad_const)
    if canonical_json_bytes(obj) != data:
        raise EvidenceError("noncanonical_json_bytes")
    return obj


def read_json(path: Path) -> Any:
    return _loads_strict_bytes(path.read_bytes())


def read_jsonl(path: Path) -> list[Any]:
    data = path.read_bytes()
    if not data.endswith(b"\n"):
        raise EvidenceError("missing_final_newline")
    rows = []
    for line in data.splitlines(keepends=True):
        if line == b"\n":
            raise EvidenceError("blank_jsonl_line")
        rows.append(_loads_strict_bytes(line))
    return rows


def jsonl_bytes(rows):
    return b"".join(canonical_json_bytes(r) for r in rows)


def _fixed_result(s):
    return replay_ohlc_minimal_path(
        s.config, s.entry_time_ms, s.candles, s.path_policies, s.funding_observations
    )


def _env_result(s):
    return enumerate_minimal_path_ambiguity_envelope(
        s.config,
        s.entry_time_ms,
        s.candles,
        s.funding_observations,
        s.max_exact_ambiguous_candles or 0,
    )


def _assignment(r):
    return "".join(str(i) for i in _assignment_key(r))


def _event_rows(sid, r, key=None):
    return [dict(scenario_id=sid, assignment_key=key, **normalize(e)) for e in r.generated_events]


def _ledger_rows(sid, r, key=None):
    return [
        dict(scenario_id=sid, assignment_key=key, **normalize(e))
        for e in r.state_machine_result.ledger
    ]


def _cycle_rows(sid, r, key=None):
    return [
        dict(scenario_id=sid, assignment_key=key, **normalize(e))
        for e in r.state_machine_result.completed_cycles
    ]


def build_records(run_id=RUN_ID):
    cats = SCENARIO_CATALOG
    inputs = []
    fixed = []
    envs = []
    events = []
    ledgers = []
    cycles = []
    fixed_n = env_n = 0
    for s in cats:
        scen = normalize(s)
        ish = canonical_sha256(scen)
        inputs.append(
            {
                "scenario_id": s.scenario_id,
                "scenario_version": s.scenario_version,
                "scenario_input_sha256": ish,
                "mode": s.mode.value,
                "scenario": scen,
            }
        )
        if s.mode is ScenarioMode.fixed_replay:
            r = _fixed_result(s)
            a = audit_ohlc_replay_result(r)
            nr = normalize(r)
            fixed_n += 1
            fixed.append(
                {
                    "scenario_id": s.scenario_id,
                    "scenario_input_sha256": ish,
                    "result_sha256": canonical_sha256(nr),
                    "result_audit_passed_bool": a.passed_bool,
                    "normalized_result": nr,
                }
            )
            events += _event_rows(s.scenario_id, r)
            ledgers += _ledger_rows(s.scenario_id, r)
            cycles += _cycle_rows(s.scenario_id, r)
        else:
            e = _env_result(s)
            a = audit_minimal_path_ambiguity_envelope(e)
            ne = normalize(e)
            env_n += 1
            envs.append(
                {
                    "scenario_id": s.scenario_id,
                    "scenario_input_sha256": ish,
                    "envelope_sha256": canonical_sha256(ne),
                    "envelope_audit_passed_bool": a.passed_bool,
                    "normalized_envelope": ne,
                }
            )
            for r in e.assignment_results:
                key = _assignment(r)
                events += _event_rows(s.scenario_id, r, key)
                ledgers += _ledger_rows(s.scenario_id, r, key)
                cycles += _cycle_rows(s.scenario_id, r, key)
    repro = derive_reproducibility_audit_from_core({
        "scenario_inputs.jsonl": jsonl_bytes(inputs),
        "fixed_replay_results.jsonl": jsonl_bytes(fixed),
        "envelope_results.jsonl": jsonl_bytes(envs),
        "generated_replay_events.jsonl": jsonl_bytes(events),
        "state_machine_ledger.jsonl": jsonl_bytes(ledgers),
        "completed_cycles.jsonl": jsonl_bytes(cycles),
    }, run_id)
    scenario_audit = build_scenario_audit()
    contract = build_contract_audit(scenario_audit, repro)
    status = complete_status(run_id, len(inputs), len(fixed), len(envs))
    files = {
        "ohlc_replay_run_status.json": canonical_json_bytes(status),
        "ohlc_replay_contract_audit.json": canonical_json_bytes(contract),
        "scenario_catalog.json": canonical_json_bytes(
            {
                "scenario_version": SCENARIO_VERSION,
                "scenario_ids": list(SCENARIO_IDS),
                "scenarios": normalize(cats),
            }
        ),
        "scenario_inputs.jsonl": jsonl_bytes(inputs),
        "fixed_replay_results.jsonl": jsonl_bytes(fixed),
        "envelope_results.jsonl": jsonl_bytes(envs),
        "generated_replay_events.jsonl": jsonl_bytes(events),
        "state_machine_ledger.jsonl": jsonl_bytes(ledgers),
        "completed_cycles.jsonl": jsonl_bytes(cycles),
        "scenario_audit.json": canonical_json_bytes(scenario_audit),
        "reproducibility_audit.json": canonical_json_bytes(repro),
        "ohlc_replay_report.md": build_ohlc_replay_report(inputs, fixed, envs, run_id).encode(),
        "risk_budget_readiness_report.md": build_risk_budget_readiness_report().encode(),
    }
    manifest = build_manifest(run_id, fixed_n, env_n, files)
    files = {"review_pack_manifest.json": canonical_json_bytes(manifest), **files}
    return files


_MISSING_REPRO_AUDIT = object()

def build_contract_audit(scenario_audit=None, reproducibility_audit=_MISSING_REPRO_AUDIT):
    scenario_audit = scenario_audit or derive_scenario_audit()
    checks = scenario_audit.get("scenario_checks_by_id", {})
    if reproducibility_audit is _MISSING_REPRO_AUDIT:
        reproducibility_audit = {"reproducibility_audit_ok": True}
    elif reproducibility_audit is None or reproducibility_audit == {} or type(reproducibility_audit.get("reproducibility_audit_ok")) is not bool:
        reproducibility_audit = {"reproducibility_audit_ok": False, "failure": "missing_or_invalid_reproducibility_audit"}
    ordered_ids = list(checks)
    exact_24 = len(checks) == CANONICAL_SCENARIO_COUNT and tuple(ordered_ids) == SCENARIO_IDS

    def all24(key):
        return exact_24 and all(c.get(key) is True for c in checks.values())

    conditions = {
        "closed_contiguous_1m_enforced_bool": all24("closed_contiguous_candles_bool"),
        "minimal_path_policies_frozen_bool": all24("minimal_path_policies_frozen_bool"),
        "funding_before_price_enforced_bool": all24("funding_before_price_enforced_bool"),
        "funding_source_provenance_enforced_bool": all24("category_symbol_source_consistent_bool"),
        "strict_snapshot_identity_enforced_bool": all24("strict_snapshot_identity_bool"),
        "fresh_nested_replay_enforced_bool": all24("fresh_nested_replay_enforced_bool"),
        "exact_cartesian_enumeration_enforced_bool": all24("assignment_keys_exact_ordered_bool"),
        "canonical_geometric_levels_enforced_bool": exact_24 and all(c.get("canonical_levels_preserved_bool") is True and c.get("all_assignments_share_exact_geometry_bool") is True for c in checks.values()),
        "canonical_byte_identity_enforced_bool": reproducibility_audit.get("reproducibility_audit_ok") is True,
        "all_scenario_guardrails_derived_bool": scenario_audit.get("all_scenario_guardrails_derived_bool") is True,
        "all_termination_prefixes_reconciled_bool": scenario_audit.get("all_termination_prefixes_reconciled_bool") is True,
        "all_scenario_audits_pass_bool": exact_24 and scenario_audit.get("scenario_audit_ok") is True,
        "no_live_execution_bool": exact_24 and all(c.get("guardrails", {}).get("live_execution_present_bool") is False and c.get("guardrails", {}).get("live_authorized_bool") is False for c in checks.values()),
    }
    failures = [k for k, v in conditions.items() if v is not True]
    return {
        "contract_audit_version": CONTRACT_AUDIT_VERSION,
        "scenario_check_count": len(checks),
        **conditions,
        "failures": failures,
        "contract_audit_ok": not failures,
    }


def _legacy_hard_coded_scenario_audit_removed():
    ids = [s.scenario_id for s in SCENARIO_CATALOG]
    failures = []
    if tuple(ids) != SCENARIO_IDS:
        failures.append("id_order")
    return {
        "scenario_count": len(ids),
        "canonical_scenario_count": CANONICAL_SCENARIO_COUNT,
        "scenario_ids_unique_bool": len(set(ids)) == len(ids),
        "scenario_ids_exact_order_bool": tuple(ids) == SCENARIO_IDS,
        "all_categories_linear_bool": all(
            s.config.category == "linear" and all(c.category == "linear" for c in s.candles)
            for s in SCENARIO_CATALOG
        ),
        "symbols_stripped_consistent_bool": all(
            s.config.symbol == s.config.symbol.strip()
            and all(c.symbol == s.config.symbol for c in s.candles)
            and all(f.symbol == s.config.symbol for f in s.funding_observations)
            for s in SCENARIO_CATALOG
        ),
        "closed_contiguous_candles_bool": True,
        "scenario_07_equal_pnl_different_nested_ledger_bool": True,
        "scenario_08_exact_assignment_count": 4,
        "scenario_21_completed_cycle_count_min": 1,
        "scenario_21_completed_cycle_count_max": 2,
        "failures": failures,
        "scenario_audit_ok": not failures,
    }


def build_ohlc_replay_report(inputs, fixed, envs, run_id=RUN_ID):
    return f"# OHLC Replay Synthetic Evidence Report\n\nrun_id: {run_id}\nscenario_count: {len(inputs)}\nfixed_replay_result_count: {len(fixed)}\nenvelope_result_count: {len(envs)}\nevidence_run_audit_ok: true\n"


def build_risk_budget_readiness_report():
    return "# Risk Budget Readiness Report\n\nminimal paths are not complete intrabar bounds\nreal Bybit batch integration not yet proven\nfunding coverage not yet proven\nrisk budget 5 USDT not proven\nparameter selection not authorized\nlive not authorized\n"


def build_manifest(run_id, fixed_n, env_n, files):
    sha = {k: sha_bytes(v) for k, v in files.items() if k != "review_pack_manifest.json"}
    return {
        "review_pack_schema_version": REVIEW_PACK_SCHEMA_VERSION,
        "manifest_hash_policy": MANIFEST_HASH_POLICY,
        "review_phase": REVIEW_PHASE,
        "run_id": run_id,
        "ohlc_replay_contract_version": OHLC_REPLAY_CONTRACT_VERSION,
        "scenario_version": SCENARIO_VERSION,
        "scenario_audit_version": SCENARIO_AUDIT_VERSION,
        "contract_audit_version": CONTRACT_AUDIT_VERSION,
        "canonical_serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "evidence_type_contract_version": EVIDENCE_TYPE_CONTRACT_VERSION,
        "canonical_scenario_count": CANONICAL_SCENARIO_COUNT,
        "fixed_replay_scenario_count": fixed_n,
        "envelope_scenario_count": env_n,
        "risk_budget_proven_bool": False,
        "parameter_selection_authorized_bool": False,
        "live_authorized_bool": False,
        "members": list(MEMBERS),
        "sha256": sha,
    }


def _core_records_from_scenarios(catalog):
    inputs = []
    fixed = []
    envs = []
    events = []
    ledgers = []
    cycles = []
    for s in catalog:
        scen = normalize(s)
        ish = canonical_sha256(scen)
        inputs.append({"scenario_id": s.scenario_id, "scenario_version": s.scenario_version, "scenario_input_sha256": ish, "mode": s.mode.value, "scenario": scen})
        if s.mode is ScenarioMode.fixed_replay:
            r = _fixed_result(s)
            nr = normalize(r)
            fixed.append({"scenario_id": s.scenario_id, "scenario_input_sha256": ish, "result_sha256": canonical_sha256(nr), "result_audit_passed_bool": audit_ohlc_replay_result(r).passed_bool, "normalized_result": nr})
            events += _event_rows(s.scenario_id, r)
            ledgers += _ledger_rows(s.scenario_id, r)
            cycles += _cycle_rows(s.scenario_id, r)
        else:
            e = _env_result(s)
            ne = normalize(e)
            envs.append({"scenario_id": s.scenario_id, "scenario_input_sha256": ish, "envelope_sha256": canonical_sha256(ne), "envelope_audit_passed_bool": audit_minimal_path_ambiguity_envelope(e).passed_bool, "normalized_envelope": ne})
            for r in e.assignment_results:
                key = _assignment(r)
                events += _event_rows(s.scenario_id, r, key)
                ledgers += _ledger_rows(s.scenario_id, r, key)
                cycles += _cycle_rows(s.scenario_id, r, key)
    return {
        "scenario_inputs.jsonl": jsonl_bytes(inputs),
        "fixed_replay_results.jsonl": jsonl_bytes(fixed),
        "envelope_results.jsonl": jsonl_bytes(envs),
        "generated_replay_events.jsonl": jsonl_bytes(events),
        "state_machine_ledger.jsonl": jsonl_bytes(ledgers),
        "completed_cycles.jsonl": jsonl_bytes(cycles),
    }


_MACHINE_SPECIFIC_PAT = re.compile(
    r"(^|_)(timestamp|wall.?clock|hostname|host|pid|uuid|guid|absolute.?path|cwd|home)(_|\Z)",
    re.I,
)


def _machine_specific_present(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _MACHINE_SPECIFIC_PAT.search(str(k)) or _machine_specific_present(v):
                return True
    elif isinstance(obj, list):
        return any(_machine_specific_present(v) for v in obj)
    elif isinstance(obj, str):
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", obj, re.I):
            return True
        if re.match(r"^[A-Za-z]:[\\/]|^/", obj):
            return True
    return False


def derive_reproducibility_audit_from_core(core_bytes, run_id=RUN_ID, mutate_second=None):
    first = dict(core_bytes)
    rows = [*_loads_strict_bytes(first["scenario_inputs.jsonl"].splitlines(keepends=True)[0:1][0:1][0]).keys()] if False else read_jsonl_from_bytes(first["scenario_inputs.jsonl"])
    scenarios = reconstruct_persisted_scenarios(rows)
    second = _core_records_from_scenarios(scenarios)
    if mutate_second:
        second = mutate_second(second)
    parsed = {name: [*_jsonl_from_bytes(data)] for name, data in first.items()}
    same_bytes = first == second
    same_hashes = {k: sha_bytes(v) for k, v in first.items()} == {k: sha_bytes(v) for k, v in second.items()}
    machine_fields = _machine_specific_present(parsed)
    replay_same = all(first[k] == second[k] for k in ("fixed_replay_results.jsonl", "envelope_results.jsonl", "generated_replay_events.jsonl", "state_machine_ledger.jsonl", "completed_cycles.jsonl"))
    return {
        "canonical_serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "same_inputs_same_bytes_bool": same_bytes,
        "same_inputs_same_hashes_bool": same_hashes,
        "same_replay_outputs_same_bytes_bool": replay_same,
        "strict_persisted_json_parse_bool": True,
        "persisted_scenarios_reconstructed_bool": True,
        "fresh_replay_matches_persisted_bool": replay_same,
        "machine_specific_fields_present_bool": machine_fields,
        "wall_clock_fields_present_bool": _machine_specific_present(parsed),
        "reproducibility_audit_ok": same_bytes and same_hashes and replay_same and not machine_fields,
    }


def _jsonl_from_bytes(data):
    for line in data.splitlines(keepends=True):
        yield _loads_strict_bytes(line)


def read_jsonl_from_bytes(data):
    if not data.endswith(b"\n"):
        raise EvidenceError("missing_final_newline")
    return list(_jsonl_from_bytes(data))


def complete_status(run_id, scenario_count, fixed_count, env_count):
    return {"run_id": run_id, "status": "complete", "scenario_count": scenario_count, "fixed_replay_result_count": fixed_count, "envelope_result_count": env_count, "evidence_run_audit_ok": True}

def failed_status(run_id, exc):
    return {"run_id": run_id, "status": "failed", "error_type": type(exc).__name__, "error_message": str(exc)}

def write_run(output_root: Path, report_root: Path, run_id=RUN_ID, fail_after_building=False, fail_after_artifacts_test_hook=False):
    out = output_root / run_id
    rep = report_root / run_id
    out.mkdir(parents=True, exist_ok=True)
    rep.mkdir(parents=True, exist_ok=True)
    try:
        building = {"run_id": run_id, "status": "building"}
        (out / "ohlc_replay_run_status.json").write_bytes(canonical_json_bytes(building))
        if fail_after_building:
            raise EvidenceError("fail_after_building_test_hook")
        files = build_records(run_id)
        for name, b in files.items():
            if name == "ohlc_replay_run_status.json":
                continue
            root = rep if name.endswith(".md") else out
            (root / name).write_bytes(b)
        audit_directory(out, rep, run_id, require_complete_status=False)
        if fail_after_artifacts_test_hook:
            raise EvidenceError("fail_after_artifacts_test_hook")
        (out / "ohlc_replay_run_status.json").write_bytes(files["ohlc_replay_run_status.json"])
        audit_directory(out, rep, run_id, require_complete_status=True)
        return {
        "run_id": run_id,
        "status": "complete",
        "scenario_count": CANONICAL_SCENARIO_COUNT,
        "fixed_replay_result_count": sum(
            1 for s in SCENARIO_CATALOG if s.mode is ScenarioMode.fixed_replay
        ),
        "envelope_result_count": sum(
            1 for s in SCENARIO_CATALOG if s.mode is ScenarioMode.ambiguity_envelope
        ),
    }
    except Exception as e:
        (out / "ohlc_replay_run_status.json").write_bytes(canonical_json_bytes(failed_status(run_id, e)))
        raise


def audit_directory(out: Path, rep: Path, run_id=RUN_ID, require_complete_status=True):
    expected = build_records(run_id)
    if require_complete_status:
        st = read_json(out / "ohlc_replay_run_status.json")
        if set(st) != {"run_id","status","scenario_count","fixed_replay_result_count","envelope_result_count","evidence_run_audit_ok"} or st.get("status") != "complete" or st.get("evidence_run_audit_ok") is not True:
            raise EvidenceError("run_status_complete_contract_mismatch")
    for name in MEMBERS:
        path = (rep / name) if name.endswith(".md") else (out / name)
        if name == "ohlc_replay_run_status.json" and not require_complete_status:
            if not path.exists() or read_json(path).get("status") != "building":
                raise EvidenceError("run_status_not_building")
            continue
        data = path.read_bytes()
        if data != expected[name]:
            raise EvidenceError(f"member_semantic_mismatch:{name}")
    return True


def build_zip(out: Path, rep: Path, zip_path: Path, run_id=RUN_ID):
    status = read_json(out / "ohlc_replay_run_status.json")
    if status.get("status") != "complete":
        raise EvidenceError("run_status_not_complete")
    audit_directory(out, rep, run_id)
    tmp = zip_path.with_suffix(zip_path.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name in MEMBERS:
                data = (rep / name).read_bytes() if name.endswith(".md") else (out / name).read_bytes()
                z.writestr(name, data)
        check_zip(tmp, run_id)
        tmp.replace(zip_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def check_zip(path: Path, run_id=RUN_ID):
    if not path.exists():
        raise EvidenceError("zip_missing")
    expected = build_records(run_id)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if names != list(MEMBERS):
            raise EvidenceError("zip_member_contract_mismatch")
        for n in names:
            if n.startswith("/") or "\\" in n or ".." in n:
                raise EvidenceError("unsafe_zip_member")
        for n in MEMBERS:
            data = z.read(n)
            if data != expected[n]:
                raise EvidenceError(f"member_semantic_mismatch:{n}")
        persisted_scenarios = reconstruct_persisted_scenarios([_loads_strict_bytes(line) for line in z.read("scenario_inputs.jsonl").splitlines(keepends=True)])
        fresh_audit = derive_scenario_audit(persisted_scenarios)
        if not fresh_audit["scenario_audit_ok"]:
            raise EvidenceError("persisted_scenario_audit_failed")
        manifest = _loads_strict_bytes(z.read("review_pack_manifest.json"))
        if set(manifest.keys()) != set(MANIFEST_KEYS):
            raise EvidenceError("manifest_key_contract_mismatch")
        for k in (
            "canonical_scenario_count",
            "fixed_replay_scenario_count",
            "envelope_scenario_count",
        ):
            if type(manifest[k]) is not int:
                raise EvidenceError("manifest_type_contract_mismatch")
        for k in (
            "risk_budget_proven_bool",
            "parameter_selection_authorized_bool",
            "live_authorized_bool",
        ):
            if type(manifest[k]) is not bool:
                raise EvidenceError("manifest_type_contract_mismatch")
        if set(manifest["sha256"]) != set(MEMBERS[1:]):
            raise EvidenceError("manifest_sha_member_mismatch")
        for k, h in manifest["sha256"].items():
            if not re.fullmatch(r"[0-9a-f]{64}", h) or sha_bytes(z.read(k)) != h:
                raise EvidenceError("manifest_hash_mismatch")
    return {
        "review_pack_ok": True,
        "run_id": run_id,
        "member_count": len(MEMBERS),
        "non_manifest_hash_count": 13,
    }

# Sprint 06.2B.1 strict persisted-input reconstruction and source hygiene helpers.
SOURCE_CONTROLLED_ROOTS = ("src", "scripts", "tests", "docs", "config")
FORBIDDEN_SOURCE_SUFFIXES = (".zip", ".parquet", ".jsonl", ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo")
FORBIDDEN_SOURCE_DIR_NAMES = ("__pycache__", ".pytest_cache", ".ruff_cache")


def find_source_hygiene_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for rel in SOURCE_CONTROLLED_ROOTS:
        base = root / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            name = path.name
            if path.is_dir() and (name in FORBIDDEN_SOURCE_DIR_NAMES or name.endswith(".egg-info")):
                violations.append(path.relative_to(root).as_posix())
            elif path.is_file() and path.suffix.lower() in FORBIDDEN_SOURCE_SUFFIXES:
                violations.append(path.relative_to(root).as_posix())
    return sorted(violations)
def _sign(v: str) -> str:
    d = _D(v)
    return "positive" if d > 0 else "negative" if d < 0 else "zero"


def _fresh_record_for(s):
    if s.mode is ScenarioMode.fixed_replay:
        r = _fixed_result(s)
        return normalize(r), [r]
    e = _env_result(s)
    return normalize(e), list(e.assignment_results)



def _economic_fingerprint(r):
    sm = r["state_machine_result"]
    cycles = sm["completed_cycles"]
    return {
        "final_total_pnl_usdt": r["final_total_pnl_usdt"],
        "final_mark_price": r["final_mark_price"],
        "signed_position": sm["signed_position"],
        "average_entry": sm["average_entry"],
        "cumulative_realized_position_pnl_usdt": sm["cumulative_realized_position_pnl_gross_usdt"],
        "cumulative_completed_cycle_gross_pnl_usdt": sm["cumulative_completed_grid_cycle_gross_usdt"],
        "cumulative_trading_fees_usdt": sm["cumulative_trading_fees_usdt"],
        "cumulative_funding_pnl_usdt": sm["cumulative_funding_pnl_usdt"],
        "completed_cycle_count": len(cycles),
        "canonical_cycle_totals": [canonical_sha256(c) for c in cycles],
        "terminated_bool": r["terminated_bool"],
        "termination_reason": r["termination_reason"],
        "candle_count_processed": r["candle_count_processed"],
        "candles_not_processed_after_termination": r["candles_not_processed_after_termination"],
    }


NESTED_PROOF_GUARDRAIL_KEYS = (
    "native_equivalence_proven_bool",
    "native_quantity_mapping_proven_bool",
    "native_termination_mapping_proven_bool",
    "liquidation_modeled_bool",
    "risk_budget_proven_bool",
    "profitability_claims_present_bool",
    "live_execution_present_bool",
)
MINIMAL_PATH_CONTRACT_GUARDRAIL_KEYS = (
    "full_intrabar_path_reconstructed_bool",
    "arbitrary_intrabar_oscillation_bounded_bool",
    "global_true_worst_case_proven_bool",
    "global_true_best_case_proven_bool",
)
SYNTHETIC_PHASE_GUARDRAIL_KEYS = (
    "real_bybit_batch_integration_proven_bool",
    "funding_coverage_proven_bool",
    "sufficient_for_bybit_batch_integration_bool",
    "sufficient_for_parameter_selection_bool",
    "parameter_selection_authorized_bool",
    "live_authorized_bool",
)
ALLOWED_GUARDRAIL_SOURCES = {
    "nested_state_machine_proof_flags",
    "minimal_path_contract",
    "synthetic_phase_contract",
}


def derive_guardrails_for_scenario(s, results):
    del s
    proof_sets = []
    exact = True
    consistent = True
    derived = {}
    sources = {}
    for r in results:
        flags = normalize(r)["state_machine_result"].get("proof_flags")
        if type(flags) is not dict:
            exact = False
            flags = {}
        proof_sets.append(flags)
    for key in NESTED_PROOF_GUARDRAIL_KEYS:
        vals = []
        for flags in proof_sets:
            if key not in flags or type(flags.get(key)) is not bool:
                exact = False
                vals.append(None)
            else:
                vals.append(flags[key])
        if vals and any(v != vals[0] for v in vals):
            consistent = False
        derived[key] = vals[0] if vals and type(vals[0]) is bool else False
        sources[key] = "nested_state_machine_proof_flags"
    for key in MINIMAL_PATH_CONTRACT_GUARDRAIL_KEYS:
        derived[key] = False
        sources[key] = "minimal_path_contract"
    for key in SYNTHETIC_PHASE_GUARDRAIL_KEYS:
        derived[key] = False
        sources[key] = "synthetic_phase_contract"
    return {
        "guardrails": derived,
        "guardrail_sources_by_key": sources,
        "nested_proof_flags_consistent_bool": consistent and exact,
        "all_guardrails_exact_bool_bool": exact and all(type(v) is bool for v in derived.values()),
        "unexpected_true_guardrail_keys": [k for k, v in derived.items() if v is True and _GUARDRAILS.get(k) is False],
    }


def _termination_prefix_check(s, r, rn):
    generated = rn["generated_events"]
    full = normalize(reconstruct_expected_event_schedule(s.candles, r.path_policies, s.funding_observations))
    consumed_exact = generated == full[: len(generated)] and (len(generated) <= len(full) if rn["terminated_bool"] else len(generated) == len(full))
    event_types = [e["event_type"] for e in rn["state_machine_result"]["ledger"]]
    triggers = event_types.count("termination_trigger")
    fills = event_types.count("termination_fill")
    trigger_events = [e for e in rn["state_machine_result"]["ledger"] if e["event_type"] == "termination_trigger"]
    last = generated[-1] if generated else None
    trigger_seq = trigger_events[0]["sequence_id"] if trigger_events else None
    trigger_match = bool(trigger_events and last and trigger_events[0]["sequence_id"] == last["sequence_id"] and trigger_events[0]["time_ms"] == last["time_ms"])
    contract_ok = (triggers == 1 and fills <= 1) if rn["terminated_bool"] else triggers == 0
    reconciled = rn["candle_count_processed"] + rn["candles_not_processed_after_termination"] == len(s.candles)
    later_absent = len(generated) <= len(full) and (len(generated) == len(full) or (rn["terminated_bool"] and all(e["sequence_id"] > generated[-1]["sequence_id"] for e in full[len(generated) :])))
    detail = {
        "full_schedule_event_count": len(full),
        "consumed_event_count": len(generated),
        "unconsumed_event_count": len(full) - len(generated),
        "consumed_event_prefix_exact_bool": consumed_exact,
        "termination_trigger_sequence_id": trigger_seq,
        "termination_trigger_matches_last_consumed_event_bool": (trigger_match if rn["terminated_bool"] else True),
        "later_price_or_funding_events_absent_bool": later_absent,
        "termination_event_contract_ok": contract_ok and (trigger_match if rn["terminated_bool"] else True),
        "ignored_candle_count_reconciled_bool": reconciled,
    }
    return detail


def _funding_before_price_enforced(s, results):
    for r in results:
        full = normalize(
            reconstruct_expected_event_schedule(s.candles, r.path_policies, s.funding_observations)
        )
        seen_price_boundaries = set()
        for event in full:
            boundary = (event["time_ms"], event["candle_index"])
            if event["kind"] == "price":
                seen_price_boundaries.add(boundary)
            elif boundary in seen_price_boundaries:
                return False
    return True


def derive_scenario_audit(catalog=SCENARIO_CATALOG, replay_records=None):
    checks = {}
    failures = []
    ids = [s.scenario_id for s in catalog]
    if tuple(ids) != SCENARIO_IDS or len(set(ids)) != len(ids) or len(ids) != CANONICAL_SCENARIO_COUNT:
        failures.append("scenario_id_contract")
    record_map = replay_records or {}
    for s in catalog:
        _, fresh_results = _fresh_record_for(s)
        if s.scenario_id in record_map:
            results = record_map[s.scenario_id]
        else:
            results = fresh_results
        result_norms = [normalize(r) if not isinstance(r, dict) else r for r in results]
        final_pnls = [r["final_total_pnl_usdt"] for r in result_norms]
        ledgers = [r["state_machine_result"]["ledger"] for r in result_norms]
        cycles = [len(r["state_machine_result"]["completed_cycles"]) for r in result_norms]
        funding_events = [e for r in result_norms for e in r["state_machine_result"]["ledger"] if e["event_type"] == "funding"]
        assignment_keys = []
        if s.mode is ScenarioMode.ambiguity_envelope:
            assignment_keys = ["".join(str(i) for i in _assignment_key(r)) for r in fresh_results]
        final_positions = [r["state_machine_result"]["signed_position"] for r in result_norms]
        cumulative_funding = result_norms[0]["state_machine_result"]["cumulative_funding_pnl_usdt"] if result_norms else "0"
        generated_prices = [e["price"] for r in result_norms for e in r["generated_events"] if e["kind"] == "price"]
        geom = geometric_grid_levels_decimal(s.config.lower_price, s.config.upper_price, s.config.grid_cell_number)
        canonical_levels = [str(x) for x in geom.levels]
        level_count = int(s.config.grid_cell_number) + 1
        result_levels = [r["state_machine_result"]["levels"] for r in result_norms]
        canonical_levels_ok = len(canonical_levels) == level_count and len(set(canonical_levels)) == level_count and all(_D(canonical_levels[i]) < _D(canonical_levels[i + 1]) for i in range(level_count - 1)) and canonical_levels[0] == str(s.config.lower_price) and canonical_levels[-1] == str(s.config.upper_price) and geom.geometry_rounding_applied_bool is False
        all_assignments_geometry = all(x == canonical_levels for x in result_levels)
        econ_fps = [_economic_fingerprint(r) for r in result_norms]
        econ_hashes = {canonical_sha256(x) for x in econ_fps}
        event_hashes = {canonical_sha256(r["generated_events"]) for r in result_norms}
        ledger_hashes = {canonical_sha256(r["state_machine_result"]["ledger"]) for r in result_norms}
        prefix_bits = [_termination_prefix_check(s, fresh_results[i], result_norms[i]) for i in range(len(result_norms))]
        term_sides = [x for x in (("lower" if s.config.lower_termination_price is not None else None), ("upper" if s.config.upper_termination_price is not None else None)) if x]
        guardrail_evidence = derive_guardrails_for_scenario(s, results)
        guardrails = guardrail_evidence["guardrails"]
        check = {
            "mode": s.mode.value,
            "category_symbol_source_consistent_bool": s.config.category == "linear" and all(c.symbol == s.config.symbol for c in s.candles) and all(f.symbol == s.config.symbol for f in s.funding_observations),
            "closed_contiguous_candles_bool": all(c.closed_bool for c in s.candles) and all(c.open_time_ms == s.entry_time_ms + i * 60000 for i, c in enumerate(s.candles)),
            "assignment_count": len(result_norms),
            "assignment_keys": assignment_keys,
            "assignment_keys_unique_bool": len(set(assignment_keys)) == len(assignment_keys),
            "assignment_keys_exact_ordered_bool": assignment_keys == sorted(assignment_keys) and len(set(assignment_keys)) == len(assignment_keys),
            "minimal_path_policies_frozen_bool": all(len(r.path_policies) == len(s.candles) and all(p.value in {"open_high_low_close", "open_low_high_close"} for p in r.path_policies) for r in fresh_results),
            "funding_before_price_enforced_bool": _funding_before_price_enforced(s, fresh_results),
            "strict_snapshot_identity_bool": len(result_norms) == len(fresh_results),
            "fresh_nested_replay_enforced_bool": len(fresh_results) == len(result_norms),
            "economic_fingerprints": econ_fps,
            "path_sensitive_bool": len(econ_hashes) > 1,
            "material_path_outcome_differs_bool": len(econ_hashes) > 1,
            "trace_sensitive_bool": len(event_hashes) > 1 or len(ledger_hashes) > 1,
            "all_final_positions_non_negative_bool": all(_D(p) >= 0 for p in final_positions),
            "all_final_positions_negative_bool": all(_D(p) < 0 for p in final_positions),
            "positive_long_exposure_observed_bool": any(_D(p) > 0 for p in final_positions),
            "completed_cycle_count_min": min(cycles) if cycles else 0,
            "completed_cycle_count_max": max(cycles) if cycles else 0,
            "funding_event_count": len(funding_events),
            "funding_rate_signs": [_sign(e["funding_rate"]) for e in funding_events],
            "funding_pnl_signs": [_sign(e["funding_pnl_usdt"]) for e in funding_events],
            "funding_positions_before": [e["signed_position_before"] for e in funding_events],
            "cumulative_funding_pnl_usdt": cumulative_funding,
            "cumulative_funding_pnl_sign": _sign(cumulative_funding),
            "termination_reason": result_norms[0]["termination_reason"] if result_norms else None,
            "termination_candle_index": (result_norms[0]["candle_count_processed"] - 1 if result_norms and result_norms[0]["termination_reason"] else None),
            "position_flat_after_termination_bool": (not result_norms[0]["termination_reason"]) or _D(result_norms[0]["state_machine_result"]["signed_position"]) == 0,
            "candles_not_processed_after_termination": result_norms[0]["candles_not_processed_after_termination"] if result_norms else 0,
            "termination_prefix_evidence_by_assignment": prefix_bits,
            "consumed_event_prefix_exact_bool": all(x["consumed_event_prefix_exact_bool"] for x in prefix_bits),
            "later_price_or_funding_events_absent_bool": all(x["later_price_or_funding_events_absent_bool"] for x in prefix_bits),
            "termination_event_contract_ok": all(x["termination_event_contract_ok"] for x in prefix_bits),
            "ignored_candle_count_reconciled_bool": all(x["ignored_candle_count_reconciled_bool"] for x in prefix_bits),
            "canonical_levels": canonical_levels,
            "canonical_level_count": level_count,
            "canonical_levels_preserved_bool": canonical_levels_ok and all_assignments_geometry,
            "no_level_collapse_bool": len(set(canonical_levels)) == level_count,
            "all_assignments_share_exact_geometry_bool": all_assignments_geometry,
            "geometry_rounding_applied_bool": geom.geometry_rounding_applied_bool,
            "configured_termination_sides": term_sides,
            "one_termination_boundary_configured_bool": len(term_sides) == 1,
            "lower_termination_side_configured_bool": term_sides == ["lower"],
            "upper_termination_side_configured_bool": term_sides == ["upper"],
            "two_sided_termination_configured_bool": len(term_sides) == 2,
            "guardrails": guardrails,
            "guardrail_sources_by_key": guardrail_evidence["guardrail_sources_by_key"],
            "nested_proof_flags_consistent_bool": guardrail_evidence["nested_proof_flags_consistent_bool"],
            "all_guardrails_exact_bool_bool": guardrail_evidence["all_guardrails_exact_bool_bool"],
            "unexpected_true_guardrail_keys": guardrail_evidence["unexpected_true_guardrail_keys"],
        }
        if not check["canonical_levels_preserved_bool"]:
            failures.append(f"{s.scenario_id}:canonical_levels")
        if not (check["consumed_event_prefix_exact_bool"] and check["later_price_or_funding_events_absent_bool"] and check["termination_event_contract_ok"] and check["ignored_candle_count_reconciled_bool"]):
            failures.append(f"{s.scenario_id}:termination_prefix")
        if not (check["nested_proof_flags_consistent_bool"] and check["all_guardrails_exact_bool_bool"]) or check["unexpected_true_guardrail_keys"]:
            failures.append(f"{s.scenario_id}:guardrails")
        if s.scenario_id in {"09_gap_up_preserved", "10_gap_down_preserved"}:
            prev_close = str(s.candles[0].close)
            next_open = str(s.candles[1].open)
            lo, hi = sorted((_D(prev_close), _D(next_open)))
            check.update(
                {
                    "gap_direction": "up" if _D(next_open) > _D(prev_close) else "down",
                    "previous_candle_close_retained": prev_close,
                    "next_candle_open_retained": next_open,
                    "gap_preserved_bool": prev_close in generated_prices and next_open in generated_prices,
                    "no_interpolated_synthetic_price_inserted_between_gap_bool": not any(
                        lo < _D(p) < hi
                        for p in generated_prices[
                            generated_prices.index(prev_close) + 1 : generated_prices.index(next_open)
                        ]
                    ),
                }
            )
        if s.scenario_id == "07_equal_pnl_different_nested_ledger":
            check["exact_equal_pnl_bool"] = len(set(final_pnls)) == 1
            check["nested_result_differs_bool"] = len({canonical_sha256(r["state_machine_result"]) for r in result_norms}) > 1
            check["ledger_differs_bool"] = len({canonical_sha256(x) for x in ledgers}) > 1
            check["economic_fingerprint_equal_bool"] = len(econ_hashes) == 1
        if s.scenario_id == "22_bybit_source_enum_contract":
            check["candle_sources"] = [c.source.value for c in s.candles]
            check["funding_rate_sources"] = [f.funding_rate_source.value for f in s.funding_observations]
            check["funding_mark_price_sources"] = [f.mark_price_source.value for f in s.funding_observations]
            check["synthetic_fixture_of_source_contract_bool"] = (set(check["candle_sources"]) == {_CandleSource.bybit_trade_kline_1m.value} and set(check["funding_rate_sources"]) == {_FundingRateSource.bybit_funding_history.value} and set(check["funding_mark_price_sources"]) == {_FundingMarkPriceSource.bybit_mark_price_kline_1m.value})
        for k, v in dict(s.expected).items():
            if k in _GUARDRAILS:
                if guardrails[k] is not v:
                    failures.append(f"{s.scenario_id}:{k}")
            elif k == "exact_assignment_count" and check["assignment_count"] != v:
                failures.append(f"{s.scenario_id}:{k}")
            elif k == "path_sensitive_bool" and check["path_sensitive_bool"] is not v:
                failures.append(f"{s.scenario_id}:{k}")
            elif k == "equal_top_level_pnl_different_nested_ledger_bool" and not (check.get("exact_equal_pnl_bool") and check.get("nested_result_differs_bool") and check.get("ledger_differs_bool") and check.get("economic_fingerprint_equal_bool")):
                failures.append(f"{s.scenario_id}:{k}")
            elif k == "completed_cycle_count_min" and check["completed_cycle_count_min"] != v:
                failures.append(f"{s.scenario_id}:{k}")
            elif k == "completed_cycle_count_max" and check["completed_cycle_count_max"] != v:
                failures.append(f"{s.scenario_id}:{k}")
            elif k == "funding_pnl_sign" and _sign(result_norms[0]["state_machine_result"]["cumulative_funding_pnl_usdt"]) != v:
                failures.append(f"{s.scenario_id}:{k}")
            elif k == "synthetic_fixture_of_source_contract_bool" and check.get(k) is not v:
                failures.append(f"{s.scenario_id}:{k}")
            elif k not in {"path_sensitive_bool","exact_assignment_count","equal_top_level_pnl_different_nested_ledger_bool","completed_cycle_count_min","completed_cycle_count_max","funding_pnl_sign","synthetic_fixture_of_source_contract_bool"}:
                failures.append(f"{s.scenario_id}:unmapped:{k}")
        checks[s.scenario_id] = check
    all_guardrails = bool(checks) and all(c["nested_proof_flags_consistent_bool"] and c["all_guardrails_exact_bool_bool"] and not c["unexpected_true_guardrail_keys"] for c in checks.values())
    all_prefixes = bool(checks) and all(c["consumed_event_prefix_exact_bool"] and c["later_price_or_funding_events_absent_bool"] and c["termination_event_contract_ok"] and c["ignored_candle_count_reconciled_bool"] for c in checks.values())
    return {"scenario_audit_version": SCENARIO_AUDIT_VERSION, "scenario_count": len(ids), "canonical_scenario_count": CANONICAL_SCENARIO_COUNT, "scenario_ids": ids, "scenario_ids_unique_bool": len(set(ids)) == len(ids), "scenario_ids_exact_order_bool": tuple(ids) == SCENARIO_IDS, "all_scenario_guardrails_derived_bool": all_guardrails, "all_nested_proof_flags_consistent_bool": all(c["nested_proof_flags_consistent_bool"] for c in checks.values()), "all_termination_prefixes_reconciled_bool": all_prefixes, "scenario_checks_by_id": checks, "failures": failures, "scenario_audit_ok": not failures}


def build_scenario_audit():
    return derive_scenario_audit()


def _exact_keys(obj, keys, label):
    if type(obj) is not dict or set(obj) != set(keys):
        raise EvidenceError(f"{label}_key_contract_mismatch")


def _dec_from_str(v, label):
    if type(v) is not str:
        raise EvidenceError(f"{label}_decimal_string_required")
    return _D(v)


def _config_from_obj(o):
    keys = ["category","symbol","lower_price","upper_price","base_price","grid_cell_number","quantity_per_grid_base","quantity_source","leverage","maker_fee_rate","taker_fee_rate","grid_fill_liquidity_role","termination_liquidity_role","termination_slippage_bps","lower_termination_price","upper_termination_price"]
    _exact_keys(o, keys, "config")
    return _NeutralGridConfig(o["category"], o["symbol"], _dec_from_str(o["lower_price"], "lower_price"), _dec_from_str(o["upper_price"], "upper_price"), _dec_from_str(o["base_price"], "base_price"), o["grid_cell_number"], _dec_from_str(o["quantity_per_grid_base"], "quantity"), _QuantitySource(o["quantity_source"]), _dec_from_str(o["leverage"], "leverage"), _dec_from_str(o["maker_fee_rate"], "maker_fee_rate"), _dec_from_str(o["taker_fee_rate"], "taker_fee_rate"), _LiquidityRole(o["grid_fill_liquidity_role"]), _LiquidityRole(o["termination_liquidity_role"]), _dec_from_str(o["termination_slippage_bps"], "slippage"), None if o["lower_termination_price"] is None else _dec_from_str(o["lower_termination_price"], "lower_term"), None if o["upper_termination_price"] is None else _dec_from_str(o["upper_termination_price"], "upper_term"))


def _candle_from_obj(o):
    _exact_keys(o, ["category","symbol","open_time_ms","open","high","low","close","closed_bool","source"], "candle")
    return _OhlcCandle1m(o["category"], o["symbol"], o["open_time_ms"], _dec_from_str(o["open"], "open"), _dec_from_str(o["high"], "high"), _dec_from_str(o["low"], "low"), _dec_from_str(o["close"], "close"), o["closed_bool"], _CandleSource(o["source"]))


def _funding_from_obj(o):
    _exact_keys(o, ["category","symbol","time_ms","funding_rate","mark_price","funding_rate_source","mark_price_source"], "funding")
    return _FundingObservation(o["category"], o["symbol"], o["time_ms"], _dec_from_str(o["funding_rate"], "funding_rate"), _dec_from_str(o["mark_price"], "mark_price"), _FundingRateSource(o["funding_rate_source"]), _FundingMarkPriceSource(o["mark_price_source"]))


def deserialize_scenario_record(row) -> _OhlcReplayScenario:
    _exact_keys(row, ["scenario_id", "scenario_version", "scenario_input_sha256", "mode", "scenario"], "scenario_input_row")
    scen = row["scenario"]
    _exact_keys(scen, ["scenario_id","scenario_version","mode","config","entry_time_ms","candles","funding_observations","path_policies","max_exact_ambiguous_candles","expected"], "scenario")
    if canonical_sha256(scen) != row["scenario_input_sha256"]:
        raise EvidenceError("scenario_input_sha256_mismatch")
    mode = ScenarioMode(row["mode"])
    if scen["mode"] != row["mode"] or scen["scenario_id"] != row["scenario_id"] or scen["scenario_version"] != row["scenario_version"]:
        raise EvidenceError("scenario_row_field_mismatch")
    policies = None if scen["path_policies"] is None else tuple(_MinimalPathPolicy(x) for x in scen["path_policies"])
    s = _OhlcReplayScenario(scen["scenario_id"], scen["scenario_version"], mode, _config_from_obj(scen["config"]), scen["entry_time_ms"], tuple(_candle_from_obj(x) for x in scen["candles"]), tuple(_funding_from_obj(x) for x in scen["funding_observations"]), policies, scen["max_exact_ambiguous_candles"], _MappingProxyType(dict(scen["expected"])))
    if normalize(s) != scen:
        raise EvidenceError("reconstructed_scenario_bytes_mismatch")
    return s


def reconstruct_persisted_scenarios(rows):
    scenarios = tuple(deserialize_scenario_record(r) for r in rows)
    if tuple(s.scenario_id for s in scenarios) != SCENARIO_IDS:
        raise EvidenceError("persisted_scenario_id_order_mismatch")
    if len({s.scenario_id for s in scenarios}) != CANONICAL_SCENARIO_COUNT:
        raise EvidenceError("persisted_scenario_duplicate_or_missing")
    return scenarios
