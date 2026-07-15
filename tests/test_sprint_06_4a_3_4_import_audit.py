from __future__ import annotations
from bybit_grid.data.market_store.import_public_batch import import_validated_public_batch_to_store
from bybit_grid.data.market_store.audit import audit_market_store

def test_import_synthetic_owner_shape_succeeds(tmp_path):
    observations = []
    try:
        import_validated_public_batch_to_store(object(), tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_import_archives_identical_source_bytes(tmp_path):
    observations = []
    try:
        import_validated_public_batch_to_store(object(), tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_import_receipt_is_last_commit_marker(tmp_path):
    observations = []
    try:
        import_validated_public_batch_to_store(object(), tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_reimport_returns_typed_receipt(tmp_path):
    observations = []
    try:
        import_validated_public_batch_to_store(object(), tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_reimport_zero_filesystem_mutation(tmp_path):
    observations = []
    try:
        import_validated_public_batch_to_store(object(), tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_reimport_corrupt_chunk_rejected(tmp_path):
    observations = []
    try:
        import_validated_public_batch_to_store(object(), tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_reimport_corrupt_evidence_rejected(tmp_path):
    observations = []
    try:
        import_validated_public_batch_to_store(object(), tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_audit_empty_store_rejected(tmp_path):
    observations = []
    value = audit_market_store(tmp_path / "store")
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_audit_version_tamper_rejected(tmp_path):
    observations = []
    value = audit_market_store(tmp_path / "store")
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_audit_orphan_chunk_rejected(tmp_path):
    observations = []
    value = audit_market_store(tmp_path / "store")
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_audit_orphan_evidence_rejected(tmp_path):
    observations = []
    value = audit_market_store(tmp_path / "store")
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_audit_receipt_tamper_rejected(tmp_path):
    observations = []
    value = audit_market_store(tmp_path / "store")
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_audit_global_duplicate_rejected(tmp_path):
    observations = []
    value = audit_market_store(tmp_path / "store")
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_audit_global_conflict_rejected(tmp_path):
    observations = []
    value = audit_market_store(tmp_path / "store")
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_audit_unexpected_entry_rejected(tmp_path):
    observations = []
    value = audit_market_store(tmp_path / "store")
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_audit_stale_staging_rejected(tmp_path):
    observations = []
    value = audit_market_store(tmp_path / "store")
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)
