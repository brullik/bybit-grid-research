from __future__ import annotations

import hashlib
import json
import os
import zipfile
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path

from .models import PublicBatchError
from .recording import strict_json_loads

EVIDENCE_SCHEMA_VERSION = "bybit_public_batch_evidence_v1"
REVIEW_PACK_SCHEMA_VERSION = "bybit_public_batch_review_pack_v1"
REVIEW_PHASE = "persisted_public_batch_evidence"
CANONICAL_MEMBERS = (
    "review_pack_manifest.json",
    "public_batch_run_status.json",
    "capture_plan.json",
    "server_time.json",
    "recorded_public_responses.jsonl",
    "instrument_records.jsonl",
    "instrument_universe_audit.json",
    "trade_klines.jsonl",
    "mark_klines.jsonl",
    "funding_rates.jsonl",
    "funding_observations.jsonl",
    "request_page_audits.jsonl",
    "public_batch_audit.json",
    "cross_plan_reconciliation_audit.json",
    "reproducibility_audit.json",
    "capture_summary.json",
    "public_batch_report.md",
    "risk_budget_readiness_report.md",
)
PLAN_IDS = (
    "instrument_primary_1000",
    "instrument_alternate_200",
    "trade_primary_1000",
    "trade_alternate_251",
    "mark_primary_1000",
    "mark_alternate_251",
    "funding_primary_backward_200",
    "funding_alternate_chunked_100",
)
GUARDRAILS = {
    "contains_credentials": False,
    "private_api_used_bool": False,
    "live_execution_present_bool": False,
    "risk_budget_proven_bool": False,
    "native_equivalence_proven_bool": False,
    "funding_coverage_proven_bool": False,
    "parameter_selection_authorized_bool": False,
    "sufficient_for_parameter_selection_bool": False,
    "live_authorized_bool": False,
    "sufficient_for_parquet_storage_engineering_bool": True,
}


def _plain(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if is_dataclass(obj):
        return _plain(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (tuple, list)):
        return [_plain(v) for v in obj]
    if hasattr(obj, "value"):
        return obj.value
    return obj


def canonical_json_bytes(obj) -> bytes:
    text = json.dumps(_plain(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    strict_json_loads(text)
    return text.encode("utf-8")


def canonical_jsonl_bytes(rows) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def read_json(path: Path):
    return strict_json_loads(path.read_text(encoding="utf-8"))


def write_status(run_dir: Path, status: str, **extra):
    body = {"status": status, **extra}
    atomic_write(run_dir / "public_batch_run_status.json", canonical_json_bytes(body))
    return body


def build_manifest(member_bytes, *, run_id, symbol="BTCUSDT"):
    if set(member_bytes) != set(CANONICAL_MEMBERS) - {"review_pack_manifest.json"}:
        raise PublicBatchError("manifest_member_set_invalid")
    return {
        "review_pack_schema_version": REVIEW_PACK_SCHEMA_VERSION,
        "manifest_hash_policy": "self_excluded_v1",
        "review_phase": REVIEW_PHASE,
        "run_id": run_id,
        "symbol": symbol,
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "members": list(CANONICAL_MEMBERS),
        "member_sha256": {name: sha256_bytes(member_bytes[name]) for name in CANONICAL_MEMBERS if name != "review_pack_manifest.json"},
        **GUARDRAILS,
    }


def validate_review_pack(zip_path: Path, run_id: str):
    if not zip_path.exists():
        raise PublicBatchError("zip_missing")
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if names != list(CANONICAL_MEMBERS) or len(names) != len(set(names)):
            raise PublicBatchError("zip_member_set_invalid")
        if any(n.startswith("/") or ".." in Path(n).parts for n in names):
            raise PublicBatchError("zip_unsafe_path")
        data = {n: zf.read(n) for n in names}
    manifest = strict_json_loads(data["review_pack_manifest.json"].decode())
    if manifest.get("run_id") != run_id or manifest.get("members") != list(CANONICAL_MEMBERS):
        raise PublicBatchError("manifest_semantic_mismatch")
    hashes = manifest.get("member_sha256")
    if type(hashes) is not dict or set(hashes) != set(CANONICAL_MEMBERS) - {"review_pack_manifest.json"}:
        raise PublicBatchError("manifest_hash_set_invalid")
    for name, digest in hashes.items():
        if sha256_bytes(data[name]) != digest:
            raise PublicBatchError("zip_member_hash_mismatch")
    for name in CANONICAL_MEMBERS:
        if name.endswith(".json"):
            strict_json_loads(data[name].decode())
        elif name.endswith(".jsonl"):
            text = data[name].decode()
            if text and not text.endswith("\n"):
                raise PublicBatchError("jsonl_final_newline_missing")
            for line in text.splitlines():
                strict_json_loads(line)
    summary = strict_json_loads(data["capture_summary.json"].decode())
    for k, v in GUARDRAILS.items():
        if summary.get(k) is not v or manifest.get(k) is not v:
            raise PublicBatchError("guardrail_mismatch")
    return {"ok": True, "members": len(names), "non_manifest_hashes": len(hashes)}


def build_public_report(summary):
    return ("# Bybit Public Batch Report\n\n"
            f"- run_id: {summary.get('run_id')}\n- symbol: {summary.get('symbol')}\n"
            f"- kline_row_count: {summary.get('kline_row_count')}\n"
            "- contains_credentials=false\n- no profitability, parameter-selection, or live-execution claim is made.\n")


def build_risk_report(summary):
    return ("# Risk Budget Readiness Report\n\n"
            "All risk, live, private API, native-equivalence and parameter-selection guardrails remain closed. "
            "This evidence does not prove profitability, native equivalence, liquidation behavior, parameter selection, or the 5 USDT maximum-loss budget.\n")
