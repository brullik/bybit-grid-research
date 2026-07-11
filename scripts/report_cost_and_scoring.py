from __future__ import annotations
import argparse
import json
from pathlib import Path

import polars as pl

REQUIRED_CANONICAL = [
    "fee_coverage_audit.json",
    "scoring_semantics_audit.json",
]
REQUIRED_REPORT = ["cost_model_config_resolved.yml", "cost_model_audit.json"]


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def generate_cost_and_scoring_reports(scoring_run_id: str) -> dict[str, object]:
    data = Path("data/processed/scoring_runs") / scoring_run_id
    rep = Path("reports/scoring_runs") / scoring_run_id
    missing = [str(data / n) for n in REQUIRED_CANONICAL if not (data / n).exists()]
    missing += [str(rep / n) for n in REQUIRED_REPORT if not (rep / n).exists()]
    if missing:
        raise FileNotFoundError(json.dumps({"missing_canonical_provenance": missing}))

    before = {p: p.read_bytes() for p in [rep / n for n in REQUIRED_REPORT]}
    fee = _load_json(data / "fee_coverage_audit.json")
    sem = _load_json(data / "scoring_semantics_audit.json")
    cost = _load_json(rep / "cost_model_audit.json")
    cfg_text = (rep / "cost_model_config_resolved.yml").read_text(encoding="utf-8")
    if "REQUIRED_FOR_ACCOUNT_ACTUAL" in cfg_text or "manual_scenario" in cfg_text:
        raise ValueError("unresolved fee provenance in resolved cost config")
    checks = {
        "fee_coverage_ok": fee.get("fee_coverage_ok") is True,
        "cost_model_audit_ok": cost.get("cost_model_audit_ok") is True,
        "formula_present": cost.get("cost_formula_version") == "cost_formula_v2_asymmetric_slippage",
        "risk_unproven": cost.get("risk_budget_proven_bool") is False and sem.get("risk_budget_proven_bool") is False,
        "scoring_semantics_audit_ok": sem.get("scoring_semantics_audit_ok") is True,
    }
    if not all(checks.values()):
        raise ValueError(json.dumps({"report_cost_and_scoring_ok": False, "checks": checks}, sort_keys=True))

    dataset = data / "outcome_scoring_dataset.parquet"
    scoring_rows = pl.read_parquet(dataset).height if dataset.exists() else sem.get("rows_total")
    md = "\n".join([
        "# Outcome Scoring Report",
        "",
        f"scoring_run_id: {scoring_run_id}",
        f"rows_total: {sem.get('rows_total', scoring_rows)}",
        f"score_eligible_rows: {sem.get('score_eligible_rows')}",
        f"score_ineligible_rows: {sem.get('score_ineligible_rows')}",
        f"score_eligible_rate: {sem.get('score_eligible_rate')}",
        f"ineligible_reason_counts: {json.dumps(sem.get('ineligible_reason_counts', []), sort_keys=True)}",
        "Incomplete evidence is excluded from ranking; canonical v3 scores are null for ineligible rows.",
        f"fee_snapshot_id_resolved: {fee.get('fee_snapshot_id_resolved')}",
        f"fee_source: {fee.get('fee_source')}",
        f"fee_coverage_rate: {fee.get('fee_coverage_rate')}",
        f"high_correlation_pair_count_abs_spearman_ge_0_98: {sem.get('high_correlation_pair_count_abs_spearman_ge_0_98')}",
        "Proxy only: not PnL, EV, ROI, or profitability.",
        "5 USDT max-loss budget is not proven; risk_budget_proven_bool=false.",
        "",
    ])
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "outcome_scoring_report.md").write_text(md, encoding="utf-8")
    (rep / "risk_budget_readiness_report.md").write_text(
        "# Risk Budget Status\n\nrisk_budget_proven_bool: false\n5 USDT budget is not proven.\n",
        encoding="utf-8",
    )
    after = {p: p.read_bytes() for p in before}
    if before != after:
        raise RuntimeError("canonical provenance was modified")
    return {"report_cost_and_scoring_ok": True, "scoring_run_id": scoring_run_id, "checks": checks}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scoring-run-id", required=True)
    a = p.parse_args()
    print(json.dumps(generate_cost_and_scoring_reports(a.scoring_run_id), sort_keys=True))


if __name__ == "__main__":
    main()
