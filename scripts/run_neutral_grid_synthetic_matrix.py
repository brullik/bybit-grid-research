from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.backtest.neutral_grid.evidence import (
    CONTRACT_AUDIT,
    MEMBERS,
    RISK_REPORT_GUARDRAILS,
    RUN_ID,
    RUN_STATUS_SCHEMA_VERSION,
    SCENARIO_IDS,
    STATE_MACHINE_CONTRACT_VERSION,
    audit_persisted_scenario_evidence,
    build_evidence_records,
    derive_reproducibility_audit,
    jsonl_bytes,
    read_jsonl,
    validate_reports,
)
from bybit_grid.backtest.neutral_grid.serialization import canonical_json_bytes


def emit(o):
    print(json.dumps(o, sort_keys=True, separators=(",", ":")))


def write_json(p: Path, o):
    p.write_bytes(canonical_json_bytes(o))


def write_jsonl(p: Path, rows):
    p.write_bytes(jsonl_bytes(rows))


def status(run_id, status_, **kw):
    d = {
        "schema_version": RUN_STATUS_SCHEMA_VERSION,
        "run_id": run_id,
        "status": status_,
        "canonical_scenario_count": 33,
        "completed_scenario_count": kw.get("completed", 0),
        "failed_scenario_count": kw.get("failed", 0),
        "state_machine_contract_version": STATE_MACHINE_CONTRACT_VERSION,
    }
    for k in [
        "input_record_count",
        "result_record_count",
        "ledger_event_count",
        "completed_cycle_count",
        "error_type",
        "error_summary",
    ]:
        if k in kw:
            d[k] = kw[k]
    return d


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=RUN_ID)
    p.add_argument("--output-root", default="data/processed/state_machine_runs")
    p.add_argument("--report-root", default="reports/state_machine_runs")
    p.add_argument("--fail-after-building-test-hook", action="store_true")
    a = p.parse_args(argv)
    out = Path(a.output_root) / a.run_id
    rep = Path(a.report_root) / a.run_id
    out.mkdir(parents=True, exist_ok=True)
    rep.mkdir(parents=True, exist_ok=True)
    sp = out / "state_machine_run_status.json"
    write_json(sp, status(a.run_id, "building"))
    try:
        if a.fail_after_building_test_hook:
            raise RuntimeError("deliberate test hook failure")
        inputs, results, ledger, cycles = build_evidence_records()
        write_json(out / "state_machine_contract_audit.json", CONTRACT_AUDIT)
        write_json(
            out / "scenario_catalog.json",
            {"canonical_scenario_count": 33, "scenario_ids": list(SCENARIO_IDS)},
        )
        write_jsonl(out / "scenario_inputs.jsonl", inputs)
        write_jsonl(out / "scenario_results.jsonl", results)
        write_jsonl(out / "ledger_events.jsonl", ledger)
        write_jsonl(out / "completed_cycles.jsonl", cycles)
        persisted = {
            "inputs": read_jsonl(out / "scenario_inputs.jsonl"),
            "results": read_jsonl(out / "scenario_results.jsonl"),
            "ledger": read_jsonl(out / "ledger_events.jsonl"),
            "cycles": read_jsonl(out / "completed_cycles.jsonl"),
        }
        aud = audit_persisted_scenario_evidence(
            persisted["inputs"], persisted["results"], persisted["ledger"], persisted["cycles"]
        )
        if not aud["scenario_audit_ok"]:
            raise RuntimeError(f"scenario audit failed: {aud['failures']}")
        repro = derive_reproducibility_audit({**persisted, "scenario_audit": aud})
        if not repro["reproducibility_audit_ok"]:
            raise RuntimeError("reproducibility audit failed")
        write_json(out / "scenario_audit.json", aud)
        write_json(out / "reproducibility_audit.json", repro)
        (rep / "synthetic_scenario_report.md").write_text(
            "# Synthetic scenario report\n\ncanonical_scenario_count = 33\ninput_event_evidence_complete_bool = true\nall_scenarios_replay_match_bool = true\nall_result_audits_pass_bool = true\n",
            encoding="utf-8",
        )
        (rep / "risk_budget_readiness_report.md").write_text(
            "# Risk budget readiness\n"
            + "\n".join(f"{k} = {str(v).lower()}" for k, v in RISK_REPORT_GUARDRAILS.items())
            + "\n",
            encoding="utf-8",
        )
        artifacts = {m: (out / m).read_bytes() for m in MEMBERS[1:10]} | {
            m: (rep / m).read_bytes() for m in MEMBERS[10:]
        }
        # validate reports/audits before completion; status is validated after final write by builder/checker
        validate_reports(
            artifacts["synthetic_scenario_report.md"].decode(),
            artifacts["risk_budget_readiness_report.md"].decode(),
        )
        final = status(
            a.run_id,
            "complete",
            completed=33,
            failed=0,
            input_record_count=len(inputs),
            result_record_count=len(results),
            ledger_event_count=len(ledger),
            completed_cycle_count=len(cycles),
        )
        write_json(sp, final)
        emit(
            {
                "run_ok": True,
                "run_id": a.run_id,
                "status": "complete",
                "canonical_scenario_count": 33,
                "input_record_count": len(inputs),
                "result_record_count": len(results),
                "ledger_event_count": len(ledger),
                "completed_cycle_count": len(cycles),
            }
        )
        return 0
    except Exception as e:
        write_json(
            sp,
            status(
                a.run_id,
                "failed",
                failed=33,
                error_type=type(e).__name__,
                error_summary=str(e)[:200],
            ),
        )
        emit(
            {
                "run_ok": False,
                "run_id": a.run_id,
                "status": "failed",
                "error_type": type(e).__name__,
                "error_summary": str(e)[:200],
            }
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
