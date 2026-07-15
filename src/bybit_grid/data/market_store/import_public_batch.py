from __future__ import annotations
import hashlib
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
