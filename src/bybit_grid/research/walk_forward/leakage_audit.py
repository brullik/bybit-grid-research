from __future__ import annotations
from pathlib import Path
import json
import polars as pl


def audit_splits(splits: pl.DataFrame) -> dict[str, object]:
    violations = []
    if not splits.is_empty():
        for fid in splits["fold_id"].unique().to_list():
            f = splits.filter(pl.col("fold_id") == fid)
            role_counts = (
                f.group_by("range_action_event_id")
                .agg(pl.col("role").n_unique().alias("n"))
                .filter(pl.col("n") > 1)
            )
            if role_counts.height:
                violations.append(
                    {"fold_id": fid, "type": "overlapping_event_ids", "count": role_counts.height}
                )
            reg_counts = (
                f.group_by("range_regime_id")
                .agg(pl.col("role").n_unique().alias("n"))
                .filter(pl.col("n") > 1)
            )
            if reg_counts.height:
                violations.append(
                    {"fold_id": fid, "type": "overlapping_regime_ids", "count": reg_counts.height}
                )
            if int(f["embargo_minutes"].min() or 0) < 2880:
                violations.append({"fold_id": fid, "type": "missing_embargo"})
    return {
        "leakage_violations": len(violations),
        "violations": violations,
        "leakage_audit_ok": not violations,
    }


def write_leakage_audit(scoring_run_id: str) -> dict[str, object]:
    root = Path("data/processed/scoring_runs") / scoring_run_id
    res = audit_splits(pl.read_parquet(root / "walk_forward_splits.parquet"))
    pl.DataFrame([res | {"violations_json": json.dumps(res["violations"])}]).write_parquet(
        root / "walk_forward_leakage_audit.parquet"
    )
    rep = Path("reports/scoring_runs") / scoring_run_id
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "walk_forward_leakage_audit_summary.json").write_text(
        json.dumps(res, indent=2), encoding="utf-8"
    )
    if res["leakage_violations"]:
        raise ValueError(json.dumps(res))
    return res
