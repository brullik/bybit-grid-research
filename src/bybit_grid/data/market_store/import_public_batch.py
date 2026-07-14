from __future__ import annotations
import hashlib
import json
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from types import MappingProxyType
from .models import STORE_SCHEMA_VERSION, MarketDatasetKind, MarketStoreError, StoreImportReceipt
from .writer import write_chunk_atomic
from .canonical import canonical_json_bytes
from .paths import receipt_rel, evidence_rel
from bybit_grid.data.public_batch.evidence import validate_review_pack
from bybit_grid.data.public_batch.reconstruct import records_from_jsonl, reconstruct_from_records
from bybit_grid.data.public_batch.recording import strict_json_loads


@dataclass(frozen=True)
class ValidatedPublicBatchEvidence:
    run_id: str
    review_pack_sha256: str
    batch: object
    reconstructed: MappingProxyType
    source_path: Path


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
        expected_run_id, sha, rebuilt["batch"], MappingProxyType(rebuilt), Path(path)
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
    (store_root / ".building").mkdir(parents=True, exist_ok=True)
    ver = store_root / "store_version.json"
    if not ver.exists():
        ver.write_bytes(canonical_json_bytes({"storage_schema_version": STORE_SCHEMA_VERSION}))
    rr = store_root / receipt_rel(evidence.run_id, evidence.review_pack_sha256)
    if rr.exists():
        return StoreImportReceipt(**json.loads(rr.read_text()))
    chunks = []
    rb = evidence.reconstructed
    chunks.append(
        write_chunk_atomic(
            store_root,
            MarketDatasetKind.instrument_snapshot,
            _prov(rb["instrument_rows"], evidence, "instrument_primary_1000", "bybit_public_batch"),
        )
    )
    chunks.append(
        write_chunk_atomic(
            store_root,
            MarketDatasetKind.trade_kline_1m,
            _prov(rb["trade_rows"], evidence, "trade_primary_1000", "bybit_public_batch"),
        )
    )
    chunks.append(
        write_chunk_atomic(
            store_root,
            MarketDatasetKind.mark_kline_1m,
            _prov(rb["mark_rows"], evidence, "mark_primary_1000", "bybit_public_batch"),
        )
    )
    chunks.append(
        write_chunk_atomic(
            store_root,
            MarketDatasetKind.funding_rate,
            _prov(
                rb["funding_rows"], evidence, "funding_primary_backward_200", "bybit_public_batch"
            ),
        )
    )
    er = store_root / evidence_rel(evidence.review_pack_sha256)
    er.mkdir(parents=True, exist_ok=True)
    if evidence.source_path.exists():
        shutil.copyfile(evidence.source_path, er / "review_pack.zip")
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
