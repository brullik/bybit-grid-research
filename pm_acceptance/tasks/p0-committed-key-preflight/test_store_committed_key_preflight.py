from __future__ import annotations

import ast
import hashlib
import importlib
from pathlib import Path
from typing import Any


TASK_ID = "p0-committed-key-preflight"
SENTINEL = "committed_key_preflight_contract_unavailable"
CONTRACT_VERSION = "committed-key-preflight-v1"
MODULE_CONTRACT_NAME = "COMMITTED_KEY_PREFLIGHT_CONTRACT"
TEST_CONTRACT_NAME = "COMMITTED_KEY_PREFLIGHT_TEST_CONTRACT"
ORDINARY_TEST_PATH = "tests/test_store_committed_key_preflight.py"
ORDINARY_TEST_SHA256 = (
    "2477ebbc0f011521805a5e3787eff7629639f7226f030afcd337d91f33cafb02"
)
MODULE_PATHS = (
    "src/bybit_grid/data/market_store/models.py",
    "src/bybit_grid/data/market_store/import_public_batch.py",
    "src/bybit_grid/data/market_store/transaction.py",
)
REQUIRED_IMPLEMENTATION_PATHS = (*MODULE_PATHS, ORDINARY_TEST_PATH)
RED_REQUIRED_PATHS = REQUIRED_IMPLEMENTATION_PATHS
_modules_cache: dict[str, Any] | None = None


def _modules() -> dict[str, Any]:
    global _modules_cache
    if _modules_cache is None:
        _modules_cache = {
            "models": importlib.import_module(
                "bybit_grid.data.market_store.models"
            ),
            "import_public_batch": importlib.import_module(
                "bybit_grid.data.market_store.import_public_batch"
            ),
            "transaction": importlib.import_module(
                "bybit_grid.data.market_store.transaction"
            ),
        }
    return _modules_cache


def _root() -> Path:
    return Path(_modules()["transaction"].__file__).resolve().parents[4]


def _exact_assignment(path: Path, name: str) -> str | None:
    try:
        source = path.read_text(encoding="utf-8", errors="strict")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None
    values: list[str] = []
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == name
            and isinstance(statement.value, ast.Constant)
            and type(statement.value.value) is str
        ):
            values.append(statement.value.value)
    return values[0] if values == [CONTRACT_VERSION] else None


def _ordinary_contract() -> tuple[str, str] | None:
    path = _root() / ORDINARY_TEST_PATH
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if _exact_assignment(path, TEST_CONTRACT_NAME) != CONTRACT_VERSION:
        return None
    return CONTRACT_VERSION, hashlib.sha256(raw).hexdigest()


def _available() -> None:
    modules = _modules()
    for key, path in zip(modules, MODULE_PATHS, strict=True):
        module = modules[key]
        if getattr(module, MODULE_CONTRACT_NAME, None) != CONTRACT_VERSION:
            raise RuntimeError(SENTINEL)
        module_path = Path(module.__file__).resolve()
        if _exact_assignment(module_path, MODULE_CONTRACT_NAME) != CONTRACT_VERSION:
            raise RuntimeError(SENTINEL)
        if module_path != (_root() / path).resolve():
            raise RuntimeError(SENTINEL)
    if _ordinary_contract() != (CONTRACT_VERSION, ORDINARY_TEST_SHA256):
        raise RuntimeError(SENTINEL)


def test_contract_markers_and_exact_implementation_scope() -> None:
    _available()
    assert RED_REQUIRED_PATHS == REQUIRED_IMPLEMENTATION_PATHS
    assert all((_root() / path).is_file() for path in REQUIRED_IMPLEMENTATION_PATHS)
    assert _ordinary_contract() == (CONTRACT_VERSION, ORDINARY_TEST_SHA256)
    assert (
        hashlib.sha256(ORDINARY_TEST_SOURCE.encode("utf-8")).hexdigest()
        == ORDINARY_TEST_SHA256
    )


ORDINARY_TEST_SOURCE = r'''from __future__ import annotations

import hashlib
import shutil
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from bybit_grid.data.market_store import import_public_batch, models, transaction
from bybit_grid.data.market_store.audit import audit_market_store
from bybit_grid.data.market_store.canonical import canonical_json_bytes
from bybit_grid.data.market_store.import_public_batch import (
    ValidatedPublicBatchEvidence,
    import_validated_public_batch_to_store,
)
from bybit_grid.data.market_store.inventory import snapshot_tree
from bybit_grid.data.market_store.models import (
    STORE_SCHEMA_VERSION,
    ImportPreflightPlan,
    MarketDatasetKind,
    MarketStoreError,
    StoreImportReceipt,
)
from bybit_grid.data.market_store.reader import _chunk_dirs, read_dataset


COMMITTED_KEY_PREFLIGHT_TEST_CONTRACT = "committed-key-preflight-v1"
CONTRACT = "committed-key-preflight-v1"
SENTINEL = "committed_key_preflight_contract_unavailable"
KINDS = tuple(MarketDatasetKind)
BASE_TIME_MS = 1_704_067_200_000
_SHARED_STATE = None


def _available() -> None:
    markers = (
        getattr(models, "COMMITTED_KEY_PREFLIGHT_CONTRACT", None),
        getattr(import_public_batch, "COMMITTED_KEY_PREFLIGHT_CONTRACT", None),
        getattr(transaction, "COMMITTED_KEY_PREFLIGHT_CONTRACT", None),
    )
    if markers != (CONTRACT, CONTRACT, CONTRACT):
        pytest.fail(SENTINEL)


def _common(run_id: str, source_sha256: str, plan_id: str) -> dict:
    return {
        "source_run_id": run_id,
        "source_review_pack_sha256": source_sha256,
        "source_plan_id": plan_id,
        "source_name": "synthetic_committed_key_contract",
        "storage_schema_version": STORE_SCHEMA_VERSION,
    }


def _dataset_rows(
    run_id: str,
    source_sha256: str,
    *,
    time_offset_ms: int = 0,
    price_delta: Decimal = Decimal("0"),
):
    timestamp = BASE_TIME_MS + time_offset_ms
    price = Decimal("100") + price_delta
    instrument = {
        "snapshot_server_time_ms": timestamp,
        "category": "linear",
        "symbol": "BTCUSDT",
        "contract_type": "LinearPerpetual",
        "status": "Trading",
        "base_coin": "BTC",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "launch_time_ms": 0,
        "delivery_time_ms": 0,
        "is_pre_listing": False,
        "funding_interval_minutes": 480,
        "tick_size": Decimal("0.1"),
        "qty_step": Decimal("0.001"),
        "min_order_qty": Decimal("0.001"),
        "min_notional_value": Decimal("5"),
        "min_leverage": Decimal("1"),
        "max_leverage": Decimal("100"),
        "leverage_step": Decimal("0.01"),
        **_common(run_id, source_sha256, "instrument_primary_1000"),
    }
    trade = {
        "category": "linear",
        "symbol": "BTCUSDT",
        "open_time_ms": timestamp,
        "open": price,
        "high": price + Decimal("1"),
        "low": price - Decimal("1"),
        "close": price,
        "volume": Decimal("1"),
        "turnover": price,
        "closed_bool": True,
        **_common(run_id, source_sha256, "trade_primary_1000"),
    }
    mark = {
        "category": "linear",
        "symbol": "BTCUSDT",
        "open_time_ms": timestamp,
        "open": price,
        "high": price + Decimal("1"),
        "low": price - Decimal("1"),
        "close": price,
        "closed_bool": True,
        **_common(run_id, source_sha256, "mark_primary_1000"),
    }
    funding = {
        "category": "linear",
        "symbol": "BTCUSDT",
        "funding_time_ms": timestamp,
        "funding_rate": Decimal("0.0001") + price_delta / Decimal("1000000"),
        **_common(run_id, source_sha256, "funding_primary_backward_200"),
    }
    return (
        (MarketDatasetKind.instrument_snapshot, (instrument,)),
        (MarketDatasetKind.trade_kline_1m, (trade,)),
        (MarketDatasetKind.mark_kline_1m, (mark,)),
        (MarketDatasetKind.funding_rate, (funding,)),
    )


def _evidence(
    run_id: str,
    *,
    time_offset_ms: int = 0,
    price_delta: Decimal = Decimal("0"),
    source_bytes: bytes | None = None,
) -> ValidatedPublicBatchEvidence:
    archive = (
        source_bytes
        if source_bytes is not None
        else f"synthetic-review-pack:{run_id}".encode("ascii")
    )
    source_sha256 = hashlib.sha256(archive).hexdigest()
    planned_rows = _dataset_rows(
        run_id,
        source_sha256,
        time_offset_ms=time_offset_ms,
        price_delta=price_delta,
    )
    return ValidatedPublicBatchEvidence(
        run_id,
        source_sha256,
        object(),
        MappingProxyType({"planned_rows": planned_rows}),
        archive,
    )


def _project(evidence: ValidatedPublicBatchEvidence):
    return evidence.reconstructed["planned_rows"]


def _synthetic_revalidate(evidence):
    if type(evidence) is not ValidatedPublicBatchEvidence:
        raise MarketStoreError("evidence_type_invalid")
    if type(evidence.source_bytes) is not bytes or not evidence.source_bytes:
        raise MarketStoreError("source_bytes_invalid")
    if hashlib.sha256(evidence.source_bytes).hexdigest() != evidence.review_pack_sha256:
        raise MarketStoreError("source_sha256_mismatch")
    return evidence


def _install_synthetic_boundaries(monkeypatch) -> None:
    monkeypatch.setattr(import_public_batch, "_project_planned_rows", _project)
    monkeypatch.setattr(
        import_public_batch,
        "revalidate_validated_public_batch_evidence",
        _synthetic_revalidate,
    )


def _shared_state(tmp_path: Path, monkeypatch):
    global _SHARED_STATE
    _install_synthetic_boundaries(monkeypatch)
    if _SHARED_STATE is None:
        root = tmp_path / "shared"
        root.mkdir()
        accepted = _evidence("accepted_source")
        conflicting = _evidence("conflicting_source")
        pristine = root / "pristine_store"
        receipt = import_validated_public_batch_to_store(accepted, pristine)
        assert audit_market_store(pristine).ok
        _SHARED_STATE = (pristine, receipt, accepted, conflicting)
    return _SHARED_STATE


def _fresh_store(tmp_path: Path, monkeypatch):
    pristine, receipt, accepted, conflicting = _shared_state(tmp_path, monkeypatch)
    store = tmp_path / "store"
    shutil.copytree(pristine, store)
    return store, receipt, accepted, conflicting


def _transaction_siblings(store: Path) -> tuple[str, ...]:
    prefix = store.name + ".txn-"
    return tuple(
        sorted(
            path.name
            for path in store.parent.iterdir()
            if path.name.startswith(prefix)
        )
    )


def _parent_inventory(store: Path):
    return snapshot_tree(store.parent)


def _assert_unchanged(store: Path, before) -> None:
    assert _parent_inventory(store) == before
    assert _transaction_siblings(store) == ()


def _single_committed_row(store: Path, kind: MarketDatasetKind):
    rows = read_dataset(store, kind)
    assert rows
    return rows[0]


def _forbid_uuid() -> None:
    pytest.fail("transaction UUID requested before prewrite validation completed")


def test_contract_markers_and_exact_public_surface() -> None:
    _available()
    assert tuple(kind.value for kind in KINDS) == (
        "instrument_snapshot",
        "trade_kline_1m",
        "mark_kline_1m",
        "funding_rate",
    )
    assert callable(import_public_batch.revalidate_validated_public_batch_evidence)
    assert callable(transaction.build_import_preflight_plan)
    assert callable(transaction.commit_import_preflight_plan)


def test_platform_path_reaches_preflight_without_creating_store_root(
    tmp_path: Path, monkeypatch
) -> None:
    _available()
    _install_synthetic_boundaries(monkeypatch)
    store = tmp_path / "never_created_store"
    plan = transaction.build_import_preflight_plan(_evidence("path_contract"), store)
    assert type(plan) is ImportPreflightPlan
    assert plan.store_root == store
    assert not store.exists()


def test_source_hash_revalidation_is_typed_and_prewrite(
    tmp_path: Path, monkeypatch
) -> None:
    _available()
    evidence = _evidence("forged_source")
    forged = replace(evidence, source_bytes=evidence.source_bytes + b"-forged")
    before = snapshot_tree(tmp_path)
    monkeypatch.setattr(
        import_public_batch,
        "load_validated_public_replay_batch_from_review_pack_bytes",
        lambda *_args, **_kwargs: pytest.fail("loader reached before source hash gate"),
    )
    with pytest.raises(MarketStoreError) as exc_info:
        import_public_batch.revalidate_validated_public_batch_evidence(forged)
    assert str(exc_info.value) == "source_sha256_mismatch"
    assert snapshot_tree(tmp_path) == before


def test_projection_revalidation_rejects_forged_instance(monkeypatch) -> None:
    _available()
    canonical = _evidence("canonical_projection")
    planned = list(_project(canonical))
    kind, rows = planned[1]
    altered = dict(rows[0])
    altered["close"] = Decimal("101")
    planned[1] = (kind, (altered,))
    forged = replace(
        canonical,
        reconstructed=MappingProxyType({"planned_rows": tuple(planned)}),
    )
    monkeypatch.setattr(import_public_batch, "_project_planned_rows", _project)
    monkeypatch.setattr(
        import_public_batch,
        "load_validated_public_replay_batch_from_review_pack_bytes",
        lambda *_args, **_kwargs: canonical,
    )
    with pytest.raises(MarketStoreError) as exc_info:
        import_public_batch.revalidate_validated_public_batch_evidence(forged)
    assert str(exc_info.value) == "evidence_projection_mismatch"


def test_exact_accepted_evidence_reimport_is_typed_noop(
    tmp_path: Path, monkeypatch
) -> None:
    _available()
    store, receipt, accepted, _ = _fresh_store(tmp_path, monkeypatch)
    before = _parent_inventory(store)
    monkeypatch.setattr(transaction.uuid, "uuid4", _forbid_uuid)
    plan = transaction.build_import_preflight_plan(accepted, store)
    returned = transaction.commit_import_preflight_plan(
        plan, fail_at="before_transaction_root"
    )
    assert returned == receipt
    assert type(returned) is StoreImportReceipt
    _assert_unchanged(store, before)


def test_receipt_appearing_after_plan_is_still_exact_typed_noop(
    tmp_path: Path, monkeypatch
) -> None:
    _available()
    _, _, accepted, _ = _shared_state(tmp_path, monkeypatch)
    store = tmp_path / "late_receipt_store"
    plan = transaction.build_import_preflight_plan(accepted, store)
    receipt = import_validated_public_batch_to_store(accepted, store)
    before = _parent_inventory(store)
    monkeypatch.setattr(transaction.uuid, "uuid4", _forbid_uuid)
    returned = transaction.commit_import_preflight_plan(plan)
    assert returned == receipt
    assert type(returned) is StoreImportReceipt
    _assert_unchanged(store, before)


def test_preflight_rejects_real_different_evidence_key_conflict(
    tmp_path: Path, monkeypatch
) -> None:
    _available()
    store, _, _, conflicting = _fresh_store(tmp_path, monkeypatch)
    before = _parent_inventory(store)
    with pytest.raises(MarketStoreError) as exc_info:
        transaction.build_import_preflight_plan(conflicting, store)
    assert str(exc_info.value) == "store_row_conflict"
    _assert_unchanged(store, before)


def test_stale_plan_rechecks_committed_keys_before_transaction_root(
    tmp_path: Path, monkeypatch
) -> None:
    _available()
    _, _, accepted, conflicting = _shared_state(tmp_path, monkeypatch)
    store = tmp_path / "stale_plan_store"
    stale = transaction.build_import_preflight_plan(conflicting, store)
    import_validated_public_batch_to_store(accepted, store)
    before = _parent_inventory(store)
    monkeypatch.setattr(transaction.uuid, "uuid4", _forbid_uuid)
    with pytest.raises(MarketStoreError) as exc_info:
        transaction.commit_import_preflight_plan(stale)
    assert str(exc_info.value) == "store_row_conflict"
    _assert_unchanged(store, before)


@pytest.mark.parametrize("kind", KINDS, ids=lambda kind: kind.value)
def test_equal_committed_rows_are_rejected_for_every_dataset(
    tmp_path: Path, monkeypatch, kind: MarketDatasetKind
) -> None:
    _available()
    store, _, _, conflicting = _fresh_store(tmp_path, monkeypatch)
    committed = _single_committed_row(store, kind)
    monkeypatch.setattr(
        import_public_batch,
        "_project_planned_rows",
        lambda _evidence: ((kind, (committed,)),),
    )
    before = _parent_inventory(store)
    with pytest.raises(MarketStoreError) as exc_info:
        transaction.build_import_preflight_plan(conflicting, store)
    assert str(exc_info.value) == "duplicate_committed_key"
    _assert_unchanged(store, before)


@pytest.mark.parametrize("kind", KINDS, ids=lambda kind: kind.value)
def test_different_committed_rows_are_rejected_for_every_dataset(
    tmp_path: Path, monkeypatch, kind: MarketDatasetKind
) -> None:
    _available()
    store, _, _, conflicting = _fresh_store(tmp_path, monkeypatch)
    incoming = dict(_single_committed_row(store, kind))
    incoming["source_run_id"] = conflicting.run_id
    incoming["source_review_pack_sha256"] = conflicting.review_pack_sha256
    monkeypatch.setattr(
        import_public_batch,
        "_project_planned_rows",
        lambda _evidence: ((kind, (incoming,)),),
    )
    before = _parent_inventory(store)
    with pytest.raises(MarketStoreError) as exc_info:
        transaction.build_import_preflight_plan(conflicting, store)
    assert str(exc_info.value) == "store_row_conflict"
    _assert_unchanged(store, before)


def test_nonoverlapping_second_import_remains_valid(
    tmp_path: Path, monkeypatch
) -> None:
    _available()
    store, _, _, _ = _fresh_store(tmp_path, monkeypatch)
    nonoverlapping = _evidence("nonoverlapping_source", time_offset_ms=60_000)
    receipt = import_validated_public_batch_to_store(nonoverlapping, store)
    assert type(receipt) is StoreImportReceipt
    assert audit_market_store(store).ok
    for kind in KINDS:
        assert len(read_dataset(store, kind)) == 2
    assert _transaction_siblings(store) == ()


def test_nonexact_existing_receipt_graph_is_not_a_noop(
    tmp_path: Path, monkeypatch
) -> None:
    _available()
    store, _, accepted, _ = _fresh_store(tmp_path, monkeypatch)
    planned = list(_project(accepted))
    kind, rows = planned[1]
    altered = dict(rows[0])
    altered["close"] = Decimal("101")
    planned[1] = (kind, (altered,))
    forged = replace(
        accepted,
        reconstructed=MappingProxyType({"planned_rows": tuple(planned)}),
    )
    before = _parent_inventory(store)
    with pytest.raises(MarketStoreError) as exc_info:
        transaction.build_import_preflight_plan(forged, store)
    assert str(exc_info.value) == "receipt_mismatch"
    _assert_unchanged(store, before)


def test_conflicting_immutable_chunk_path_fails_before_transaction_root(
    tmp_path: Path, monkeypatch
) -> None:
    _available()
    store, _, _, conflicting = _fresh_store(tmp_path, monkeypatch)
    kind = MarketDatasetKind.trade_kline_1m
    incoming = dict(read_dataset(store, kind)[-1])
    incoming["open_time_ms"] += 60_000
    incoming["source_run_id"] = conflicting.run_id
    incoming["source_review_pack_sha256"] = conflicting.review_pack_sha256
    monkeypatch.setattr(
        import_public_batch,
        "_project_planned_rows",
        lambda _evidence: ((kind, (incoming,)),),
    )
    plan = transaction.build_import_preflight_plan(conflicting, store)
    assert len(plan.chunks) == 1
    existing_relative = _chunk_dirs(store, kind)[0].relative_to(store).as_posix()
    chunk = plan.chunks[0]
    forged_manifest = replace(chunk.manifest, relative_path=existing_relative)
    forged_chunk = replace(
        chunk,
        manifest=forged_manifest,
        reuse_existing_bool=False,
    )
    forged_receipt = replace(plan.receipt, chunks=(forged_manifest,))
    conflicting_plan = replace(
        plan,
        chunks=(forged_chunk,),
        receipt=forged_receipt,
        receipt_bytes=canonical_json_bytes(forged_receipt),
    )
    before = _parent_inventory(store)
    monkeypatch.setattr(transaction.uuid, "uuid4", _forbid_uuid)
    with pytest.raises(MarketStoreError) as exc_info:
        transaction.commit_import_preflight_plan(conflicting_plan)
    assert str(exc_info.value) == "immutable_chunk_path_conflict"
    _assert_unchanged(store, before)
'''

if (
    hashlib.sha256(ORDINARY_TEST_SOURCE.encode("utf-8")).hexdigest()
    != ORDINARY_TEST_SHA256
):
    raise RuntimeError(SENTINEL)

_FROZEN_AVAILABLE = _available
exec(compile(ORDINARY_TEST_SOURCE, ORDINARY_TEST_PATH, "exec"), globals())
_available = _FROZEN_AVAILABLE
