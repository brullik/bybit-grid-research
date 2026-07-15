from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from types import MappingProxyType
from .models import (
    STORE_SCHEMA_VERSION,
    MarketDatasetKind,
    MarketStoreError,
    StoreImportReceipt,
    StoreChunkManifest,
)
from .writer import write_chunk_atomic
from .canonical import canonical_json_bytes
from .paths import receipt_rel, evidence_rel
from .planner import partition_validated_rows
from bybit_grid.data.public_batch.evidence import validate_review_pack
from bybit_grid.data.public_batch.reconstruct import records_from_jsonl, reconstruct_from_records
from bybit_grid.data.public_batch.recording import strict_json_loads


@dataclass(frozen=True)
class ValidatedPublicBatchEvidence:
    run_id: str
    review_pack_sha256: str
    batch: object
    reconstructed: MappingProxyType
    source_bytes: bytes


def load_validated_public_replay_batch_from_review_pack(
    path: Path, *, expected_run_id: str, expected_sha256: str | None = None
):
    b = Path(path).read_bytes()
    sha = hashlib.sha256(b).hexdigest()
    if expected_sha256 and sha != expected_sha256:
        raise MarketStoreError("source_sha256_mismatch")
    validate_review_pack(Path(path), expected_run_id)
    import zipfile

    with zipfile.ZipFile(path) as z:
        plan = strict_json_loads(z.read("capture_plan.json").decode())
        status = strict_json_loads(z.read("public_batch_run_status.json").decode())
        if status.get("status") != "complete":
            raise MarketStoreError("source_status_incomplete")
        rec = records_from_jsonl(z.read("recorded_public_responses.jsonl"), capture_plan=plan)
    rebuilt = reconstruct_from_records(
        rec, symbol="BTCUSDT", kline_row_count=1001, funding_lookback_days=100
    )
    return ValidatedPublicBatchEvidence(
        expected_run_id, sha, rebuilt["batch"], MappingProxyType(rebuilt), bytes(b)
    )


def _prov(rows, evidence, plan_id, source_name):
    out = []
    for r in rows:
        d = asdict(r)
        d.pop("source", None)
        d.update(
            source_run_id=evidence.run_id,
            source_review_pack_sha256=evidence.review_pack_sha256,
            source_plan_id=plan_id,
            source_name=source_name,
            storage_schema_version=STORE_SCHEMA_VERSION,
        )
        out.append(d)
    return tuple(out)


def import_validated_public_batch_to_store(evidence, store_root):
    store_root = Path(store_root)
    rb = evidence.reconstructed
    dataset_inputs = (
        (MarketDatasetKind.instrument_snapshot, rb["instrument_rows"], "instrument_primary_1000"),
        (MarketDatasetKind.trade_kline_1m, rb["trade_rows"], "trade_primary_1000"),
        (MarketDatasetKind.mark_kline_1m, rb["mark_rows"], "mark_primary_1000"),
        (MarketDatasetKind.funding_rate, rb["funding_rows"], "funding_primary_backward_200"),
    )
    planned = []
    for kind, rows0, plan_id in dataset_inputs:
        rows = _prov(rows0, evidence, plan_id, "bybit_public_batch")
        planned.extend((kind, e.rows) for e in partition_validated_rows(kind, rows))
    ver = store_root / "store_version.json"
    if ver.exists() and ver.read_bytes() != canonical_json_bytes({"storage_schema_version": STORE_SCHEMA_VERSION}):
        raise MarketStoreError("store_version_invalid")
    rr = store_root / receipt_rel(evidence.run_id, evidence.review_pack_sha256)
    if rr.exists():
        raw = json.loads(rr.read_text())
        if set(raw) != {"chunks", "run_id", "source_review_pack_sha256", "storage_schema_version"}:
            raise MarketStoreError("receipt_schema_invalid")
        chunks0 = tuple(
            StoreChunkManifest(
                **{
                    **c,
                    "primary_key_columns": tuple(c["primary_key_columns"]),
                    "min_key": tuple(c["min_key"]),
                    "max_key": tuple(c["max_key"]),
                }
            )
            for c in raw["chunks"]
        )
        from .reader import _read_chunk
        for c in chunks0:
            _read_chunk(store_root / c.relative_path, c.dataset)
        er0 = store_root / evidence_rel(evidence.review_pack_sha256) / "review_pack.zip"
        if hashlib.sha256(er0.read_bytes()).hexdigest() != evidence.review_pack_sha256:
            raise MarketStoreError("evidence_archive_sha256_mismatch")
        return StoreImportReceipt(raw["run_id"], raw["source_review_pack_sha256"], chunks0, raw["storage_schema_version"])
    (store_root / ".building").mkdir(parents=True, exist_ok=True)
    if not ver.exists():
        ver.write_bytes(canonical_json_bytes({"storage_schema_version": STORE_SCHEMA_VERSION}))
    chunks = []
    for kind, rows in planned:
        chunks.append(write_chunk_atomic(store_root, kind, rows))
    er = store_root / evidence_rel(evidence.review_pack_sha256)
    er.mkdir(parents=True, exist_ok=True)
    (er / "review_pack.zip").write_bytes(evidence.source_bytes)
    (er / "evidence_reference.json").write_bytes(
        canonical_json_bytes(
            {"source_review_pack_sha256": evidence.review_pack_sha256, "run_id": evidence.run_id}
        )
    )
    receipt = StoreImportReceipt(
        evidence.run_id, evidence.review_pack_sha256, tuple(c for c in chunks if c)
    )
    rr.parent.mkdir(parents=True, exist_ok=True)
    rr.write_bytes(canonical_json_bytes(asdict(receipt)))
    return receipt
