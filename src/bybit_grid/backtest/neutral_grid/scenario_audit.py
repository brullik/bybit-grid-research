from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evidence import audit_persisted_scenario_evidence, scenario_input_record
from .scenarios import ScenarioDefinition, canonical_scenarios, replay_scenario
from .serialization import normalize
from .audit import audit_simulation_result


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


def scenario_result_record(s: ScenarioDefinition) -> dict[str, Any]:
    r = replay_scenario(s)
    nr = normalize(r)
    return {
        "scenario_id": s.scenario_id,
        "scenario_input_sha256": scenario_input_record(s)["scenario_input_sha256"],
        "result_audit_passed_bool": audit_simulation_result(r).passed_bool,
        "normalized_result": nr,
        "result_sha256": __import__(
            "bybit_grid.backtest.neutral_grid.serialization", fromlist=["canonical_sha256"]
        ).canonical_sha256(nr),
    }


def audit_scenario_evidence(
    scenarios: tuple[ScenarioDefinition, ...] | None = None,
    stored_results: dict[str, Any] | None = None,
) -> ScenarioEvidenceAudit:
    scenarios = scenarios or canonical_scenarios()
    inputs = [scenario_input_record(s) for s in scenarios]
    results = []
    ledger = []
    cycles = []
    for s in scenarios:
        r = replay_scenario(s)
        row = scenario_result_record(s)
        if stored_results is not None and s.scenario_id in stored_results:
            row = row | {"normalized_result": stored_results[s.scenario_id]}
        results.append(row)
        ledger.extend({"scenario_id": s.scenario_id, **normalize(e)} for e in r.ledger)
        cycles.extend({"scenario_id": s.scenario_id, **normalize(c)} for c in r.completed_cycles)
    d = audit_persisted_scenario_evidence(inputs, results, ledger, cycles)
    return ScenarioEvidenceAudit(
        d["scenario_audit_ok"],
        tuple(d["failures"]),
        d["canonical_scenario_count"],
        d["all_scenarios_replay_match_bool"],
        d["all_result_audits_pass_bool"],
        d["input_event_evidence_complete_bool"],
        d["scenario_ids_unique_bool"],
        d["scenario_input_hashes_unique_bool"],
        d["ledger_ids_unique_within_scenario_bool"],
        d["order_ids_unique_within_scenario_bool"],
        d["cycle_ids_unique_within_scenario_bool"],
        d["all_terminated_scenarios_flat_bool"],
        d["all_nonterminated_scenarios_have_empty_termination_summary_bool"],
    )
