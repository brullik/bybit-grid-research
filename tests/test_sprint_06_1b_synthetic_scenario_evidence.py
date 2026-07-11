from __future__ import annotations
import json
import subprocess
import sys
import zipfile
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from types import MappingProxyType
import pytest
from bybit_grid.backtest.neutral_grid import (
    EventType,
    FundingEvent,
    LiquidityRole,
    ManualTerminationAction,
    NeutralGridConfig,
    NeutralGridReferenceEngine,
    PriceEvent,
    QuantitySource,
    audit_simulation_result,
    canonical_scenarios,
    replay_scenario,
)
from bybit_grid.backtest.neutral_grid.scenario_audit import (
    audit_scenario_evidence,
    scenario_input_record,
)
from bybit_grid.backtest.neutral_grid.serialization import (
    canonical_json_bytes,
    canonical_sha256,
    normalize,
)


def cfg():
    return NeutralGridConfig(
        "linear",
        "BTCUSDT",
        D("80"),
        D("120"),
        D("100"),
        4,
        D("1"),
        QuantitySource.synthetic_explicit,
        D("1"),
        D("0.001"),
        D("0.002"),
        LiquidityRole.maker,
        LiquidityRole.taker,
        D("10"),
        D("70"),
        D("130"),
    )


def test_sequence_zero_rejected_and_manual_no_mutation():
    with pytest.raises(ValueError):
        PriceEvent(0, 0, D("1"))
    with pytest.raises(ValueError):
        FundingEvent(0, 0, D("1"), D("0"))
    with pytest.raises(ValueError):
        ManualTerminationAction(0, 0, D("1"))
    e = NeutralGridReferenceEngine(cfg())
    before = e.result()
    with pytest.raises(ValueError):
        e.terminate_now(0, 0, D("100"))
    assert e.result() == before


def test_active_bijection_and_fail_closed():
    e = NeutralGridReferenceEngine(cfg())
    r = e.result()
    ao = dict(r.active_orders)
    ao.pop(next(iter(ao)))
    assert not audit_simulation_result(replace(r, active_orders=MappingProxyType(ao))).passed_bool
    orders = list(r.all_orders)
    orders[0] = replace(orders[0], order_id="")
    assert not audit_simulation_result(replace(r, all_orders=tuple(orders))).passed_bool
    orders = list(r.all_orders)
    orders[0] = replace(orders[0], level_index=True)
    assert not audit_simulation_result(replace(r, all_orders=tuple(orders))).passed_bool


def test_linked_cycle_and_termination_tamper_rejected():
    e = NeutralGridReferenceEngine(cfg())
    e.process(PriceEvent(1, 1, D("80")))
    e.process(PriceEvent(2, 2, D("100")))
    r = e.result()
    assert audit_simulation_result(r).passed_bool
    orders = [
        replace(o, linked_open_fill_id="evt-missing") if o.linked_open_fill_id else o
        for o in r.all_orders
    ]
    assert not audit_simulation_result(replace(r, all_orders=tuple(orders))).passed_bool
    cycles = [replace(r.completed_cycles[0], open_level_index=99)]
    assert not audit_simulation_result(replace(r, completed_cycles=tuple(cycles))).passed_bool
    led = list(r.ledger)
    led[0] = replace(led[0], completed_grid_cycle_gross_usdt=D("1"))
    assert not audit_simulation_result(replace(r, ledger=tuple(led))).passed_bool
    e2 = NeutralGridReferenceEngine(cfg())
    e2.terminate_now(1, 1, D("100"))
    tr = e2.result()
    assert not audit_simulation_result(
        replace(tr, termination=replace(tr.termination, termination_reason=None))
    ).passed_bool
    assert not audit_simulation_result(
        replace(tr, termination=replace(tr.termination, termination_execution_price=D("1")))
    ).passed_bool


def test_catalog_replay_serialization():
    sc = canonical_scenarios()
    assert [s.scenario_id for s in sc] == list(
        __import__(
            "bybit_grid.backtest.neutral_grid.scenarios", fromlist=["SCENARIO_IDS"]
        ).SCENARIO_IDS
    )
    assert len(sc) == 33
    for s in sc:
        seq = [a.sequence_id for a in s.actions]
        assert seq == sorted(seq) and len(seq) == len(set(seq)) and all(x >= 1 for x in seq)
        r = replay_scenario(s)
        assert audit_simulation_result(r).passed_bool
        if s.expected_termination_reason:
            assert r.terminated_bool and r.signed_position == 0 and r.average_entry is None
    assert audit_scenario_evidence(sc).scenario_audit_ok
    b1 = canonical_json_bytes([scenario_input_record(s) for s in sc])
    b2 = canonical_json_bytes([scenario_input_record(s) for s in sc])
    assert b1 == b2 and canonical_sha256(normalize(sc[0]))


def test_same_timestamp_and_repeated_same_price():
    s28 = canonical_scenarios()[27]
    s29 = canonical_scenarios()[28]
    assert normalize(replay_scenario(s28)) != normalize(replay_scenario(s29))
    r = replay_scenario(canonical_scenarios()[26])
    assert len([e for e in r.ledger if e.event_type is EventType.grid_fill]) == 1


def test_runner_pack_checker_tmp(tmp_path: Path):
    out = tmp_path / "out"
    rep = tmp_path / "rep"
    pack = tmp_path / "pack.zip"
    cmd = [
        sys.executable,
        "scripts/run_neutral_grid_synthetic_matrix.py",
        "--run-id",
        "neutral_sm_v1_synthetic",
        "--output-root",
        str(out),
        "--report-root",
        str(rep),
    ]
    assert subprocess.run(cmd, check=False).returncode == 0
    status = json.loads(
        (out / "neutral_sm_v1_synthetic" / "state_machine_run_status.json").read_text()
    )
    assert status["status"] == "complete"
    build = [
        sys.executable,
        "scripts/make_state_machine_review_pack.py",
        "--run-id",
        "neutral_sm_v1_synthetic",
        "--output-root",
        str(out),
        "--report-root",
        str(rep),
        "--pack-path",
        str(pack),
    ]
    assert subprocess.run(build, check=False).returncode == 0
    chk = subprocess.run(
        [sys.executable, "scripts/check_state_machine_review_pack.py", str(pack)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert chk.returncode == 0 and json.loads(chk.stdout)["review_pack_ok"] is True
    missing = subprocess.run(
        [
            sys.executable,
            "scripts/check_state_machine_review_pack.py",
            str(tmp_path / "missing.zip"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode == 1 and json.loads(missing.stdout)["review_pack_ok"] is False
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(pack) as z, zipfile.ZipFile(bad, "w") as w:
        for n in z.namelist():
            w.writestr(n, z.read(n) + (b"x" if n == "scenario_catalog.json" else b""))
    assert (
        subprocess.run(
            [sys.executable, "scripts/check_state_machine_review_pack.py", str(bad)],
            capture_output=True,
            check=False,
        ).returncode
        == 1
    )


FORBIDDEN_GENERATED_SUFFIXES = {".zip", ".jsonl", ".parquet", ".db", ".sqlite", ".duckdb"}
SOURCE_HYGIENE_DIRS = ("src", "scripts", "tests", "docs", "config")


def find_forbidden_generated_source_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for rel in SOURCE_HYGIENE_DIRS:
        base = root / rel
        if base.exists():
            found.extend(
                p
                for p in base.rglob("*")
                if p.is_file() and p.suffix in FORBIDDEN_GENERATED_SUFFIXES
            )
    try:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=root, text=True, capture_output=True, check=False
        )
    except (FileNotFoundError, OSError):
        tracked = None
    if tracked and tracked.returncode == 0:
        for line in tracked.stdout.splitlines():
            p = root / line
            if p.suffix in FORBIDDEN_GENERATED_SUFFIXES and p not in found:
                found.append(p)
    return sorted(found)


def test_no_forbidden_generated_repo_files():
    assert not find_forbidden_generated_source_files(Path("."))


def test_source_hygiene_ignores_operator_root_zip_and_data_jsonl(tmp_path: Path):
    (tmp_path / "pm_review_pack_old.zip").write_bytes(b"old")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "owner.jsonl").write_text("{}\n")
    (tmp_path / "src").mkdir()
    assert find_forbidden_generated_source_files(tmp_path) == []


def test_source_hygiene_rejects_generated_files_in_source_dirs(tmp_path: Path):
    bads = []
    for rel in ["src/a.zip", "scripts/a.jsonl", "tests/a.parquet", "docs/a.db", "config/a.duckdb"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
        bads.append(p)
    assert find_forbidden_generated_source_files(tmp_path) == sorted(bads)
