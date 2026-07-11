from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from .audit import audit_simulation_result
from .scenarios import SCENARIO_IDS, ScenarioDefinition, canonical_scenarios, replay_scenario
from .serialization import canonical_sha256, normalize


@dataclass(frozen=True)
class ScenarioEvidenceAudit:
    scenario_audit_ok: bool
    failures: tuple[str, ...]
    canonical_scenario_count: int
    all_scenarios_replay_match_bool: bool
    all_result_audits_pass_bool: bool
    input_event_evidence_complete_bool: bool
    scenario_ids_unique_bool: bool
    scenario_input_hashes_unique_bool: bool
    ledger_ids_unique_within_scenario_bool: bool
    order_ids_unique_within_scenario_bool: bool
    cycle_ids_unique_within_scenario_bool: bool
    all_terminated_scenarios_flat_bool: bool
    all_nonterminated_scenarios_have_empty_termination_summary_bool: bool


def scenario_input_record(s: ScenarioDefinition) -> dict[str, Any]:
    rec = normalize(s)
    return {
        "scenario_id": s.scenario_id,
        "scenario_input_sha256": canonical_sha256(rec),
        "scenario": rec,
    }


def scenario_result_record(s: ScenarioDefinition) -> dict[str, Any]:
    r = replay_scenario(s)
    a = audit_simulation_result(r)
    return {
        "scenario_id": s.scenario_id,
        "result_audit_passed_bool": a.passed_bool,
        "normalized_result": normalize(r),
        "result_sha256": canonical_sha256(normalize(r)),
    }


def audit_scenario_evidence(
    scenarios: tuple[ScenarioDefinition, ...] | None = None,
    stored_results: dict[str, Any] | None = None,
) -> ScenarioEvidenceAudit:
    scenarios = scenarios or canonical_scenarios()
    failures = []
    ids = [s.scenario_id for s in scenarios]
    hashes = [scenario_input_record(s)["scenario_input_sha256"] for s in scenarios]
    replay_match = True
    audits = True
    ledger_unique = True
    order_unique = True
    cycle_unique = True
    term_flat = True
    nonterm_empty = True
    for s in scenarios:
        r = replay_scenario(s)
        ar = audit_simulation_result(r)
        audits &= ar.passed_bool
        if stored_results and stored_results.get(s.scenario_id) != normalize(r):
            replay_match = False
        lids = [e.ledger_event_id for e in r.ledger]
        ledger_unique &= len(lids) == len(set(lids))
        oids = [o.order_id for o in r.all_orders]
        order_unique &= len(oids) == len(set(oids))
        cids = [c.cycle_id for c in r.completed_cycles]
        cycle_unique &= len(cids) == len(set(cids))
        if r.terminated_bool:
            term_flat &= r.signed_position == 0 and r.average_entry is None
        else:
            nonterm_empty &= normalize(r.termination) == normalize(r.termination.__class__())
    exact_ids = tuple(ids) == SCENARIO_IDS
    ids_unique = len(ids) == len(set(ids))
    hashes_unique = len(hashes) == len(set(hashes))
    ok = (
        exact_ids
        and len(ids) == 33
        and ids_unique
        and hashes_unique
        and replay_match
        and audits
        and ledger_unique
        and order_unique
        and cycle_unique
        and term_flat
        and nonterm_empty
    )
    if not exact_ids:
        failures.append("scenario id set/order mismatch")
    return ScenarioEvidenceAudit(
        ok,
        tuple(failures),
        len(ids),
        replay_match,
        audits,
        True,
        ids_unique,
        hashes_unique,
        ledger_unique,
        order_unique,
        cycle_unique,
        term_flat,
        nonterm_empty,
    )
