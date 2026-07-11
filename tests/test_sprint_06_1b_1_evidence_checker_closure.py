from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from bybit_grid.backtest.neutral_grid.evidence import MEMBERS

RUN = "neutral_sm_v1_synthetic"


def _run(tmp_path: Path):
    out = tmp_path / "out"
    rep = tmp_path / "rep"
    pack = tmp_path / "pack.zip"
    r = subprocess.run(
        [
            sys.executable,
            "scripts/run_neutral_grid_synthetic_matrix.py",
            "--run-id",
            RUN,
            "--output-root",
            str(out),
            "--report-root",
            str(rep),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return out, rep, pack


def _build(out, rep, pack, opt="--output"):
    r = subprocess.run(
        [
            sys.executable,
            "scripts/make_state_machine_review_pack.py",
            "--run-id",
            RUN,
            "--output-root",
            str(out),
            "--report-root",
            str(rep),
            opt,
            str(pack),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def _check(pack, *extra):
    return subprocess.run(
        [sys.executable, "scripts/check_state_machine_review_pack.py", *extra, str(pack)]
        if not extra
        else [sys.executable, "scripts/check_state_machine_review_pack.py", *extra],
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_output_pack_path_zip_and_positional(tmp_path: Path):
    out, rep, pack = _run(tmp_path)
    assert _build(out, rep, pack, "--output")["member_count"] == 12
    assert (
        json.loads(
            subprocess.run(
                [
                    sys.executable,
                    "scripts/check_state_machine_review_pack.py",
                    "--zip",
                    str(pack),
                    "--run-id",
                    RUN,
                ],
                text=True,
                capture_output=True,
            ).stdout
        )["review_pack_ok"]
        is True
    )
    pack2 = tmp_path / "pack2.zip"
    _build(out, rep, pack2, "--pack-path")
    assert (
        json.loads(
            subprocess.run(
                [sys.executable, "scripts/check_state_machine_review_pack.py", str(pack2)],
                text=True,
                capture_output=True,
            ).stdout
        )["review_pack_ok"]
        is True
    )


def test_missing_failures_are_strict_json(tmp_path: Path):
    r = subprocess.run(
        [
            sys.executable,
            "scripts/check_state_machine_review_pack.py",
            "--zip",
            str(tmp_path / "missing.zip"),
            "--run-id",
            RUN,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert (
        r.returncode == 1
        and "Traceback" not in r.stderr
        and json.loads(r.stdout)["review_pack_ok"] is False
    )
    r = subprocess.run(
        [
            sys.executable,
            "scripts/make_state_machine_review_pack.py",
            "--output",
            str(tmp_path / "x.zip"),
            "--output-root",
            str(tmp_path / "none"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert (
        r.returncode == 1
        and "Traceback" not in r.stderr
        and json.loads(r.stdout)["review_pack_ok"] is False
    )


def test_valid_counts_and_hash_mismatch(tmp_path: Path):
    out, rep, pack = _run(tmp_path)
    _build(out, rep, pack)
    with zipfile.ZipFile(pack) as z:
        assert len(z.read("scenario_inputs.jsonl").splitlines()) == 33
        assert len(z.read("scenario_results.jsonl").splitlines()) == 33
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(pack) as z, zipfile.ZipFile(bad, "w") as w:
        for n in z.namelist():
            w.writestr(n, z.read(n) + (b"x" if n == "scenario_catalog.json" else b""))
    r = subprocess.run(
        [sys.executable, "scripts/check_state_machine_review_pack.py", str(bad)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert r.returncode == 1 and json.loads(r.stdout)["error"] == "hash_mismatch"


def _tamper_rehash(src: Path, dst: Path, member: str, transform):
    with zipfile.ZipFile(src) as z:
        data = {n: z.read(n) for n in z.namelist()}
    data[member] = transform(data[member])
    man = json.loads(data["review_pack_manifest.json"])
    if member != "review_pack_manifest.json":
        man["sha256"][member] = hashlib.sha256(data[member]).hexdigest()
    data["review_pack_manifest.json"] = (
        json.dumps(man, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    with zipfile.ZipFile(dst, "w") as w:
        for n in MEMBERS:
            w.writestr(n, data[n])


def test_semantic_tamper_rehashed_is_rejected(tmp_path: Path):
    out, rep, pack = _run(tmp_path)
    _build(out, rep, pack)

    def tamper_result(b):
        rows = [json.loads(x) for x in b.splitlines()]
        rows[0]["normalized_result"]["scenario_id"] = "evil"
        return b"".join(
            (json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n").encode() for r in rows
        )

    def tamper_ledger(b):
        rows = [json.loads(x) for x in b.splitlines()]
        rows[0]["sequence_id"] = 999
        return b"".join(
            (json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n").encode() for r in rows
        )

    def tamper_audit(b):
        d = json.loads(b)
        d["scenario_audit_ok"] = False
        return (json.dumps(d, sort_keys=True, separators=(",", ":")) + "\n").encode()

    for member, fn in [
        ("scenario_results.jsonl", tamper_result),
        ("ledger_events.jsonl", tamper_ledger),
        ("scenario_audit.json", tamper_audit),
    ]:
        bad = tmp_path / f"{member}.zip"
        _tamper_rehash(pack, bad, member, fn)
        r = subprocess.run(
            [sys.executable, "scripts/check_state_machine_review_pack.py", str(bad)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert r.returncode == 1, (member, r.stdout)


def test_runner_failed_overwrites_stale_complete(tmp_path: Path):
    out, rep, pack = _run(tmp_path)
    r = subprocess.run(
        [
            sys.executable,
            "scripts/run_neutral_grid_synthetic_matrix.py",
            "--run-id",
            RUN,
            "--output-root",
            str(out),
            "--report-root",
            str(rep),
            "--fail-after-building-test-hook",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert r.returncode == 1
    status = json.loads((out / RUN / "state_machine_run_status.json").read_text())
    assert status["status"] == "failed"
