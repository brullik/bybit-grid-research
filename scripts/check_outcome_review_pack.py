from __future__ import annotations

import argparse
import json
import zipfile

PACK_SCHEMA_VERSION = "outcome_review_pack_v2"
BASE = {
    "outcome_report.md",
    "outcome_quality_report.md",
    "outcome_summary.parquet",
    "outcome_quality_summary.parquet",
    "outcome_perf.json",
    "outcome_semantic_audit.md",
    "outcome_semantic_audit.json",
    "review_pack_manifest.json",
}
FORBIDDEN = (
    "outcomes.parquet",
    "data/raw",
    ".env",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "partitions",
    "cache",
    "secret",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--outcome-run-id", required=True)
    args = ap.parse_args()
    with zipfile.ZipFile(args.zip) as z:
        names_list = z.namelist()
        names = set(names_list)
        if len(names_list) != len(names):
            raise SystemExit("duplicate zip member names detected")
        if any(fragment in n for n in names for fragment in FORBIDDEN):
            raise SystemExit("forbidden review-pack member detected")
        manifest = (
            json.loads(z.read("review_pack_manifest.json").decode("utf-8"))
            if "review_pack_manifest.json" in names
            else {}
        )
        run_kind = manifest.get(
            "run_kind",
            "repair" if "outcome_grid_serialization_repair_report.json" in names else "native",
        )
        required = (set(BASE) if manifest else (set(BASE) - {"review_pack_manifest.json"})) | (
            {"outcome_grid_serialization_repair_report.json"} if run_kind == "repair" else set()
        )
        bad = names - required
        missing = required - names
        if bad or missing:
            raise SystemExit(f"bad={bad} missing={missing}")
        if manifest and (
            manifest.get("outcome_run_id") != args.outcome_run_id
            or manifest.get("pack_schema_version") != PACK_SCHEMA_VERSION
            or sorted(manifest.get("members", [])) != sorted(names)
        ):
            raise SystemExit("manifest mismatch")
        perf = json.loads(z.read("outcome_perf.json").decode("utf-8"))
        audit = json.loads(z.read("outcome_semantic_audit.json").decode("utf-8"))
        if run_kind == "repair":
            repair = json.loads(
                z.read("outcome_grid_serialization_repair_report.json").decode("utf-8")
            )
            if (
                repair.get("non_grid_drift_count") != 0
                or repair.get("semantic_audit_ok") is not True
            ):
                raise SystemExit("repair report failed")
    if audit.get("semantic_audit_ok") is not True or (
        manifest and manifest.get("semantic_audit_ok") is not True
    ):
        raise SystemExit("semantic audit failed or absent")
    if perf.get("outcome_rows_total", 0) <= 0:
        raise SystemExit("outcome_rows_total must be > 0")
    if manifest and manifest.get("outcome_rows_total") != perf.get("outcome_rows_total"):
        raise SystemExit("outcome row count invalid or mismatched")

    required_diag = [
        "funding_rows_total",
        "funding_files_found_count",
        "funding_symbols_with_files",
        "funding_rows_scanned_total",
        "funding_rows_joined_total",
        "funding_join_coverage_rate",
        "funding_missing_symbols",
        "funding_source_status_counts",
        "funding_zero_reason",
    ]
    missing_diag = [k for k in required_diag if k not in perf]
    if missing_diag:
        raise SystemExit(f"missing funding diagnostics: {missing_diag}")
    if perf.get("unique_outcome_id_count") != perf.get("outcome_rows_total"):
        raise SystemExit("duplicate outcome_id rows detected")
    if perf.get("duplicate_range_action_event_horizon_grid_sl_rows") != 0:
        raise SystemExit("duplicate composite outcome rows detected")
    print(
        json.dumps(
            {"review_pack_ok": True, "outcome_run_id": args.outcome_run_id, "run_kind": run_kind},
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
