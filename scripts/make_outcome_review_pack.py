from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.research.outcome_reporting import (
    generate_outcome_reports,
    generate_outcome_semantic_audit,
)

PACK_SCHEMA_VERSION = "outcome_review_pack_v2"
BASE = [
    "outcome_report.md",
    "outcome_quality_report.md",
    "outcome_semantic_audit.md",
    "outcome_summary.parquet",
    "outcome_quality_summary.parquet",
    "outcome_perf.json",
    "outcome_semantic_audit.json",
]


def infer_run_kind(rid: str, summary_dir: Path) -> str:
    return (
        "repair"
        if (summary_dir / "outcome_grid_serialization_repair_report.json").exists()
        or "repair" in rid
        else "native"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome-run-id", required=True)
    ap.add_argument("--run-kind", choices=["native", "repair"])
    args = ap.parse_args()
    rid = args.outcome_run_id
    perf = generate_outcome_reports(rid)
    audit = generate_outcome_semantic_audit(rid)
    if audit.get("semantic_audit_ok") is not True:
        raise SystemExit("semantic audit failed; refusing to create review pack")
    summary_dir = Path("data/processed/outcome_runs") / rid / "summary"
    report_dir = Path("reports/outcome_runs") / rid
    run_kind = args.run_kind or infer_run_kind(rid, summary_dir)
    required = list(BASE) + (
        ["outcome_grid_serialization_repair_report.json"] if run_kind == "repair" else []
    )
    locations = {
        name: (report_dir / name if name.endswith(".md") else summary_dir / name)
        for name in required
    }
    missing = [name for name, path in locations.items() if not path.exists()]
    if missing:
        raise SystemExit(f"missing required review-pack files: {missing}")
    manifest = {
        "outcome_run_id": rid,
        "pack_schema_version": PACK_SCHEMA_VERSION,
        "run_kind": run_kind,
        "members": sorted(required + ["review_pack_manifest.json"]),
        "outcome_rows_total": int(perf.get("outcome_rows_total", 0)),
        "semantic_audit_ok": bool(audit.get("semantic_audit_ok")),
        "created_at_utc": datetime.now(UTC).isoformat(),
    }
    manifest_path = summary_dir / "review_pack_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    out = Path(f"pm_review_pack_{rid}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, path in locations.items():
            z.write(path, name)
        z.write(manifest_path, "review_pack_manifest.json")
    print(
        json.dumps(
            {"review_pack_created": str(out), "run_kind": run_kind, "members": manifest["members"]},
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
