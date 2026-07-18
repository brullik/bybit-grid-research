from __future__ import annotations
import hashlib
import tempfile
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from types import MappingProxyType
from .models import (
    STORE_SCHEMA_VERSION,
    MarketDatasetKind,
    MarketStoreError,
)
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


def load_validated_public_replay_batch_from_review_pack_bytes(
    source_bytes: bytes, *, expected_run_id: str, expected_sha256: str | None = None
) -> ValidatedPublicBatchEvidence:
    if type(source_bytes) is not bytes or not source_bytes:
        raise MarketStoreError("source_bytes_invalid")
    sha = hashlib.sha256(source_bytes).hexdigest()
    if expected_sha256 is not None and sha != expected_sha256:
        raise MarketStoreError("source_sha256_mismatch")
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(source_bytes)
            tmp_name = tmp.name
        validate_review_pack(Path(tmp_name), expected_run_id)
        with zipfile.ZipFile(__import__("io").BytesIO(source_bytes)) as z:
            plan = strict_json_loads(z.read("capture_plan.json").decode())
            status = strict_json_loads(z.read("public_batch_run_status.json").decode())
            if status.get("status") != "complete":
                raise MarketStoreError("source_status_incomplete")
            rec = records_from_jsonl(z.read("recorded_public_responses.jsonl"), capture_plan=plan)
        rebuilt = reconstruct_from_records(
            rec, symbol="BTCUSDT", kline_row_count=1001, funding_lookback_days=100
        )
        batch = rebuilt["batch"]
        audit = getattr(batch, "audit", None)
        if audit is not None:
            if getattr(audit, "private_api_used_bool", False) or getattr(audit, "live_execution_present_bool", False):
                raise MarketStoreError("source_private_or_live_forbidden")
            if not getattr(audit, "sufficient_for_parquet_storage_engineering_bool", True):
                raise MarketStoreError("source_not_storage_sufficient")
        return ValidatedPublicBatchEvidence(expected_run_id, sha, batch, MappingProxyType(rebuilt), bytes(source_bytes))
    finally:
        if tmp_name is not None:
            Path(tmp_name).unlink(missing_ok=True)


def load_validated_public_replay_batch_from_review_pack(
    path: Path, *, expected_run_id: str, expected_sha256: str | None = None
):
    source_bytes = Path(path).read_bytes()
    return load_validated_public_replay_batch_from_review_pack_bytes(
        source_bytes, expected_run_id=expected_run_id, expected_sha256=expected_sha256
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


def _project_planned_rows(evidence):
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
    return tuple(planned)


def import_validated_public_batch_to_store(evidence, store_root):
    from .transaction import build_import_preflight_plan, commit_import_preflight_plan
    plan = build_import_preflight_plan(evidence, Path(store_root))
    return commit_import_preflight_plan(plan)
# Mandatory RED probe only: contract intentionally unavailable.
