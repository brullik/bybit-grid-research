from __future__ import annotations
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.backtest.neutral_grid.scenario_audit import scenario_input_record
from bybit_grid.backtest.neutral_grid.scenarios import canonical_scenarios, SCENARIO_IDS

MEMBERS = [
    "review_pack_manifest.json",
    "state_machine_run_status.json",
    "state_machine_contract_audit.json",
    "scenario_catalog.json",
    "scenario_inputs.jsonl",
    "scenario_results.jsonl",
    "ledger_events.jsonl",
    "completed_cycles.jsonl",
    "scenario_audit.json",
    "reproducibility_audit.json",
    "synthetic_scenario_report.md",
    "risk_budget_readiness_report.md",
]


def emit(o, code):
    print(json.dumps(o, sort_keys=True, separators=(",", ":")))
    return code


def bad(msg):
    return emit({"review_pack_ok": False, "error": msg}, 1)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("pack_path")
    a = p.parse_args(argv)
    try:
        with zipfile.ZipFile(a.pack_path) as z:
            names = z.namelist()
            if len(names) != len(set(names)):
                return bad("duplicate member")
            if names != MEMBERS:
                return bad("missing extra or ordered member mismatch")
            for n in names:
                pp = PurePosixPath(n)
                if pp.is_absolute() or ".." in pp.parts or n.endswith("/"):
                    return bad("forbidden member path")
            data = {n: z.read(n) for n in names}
        man = json.loads(data["review_pack_manifest.json"])
        if "review_pack_manifest.json" in man.get("sha256", {}):
            return bad("manifest self hash forbidden")
        if man.get("members") != MEMBERS:
            return bad("manifest members mismatch")
        if set(man.get("sha256", {})) != set(MEMBERS[1:]):
            return bad("hash key set mismatch")
        for m in MEMBERS[1:]:
            if hashlib.sha256(data[m]).hexdigest() != man["sha256"][m]:
                return bad(f"hash mismatch {m}")
        status = json.loads(data["state_machine_run_status.json"])
        scen = json.loads(data["scenario_catalog.json"])
        aud = json.loads(data["scenario_audit.json"])
        rep = data["risk_budget_readiness_report.md"].decode()
        if status.get("status") != "complete" or status.get("run_id") != man.get("run_id"):
            return bad("status/run mismatch")
        if scen.get("scenario_ids") != list(SCENARIO_IDS):
            return bad("scenario ids mismatch")
        inputs = [
            json.loads(line) for line in data["scenario_inputs.jsonl"].decode().splitlines() if line
        ]
        if len(inputs) != 33:
            return bad("input row count mismatch")
        expected = {
            scenario_input_record(s)["scenario_id"]: scenario_input_record(s)[
                "scenario_input_sha256"
            ]
            for s in canonical_scenarios()
        }
        if {r["scenario_id"]: r["scenario_input_sha256"] for r in inputs} != expected:
            return bad("input hashes mismatch")
        for fname in ["scenario_results.jsonl", "ledger_events.jsonl", "completed_cycles.jsonl"]:
            for line in data[fname].decode().splitlines():
                json.loads(line)
        if not aud.get("scenario_audit_ok"):
            return bad("scenario audit not ok")
        for text in [
            "risk_budget_proven_bool = false",
            "sufficient_for_parameter_selection_bool = false",
            "live_execution_present_bool = false",
        ]:
            if text not in rep:
                return bad("risk guardrail missing")
        return emit(
            {
                "review_pack_ok": True,
                "member_count": 12,
                "hashes_verified": 11,
                "canonical_scenario_count": 33,
                "risk_budget_proven_bool": False,
                "parameter_selection_authorized_bool": False,
                "live_authorized_bool": False,
            },
            0,
        )
    except FileNotFoundError:
        return bad("missing zip")
    except zipfile.BadZipFile:
        return bad("bad zip")
    except Exception as e:
        return bad(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(main())
