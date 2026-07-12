from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from bybit_grid.backtest.neutral_grid.evidence import MEMBERS, canonical_json_bytes
from bybit_grid.backtest.neutral_grid.geometry import geometric_grid_levels_decimal
from bybit_grid.backtest.neutral_grid.scenarios import canonical_scenarios, replay_scenario

RUN = "neutral_sm_v1_synthetic_v2"


def _run_build(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    rep = tmp_path / "rep"
    pack = tmp_path / "pack.zip"
    r = subprocess.run(
        [sys.executable, "scripts/run_neutral_grid_synthetic_matrix.py", "--run-id", RUN, "--output-root", str(out), "--report-root", str(rep)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    b = subprocess.run(
        [sys.executable, "scripts/make_state_machine_review_pack.py", "--run-id", RUN, "--output-root", str(out), "--report-root", str(rep), "--pack-path", str(pack)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert b.returncode == 0, b.stdout + b.stderr
    return pack


def _check(pack: Path, *args: str) -> dict[str, object]:
    r = subprocess.run([sys.executable, "scripts/check_state_machine_review_pack.py", *args, str(pack)], text=True, capture_output=True, check=False)
    out = json.loads(r.stdout)
    out["returncode"] = r.returncode
    return out


def _tamper(pack: Path, dst: Path, member: str, data: bytes) -> Path:
    with zipfile.ZipFile(pack) as z:
        files = {n: z.read(n) for n in z.namelist()}
    files[member] = data
    man = json.loads(files["review_pack_manifest.json"])
    if member != "review_pack_manifest.json":
        man["sha256"][member] = hashlib.sha256(data).hexdigest()
        files["review_pack_manifest.json"] = canonical_json_bytes(man)
    with zipfile.ZipFile(dst, "w") as w:
        for name in MEMBERS:
            w.writestr(name, files[name])
    return dst


def test_exact_base_and_between_level_geometry():
    scenarios = {s.scenario_id: s for s in canonical_scenarios()}
    exact = scenarios["01_initial_exact_base"]
    levels = geometric_grid_levels_decimal(exact.config.lower_price, exact.config.upper_price, exact.config.grid_cell_number).levels
    matches = [i for i, level in enumerate(levels) if level == exact.config.base_price]
    assert len(matches) == 1
    result = replay_scenario(exact)
    assert matches[0] not in result.active_orders
    assert len([o for o in result.all_orders if o.activation_sequence_id == 0]) == exact.config.grid_cell_number
    between = scenarios["02_initial_between_levels"]
    between_levels = geometric_grid_levels_decimal(between.config.lower_price, between.config.upper_price, between.config.grid_cell_number).levels
    assert between.config.base_price not in between_levels


def test_expected_termination_reasons_match_replay():
    for scenario in canonical_scenarios():
        result = replay_scenario(scenario)
        actual = None if not result.terminated_bool else result.termination.termination_reason
        assert actual == scenario.expected_termination_reason


def test_valid_v2_pack_passes_and_v1_request_rejected(tmp_path: Path):
    pack = _run_build(tmp_path)
    assert _check(pack)["review_pack_ok"] is True
    rejected = _check(pack, "--run-id", "neutral_sm_v1_synthetic")
    assert rejected["returncode"] == 1
    assert rejected["error"] == "manifest_semantics_mismatch"


def test_manifest_extra_missing_and_duplicate_key_rejected(tmp_path: Path):
    pack = _run_build(tmp_path)
    with zipfile.ZipFile(pack) as z:
        man = json.loads(z.read("review_pack_manifest.json"))
    extra = dict(man, undeclared_claim=True)
    bad = _tamper(pack, tmp_path / "extra.zip", "review_pack_manifest.json", canonical_json_bytes(extra))
    assert _check(bad)["error"] == "manifest_key_set_mismatch"
    missing = dict(man)
    missing.pop("scenario_version")
    bad = _tamper(pack, tmp_path / "missing.zip", "review_pack_manifest.json", canonical_json_bytes(missing))
    assert _check(bad)["error"] == "manifest_key_set_mismatch"
    with zipfile.ZipFile(pack) as zf:
        raw = zf.read("review_pack_manifest.json").decode()
    dup_bytes = raw.replace('{"canonical_scenario_count":33', '{"canonical_scenario_count":33,"canonical_scenario_count":33', 1).encode()
    bad = _tamper(pack, tmp_path / "dup.zip", "review_pack_manifest.json", dup_bytes)
    assert _check(bad)["error"] in {"duplicate_json_key", "malformed_json"}


def test_report_and_canonical_byte_tampers_rejected(tmp_path: Path):
    pack = _run_build(tmp_path)
    with zipfile.ZipFile(pack) as z:
        risk = z.read("risk_budget_readiness_report.md")
        synthetic = z.read("synthetic_scenario_report.md")
        catalog = json.loads(z.read("scenario_catalog.json"))
        inputs = z.read("scenario_inputs.jsonl")
    cases = [
        ("risk_budget_readiness_report.md", risk + b"risk_budget_proven_bool = true\n"),
        ("risk_budget_readiness_report.md", risk + b"risk_budget_proven_bool = false\n"),
        ("synthetic_scenario_report.md", synthetic + b"all_scenarios_replay_match_bool = false\n"),
        ("risk_budget_readiness_report.md", risk + b"profitability_claims_present_bool = true\n"),
        ("synthetic_scenario_report.md", synthetic + b"live_authorized_bool = true\n"),
        ("scenario_catalog.json", json.dumps(catalog, indent=2, sort_keys=True).encode() + b"\n"),
        ("scenario_inputs.jsonl", inputs.replace(b"\n", b" \n", 1)),
        ("scenario_inputs.jsonl", inputs + b"\n"),
        ("scenario_inputs.jsonl", inputs.rstrip(b"\n")),
        ("scenario_inputs.jsonl", inputs.splitlines()[0].replace(b'{"scenario":', b'{"scenario":{},"scenario":', 1) + b"\n" + b"\n".join(inputs.splitlines()[1:]) + b"\n"),
    ]
    for i, (member, payload) in enumerate(cases):
        bad = _tamper(pack, tmp_path / f"bad-{i}.zip", member, payload)
        assert _check(bad)["returncode"] == 1


def test_changed_expected_termination_reason_and_valid_artifacts(tmp_path: Path):
    pack = _run_build(tmp_path)
    with zipfile.ZipFile(pack) as z:
        rows = [json.loads(line) for line in z.read("scenario_results.jsonl").splitlines()]
    rows[21]["normalized_result"]["termination"]["termination_reason"] = "upper_boundary"
    payload = b"".join(canonical_json_bytes(row) for row in rows)
    bad = _tamper(pack, tmp_path / "term.zip", "scenario_results.jsonl", payload)
    assert _check(bad)["returncode"] == 1
    assert subprocess.run([sys.executable, "scripts/check_no_live_execution.py"], text=True, capture_output=True).returncode == 0
