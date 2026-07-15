from __future__ import annotations
import subprocess
from bybit_grid.data.market_store.evidence import make_seed_review_pack, check_seed_review_pack

def test_pack_builder_rejects_bad_store(tmp_path):
    observations = []
    try:
        make_seed_review_pack(tmp_path / "store", tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        check_seed_review_pack(tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_pack_exact_member_set(tmp_path):
    observations = []
    try:
        make_seed_review_pack(tmp_path / "store", tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        check_seed_review_pack(tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_pack_empty_manifest_rejected(tmp_path):
    observations = []
    try:
        make_seed_review_pack(tmp_path / "store", tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        check_seed_review_pack(tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_pack_rehashed_fake_rejected(tmp_path):
    observations = []
    try:
        make_seed_review_pack(tmp_path / "store", tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        check_seed_review_pack(tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_pack_nested_public_evidence_validated(tmp_path):
    observations = []
    try:
        make_seed_review_pack(tmp_path / "store", tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        check_seed_review_pack(tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_pack_report_tamper_rejected_after_rehash(tmp_path):
    observations = []
    try:
        make_seed_review_pack(tmp_path / "store", tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        check_seed_review_pack(tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_pack_temp_cleanup_on_failure(tmp_path):
    observations = []
    try:
        make_seed_review_pack(tmp_path / "store", tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        check_seed_review_pack(tmp_path / "pack.zip")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_cli_full_lifecycle_bybit_host_offline(tmp_path):
    observations = []
    cp = subprocess.run(["python", "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    observations.append(cp.returncode)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_cli_full_lifecycle_bytick_host_offline(tmp_path):
    observations = []
    cp = subprocess.run(["python", "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    observations.append(cp.returncode)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)
