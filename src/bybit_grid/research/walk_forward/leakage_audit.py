from __future__ import annotations
from pathlib import Path
import json
import polars as pl


def audit_splits(splits: pl.DataFrame) -> dict[str, object]:
    violations = []
    if not splits.is_empty():
        for fid in splits["fold_id"].unique().to_list():
            f = splits.filter(pl.col("fold_id") == fid)
            for key, typ in [
                ("range_action_event_id", "overlapping_event_ids"),
                ("range_regime_id", "overlapping_regime_ids"),
            ]:
                c = (
                    f.group_by(key)
                    .agg(pl.col("role").n_unique().alias("n"))
                    .filter(pl.col("n") > 1)
                )
                if c.height:
                    violations.append({"fold_id": fid, "type": typ, "count": c.height})
            vals = f.select(
                pl.first("validation_start_ms"),
                pl.first("validation_end_ms"),
                pl.first("test_start_ms"),
                pl.first("test_end_ms"),
                pl.first("purge_minutes"),
                pl.first("embargo_minutes"),
            ).row(0, named=True)
            tr = f.filter(pl.col("role") == "train")
            va = f.filter(pl.col("role") == "validation")
            te = f.filter(pl.col("role") == "test")
            if tr.height and tr["outcome_end_ms"].max() >= vals["validation_start_ms"]:
                violations.append({"fold_id": fid, "type": "train_outcome_crosses_validation"})
            if va.height and va["outcome_end_ms"].max() >= vals["test_start_ms"]:
                violations.append({"fold_id": fid, "type": "validation_outcome_crosses_test"})
            if te.height and te["outcome_end_ms"].max() > vals["test_end_ms"]:
                violations.append({"fold_id": fid, "type": "test_outcome_crosses_test_end"})
            if vals["purge_minutes"] < 2880 or vals["embargo_minutes"] < 2880:
                violations.append({"fold_id": fid, "type": "gap_too_small"})
    return {
        "leakage_violations": len(violations),
        "violations": violations,
        "leakage_audit_ok": not violations,
        "temporal_leakage_audit_ok": not violations,
    }


def write_leakage_audit(scoring_run_id: str) -> dict[str, object]:
    root = Path("data/processed/scoring_runs") / scoring_run_id
    res = audit_splits(pl.read_parquet(root / "walk_forward_splits.parquet"))
    pl.DataFrame([res | {"violations_json": json.dumps(res["violations"])}]).write_parquet(
        root / "walk_forward_leakage_audit.parquet"
    )
    (root / "walk_forward_temporal_leakage_audit.json").write_text(
        json.dumps(res, indent=2), encoding="utf-8"
    )
    rep = Path("reports/scoring_runs") / scoring_run_id
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "walk_forward_leakage_audit_summary.json").write_text(
        json.dumps(res, indent=2), encoding="utf-8"
    )
    if res["leakage_violations"]:
        raise ValueError(json.dumps(res))
    return res
# Mandatory RED probe for issue #156 (3/8); behavior intentionally unchanged.
