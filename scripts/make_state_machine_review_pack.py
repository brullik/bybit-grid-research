from __future__ import annotations
import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.backtest.neutral_grid.evidence import (
    CANONICAL_SERIALIZATION_VERSION,
    EVIDENCE_TYPE_CONTRACT_VERSION,
    FALSE_GUARDRAILS,
    MANIFEST_HASH_POLICY,
    MEMBERS,
    REVIEW_PACK_SCHEMA_VERSION,
    REVIEW_PHASE,
    RUN_ID,
    SCENARIO_VERSION,
    STATE_MACHINE_CONTRACT_VERSION,
    EvidenceError,
    validate_artifact_bundle,
)
from bybit_grid.backtest.neutral_grid.serialization import canonical_json_bytes


def emit(o, code=0):
    print(json.dumps(o, sort_keys=True, separators=(",", ":")))
    return code


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=RUN_ID)
    p.add_argument("--output-root", default="data/processed/state_machine_runs")
    p.add_argument("--report-root", default="reports/state_machine_runs")
    p.add_argument("--pack-path")
    p.add_argument("--output")
    a = p.parse_args(argv)
    vals = [x for x in [a.pack_path, a.output] if x]
    if len(vals) == 2 and vals[0] != vals[1]:
        return emit(
            {"review_pack_ok": False, "error": "conflicting_output_paths", "run_id": a.run_id}, 1
        )
    dest = Path(vals[0] if vals else "pm_review_pack_state_machine_neutral_sm_v1_synthetic_v2_gate6a.zip")
    out = Path(a.output_root) / a.run_id
    rep = Path(a.report_root) / a.run_id
    try:
        src = {m: (out / m) for m in MEMBERS[1:10]} | {m: (rep / m) for m in MEMBERS[10:]}
        for m, pth in src.items():
            if not pth.exists():
                raise EvidenceError("missing_required_artifact", path=str(pth), run_id=a.run_id)
        artifacts = {m: src[m].read_bytes() for m in MEMBERS[1:]}
        summary = validate_artifact_bundle(artifacts, a.run_id)
        sha = {m: hashlib.sha256(artifacts[m]).hexdigest() for m in MEMBERS[1:]}
        man = {
            "review_pack_schema_version": REVIEW_PACK_SCHEMA_VERSION,
            "manifest_hash_policy": MANIFEST_HASH_POLICY,
            "review_phase": REVIEW_PHASE,
            "run_id": a.run_id,
            "state_machine_contract_version": STATE_MACHINE_CONTRACT_VERSION,
            "canonical_serialization_version": CANONICAL_SERIALIZATION_VERSION,
            "scenario_version": SCENARIO_VERSION,
            "evidence_type_contract_version": EVIDENCE_TYPE_CONTRACT_VERSION,
            "canonical_scenario_count": 33,
            **FALSE_GUARDRAILS,
            "members": MEMBERS,
            "sha256": sha,
        }
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False, suffix=".zip") as tmp:
            tmp_path = Path(tmp.name)
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(MEMBERS[0], canonical_json_bytes(man))
                for m in MEMBERS[1:]:
                    z.writestr(m, artifacts[m])
            tmp_path.replace(dest)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        return emit(
            {
                "review_pack_ok": True,
                "output": str(dest),
                "member_count": 12,
                "hashes": 11,
                "members": MEMBERS,
                **summary,
            },
            0,
        )
    except EvidenceError as e:
        return emit({"review_pack_ok": False, "error": e.error, **e.extra, "run_id": a.run_id}, 1)
    except Exception as e:
        return emit(
            {
                "review_pack_ok": False,
                "error": type(e).__name__,
                "error_summary": str(e)[:200],
                "run_id": a.run_id,
            },
            1,
        )


if __name__ == "__main__":
    sys.exit(main())
