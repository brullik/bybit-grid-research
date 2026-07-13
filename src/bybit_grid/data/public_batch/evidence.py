from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Protocol

from .models import PublicBatchError
from .recording import strict_json_loads

EVIDENCE_SCHEMA_VERSION = "bybit_public_batch_evidence_v1"
REVIEW_PACK_SCHEMA_VERSION = "bybit_public_batch_review_pack_v1"
REVIEW_PHASE = "persisted_public_batch_evidence"
ALLOWED_BASE_URLS = ("https://api.bybit.com", "https://api.bytick.com")
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
NON_STATUS_ARTIFACT_COUNT = len(CANONICAL_MEMBERS) - 2
SOURCE_ARTIFACT_MEMBERS = ("recorded_public_responses.jsonl",)
DERIVED_ARTIFACT_MEMBERS = tuple(
    name
    for name in CANONICAL_MEMBERS
    if name not in {
        "review_pack_manifest.json",
        "public_batch_run_status.json",
        *SOURCE_ARTIFACT_MEMBERS,
    }
)
SOURCE_ARTIFACT_COUNT = len(SOURCE_ARTIFACT_MEMBERS)
DERIVED_ARTIFACT_COUNT = len(DERIVED_ARTIFACT_MEMBERS)
assert SOURCE_ARTIFACT_COUNT == 1
assert DERIVED_ARTIFACT_COUNT == 15
assert NON_STATUS_ARTIFACT_COUNT == SOURCE_ARTIFACT_COUNT + DERIVED_ARTIFACT_COUNT == 16
PLAN_IDS = (
    "server_time_snapshot",
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


class EvidenceReader(Protocol):
    def names(self) -> tuple[str, ...]: ...
    def read_bytes(self, name: str) -> bytes: ...


class DirectoryEvidenceReader:
    def __init__(self, root: Path):
        self.root = Path(root)

    def names(self) -> tuple[str, ...]:
        entries = tuple(sorted(self.root.iterdir(), key=lambda p: p.name))
        for p in entries:
            if p.name in (".", "..") or p.is_symlink() or not p.is_file():
                raise PublicBatchError(f"evidence_non_regular_entry:{p.name}")
        return tuple(p.name for p in entries)

    def read_bytes(self, name: str) -> bytes:
        return (self.root / name).read_bytes()


class ZipEvidenceReader:
    def __init__(self, zip_path: Path):
        self.zip_path = Path(zip_path)
        self._zf = zipfile.ZipFile(self.zip_path)

    def names(self) -> tuple[str, ...]:
        return tuple(self._zf.namelist())

    def read_bytes(self, name: str) -> bytes:
        return self._zf.read(name)

    def close(self):
        self._zf.close()


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    members: int
    non_status_artifact_count: int
    source_artifact_count: int
    rebuilt_derived_artifact_count: int


def _plain(obj):
    if obj is None or type(obj) in (str, int, bool):
        return obj
    if type(obj) is float:
        raise PublicBatchError("json_float_forbidden")
    if isinstance(obj, Decimal):
        if not obj.is_finite():
            raise PublicBatchError("decimal_non_finite")
        return str(obj)
    if isinstance(obj, Enum):
        return _plain(obj.value)
    if is_dataclass(obj):
        return {f.name: _plain(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Mapping):
        out = {}
        for k in obj.keys():
            if type(k) is not str or not k:
                raise PublicBatchError("mapping_key_type_invalid")
        for k in sorted(obj.keys()):
            if k in out:
                raise PublicBatchError("mapping_key_collision")
            out[k] = _plain(obj[k])
        return out
    if type(obj) in (tuple, list):
        return [_plain(v) for v in obj]
    if type(obj) in (set, frozenset, bytes, bytearray) or isinstance(obj, Path):
        raise PublicBatchError("json_type_forbidden")
    raise PublicBatchError(f"json_type_unknown:{type(obj).__name__}")


def canonical_json_bytes(obj) -> bytes:
    text = json.dumps(
        _plain(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
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
        "member_sha256": {
            name: sha256_bytes(member_bytes[name])
            for name in CANONICAL_MEMBERS
            if name != "review_pack_manifest.json"
        },
        **GUARDRAILS,
    }


def parse_canonical_json_bytes(name: str, data: bytes):
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as e:
        raise PublicBatchError(f"json_utf8_invalid:{name}") from e
    obj = strict_json_loads(text)
    if canonical_json_bytes(obj) != data:
        raise PublicBatchError(f"noncanonical_json_bytes:{name}")
    return obj


def parse_canonical_jsonl_bytes(name: str, data: bytes):
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as e:
        raise PublicBatchError(f"jsonl_utf8_invalid:{name}") from e
    if text and not text.endswith("\n"):
        raise PublicBatchError(f"jsonl_final_newline_missing:{name}")
    rows = []
    for line in text.splitlines():
        if not line:
            raise PublicBatchError(f"jsonl_blank_line:{name}")
        obj = strict_json_loads(line)
        if canonical_json_bytes(obj) + b"\n" != line.encode() + b"\n":
            raise PublicBatchError(f"noncanonical_jsonl_line:{name}")
        rows.append(obj)
    return tuple(rows)


def _expect_keys(obj, keys, name):
    if set(obj) != set(keys):
        raise PublicBatchError(f"{name}_key_set_invalid")


def _validate_status(status, run_id, require_complete):
    st = status.get("status")
    if st == "building":
        _expect_keys(status, {"run_id", "status"}, "status")
    elif st == "failed":
        _expect_keys(status, {"run_id", "status", "exception_type", "exception_message"}, "status")
    elif st == "complete":
        _expect_keys(
            status,
            {"run_id", "status", "evidence_validation_ok", "non_status_artifact_count"},
            "status",
        )
        if (
            status["evidence_validation_ok"] is not True
            or status["non_status_artifact_count"] != NON_STATUS_ARTIFACT_COUNT
        ):
            raise PublicBatchError("complete_status_values_invalid")
    else:
        raise PublicBatchError("status_value_invalid")
    if status.get("run_id") != run_id:
        raise PublicBatchError("status_run_id_mismatch")
    if require_complete and st != "complete":
        raise PublicBatchError("status_not_complete")


def validate_persisted_public_batch_evidence(
    reader: EvidenceReader, *, expected_run_id: str, require_complete_status: bool
) -> ValidationResult:
    names = reader.names()
    if len(names) != len(set(names)):
        raise PublicBatchError("evidence_member_duplicate")
    if any(n.startswith("/") or ".." in Path(n).parts or "\\" in n or n.endswith("/") for n in names):
        raise PublicBatchError("evidence_unsafe_path")
    if set(names) != set(CANONICAL_MEMBERS) or len(names) != len(CANONICAL_MEMBERS):
        raise PublicBatchError("evidence_member_set_invalid")
    data = {n: reader.read_bytes(n) for n in CANONICAL_MEMBERS}
    objs = {n: parse_canonical_json_bytes(n, data[n]) for n in CANONICAL_MEMBERS if n.endswith(".json")}
    for n in CANONICAL_MEMBERS:
        if n.endswith(".jsonl"):
            parse_canonical_jsonl_bytes(n, data[n])
    _validate_status(objs["public_batch_run_status.json"], expected_run_id, require_complete_status)
    manifest = objs["review_pack_manifest.json"]
    _expect_keys(
        manifest,
        {
            "review_pack_schema_version",
            "manifest_hash_policy",
            "review_phase",
            "run_id",
            "symbol",
            "evidence_schema_version",
            "members",
            "member_sha256",
            *GUARDRAILS.keys(),
        },
        "manifest",
    )
    if (
        manifest["run_id"] != expected_run_id
        or manifest["members"] != list(CANONICAL_MEMBERS)
        or manifest["symbol"] != "BTCUSDT"
    ):
        raise PublicBatchError("manifest_semantic_mismatch")
    if (
        manifest["review_pack_schema_version"] != REVIEW_PACK_SCHEMA_VERSION
        or manifest["evidence_schema_version"] != EVIDENCE_SCHEMA_VERSION
        or manifest["review_phase"] != REVIEW_PHASE
        or manifest["manifest_hash_policy"] != "self_excluded_v1"
    ):
        raise PublicBatchError("manifest_version_mismatch")
    hashes = manifest["member_sha256"]
    if type(hashes) is not dict or set(hashes) != set(CANONICAL_MEMBERS) - {
        "review_pack_manifest.json"
    }:
        raise PublicBatchError("manifest_hash_set_invalid")
    for n, h in hashes.items():
        if type(h) is not str or h != sha256_bytes(data[n]):
            raise PublicBatchError("zip_member_hash_mismatch")
    for k, v in GUARDRAILS.items():
        if manifest.get(k) is not v:
            raise PublicBatchError("manifest_guardrail_mismatch")
    plan = objs["capture_plan.json"]
    _expect_keys(
        plan,
        {
            "run_id",
            "schema_version",
            "base_url",
            "timeout_seconds",
            "symbol",
            "category",
            "interval",
            "kline_row_count",
            "funding_lookback_days",
            "plans",
        },
        "capture_plan",
    )
    if (
        plan["run_id"] != expected_run_id
        or plan["base_url"] not in ALLOWED_BASE_URLS
        or plan["symbol"] != "BTCUSDT"
        or plan["category"] != "linear"
        or plan["interval"] != "1"
        or plan["kline_row_count"] != 1001
        or plan["funding_lookback_days"] != 100
    ):
        raise PublicBatchError("capture_plan_values_invalid")
    if type(plan["timeout_seconds"]) is not int or not (1 <= plan["timeout_seconds"] <= 120):
        raise PublicBatchError("timeout_seconds_invalid")
    if [p.get("plan_id") for p in plan["plans"]] != list(PLAN_IDS):
        raise PublicBatchError("plan_order_invalid")
    for i, p in enumerate(plan["plans"]):
        _expect_keys(
            p,
            {
                "plan_id",
                "endpoint",
                "pagination_method",
                "page_limit",
                "target_records",
                "fixed_params",
                "order_index",
                "acceptance_page_count_rule",
            },
            "plan_spec",
        )
        if p["order_index"] != i:
            raise PublicBatchError("plan_order_index_invalid")
    summary = objs["capture_summary.json"]
    for k, v in GUARDRAILS.items():
        if summary.get(k) is not v:
            raise PublicBatchError("summary_guardrail_mismatch")
    if (
        summary.get("run_id") != expected_run_id
        or summary.get("symbol") != "BTCUSDT"
        or summary.get("kline_row_count") != 1001
        or summary.get("funding_lookback_days") != 100
        or summary.get("base_url") != plan["base_url"]
        or summary.get("timeout_seconds") != plan["timeout_seconds"]
    ):
        raise PublicBatchError("summary_values_invalid")
    from .reconstruct import artifact_bytes, records_from_jsonl, reconstruct_from_records

    records = records_from_jsonl(data["recorded_public_responses.jsonl"], capture_plan=plan)
    rebuilt = artifact_bytes(
        reconstruct_from_records(
            records, symbol="BTCUSDT", kline_row_count=1001, funding_lookback_days=100
        ),
        run_id=expected_run_id,
        symbol="BTCUSDT",
        base_url=plan["base_url"],
        timeout_seconds=plan["timeout_seconds"],
    )
    # reproducibility: independently invoke the deterministic builder twice from immutable reconstructed evidence.
    rebuilt2 = artifact_bytes(
        reconstruct_from_records(
            records, symbol="BTCUSDT", kline_row_count=1001, funding_lookback_days=100
        ),
        run_id=expected_run_id,
        symbol="BTCUSDT",
        base_url=plan["base_url"],
        timeout_seconds=plan["timeout_seconds"],
    )
    if rebuilt.keys() != rebuilt2.keys() or any(rebuilt[k] != rebuilt2[k] for k in rebuilt):
        raise PublicBatchError("reproducibility_rebuild_mismatch")
    for n, b in rebuilt.items():
        if data[n] != b:
            raise PublicBatchError(f"artifact_semantic_mismatch:{n}")
    return ValidationResult(True, len(names), NON_STATUS_ARTIFACT_COUNT, SOURCE_ARTIFACT_COUNT, len(rebuilt))


def validate_review_pack(zip_path: Path, run_id: str):
    if not zip_path.exists():
        raise PublicBatchError("zip_missing")
    zr = ZipEvidenceReader(zip_path)
    try:
        r = validate_persisted_public_batch_evidence(
            zr, expected_run_id=run_id, require_complete_status=True
        )
    finally:
        zr.close()
    return {
        "ok": r.ok,
        "members": r.members,
        "non_status_artifact_count": r.non_status_artifact_count,
        "source_artifact_count": r.source_artifact_count,
        "rebuilt_derived_artifact_count": r.rebuilt_derived_artifact_count,
    }


def build_public_report(summary):
    return (
        "# Bybit Public Batch Report\n\n"
        + "".join(
            f"- {k}: {str(v).lower() if type(v) is bool else v}\n"
            for k, v in summary.items()
            if k not in GUARDRAILS
        )
        + "- contains_credentials=false\n"
    )


def build_risk_report(summary):
    guardrail_lines = "".join(f"- {k}: {str(v).lower()}\n" for k, v in GUARDRAILS.items())
    return "# Risk Budget Readiness Report\n\n" + guardrail_lines + "\nClosed guardrails: no credentials, no private API, no live execution, no Telegram, no parameter selection, no profitability claim.\n\nThis pack does not prove profitability, parameter suitability, native grid equivalence, native quantity mapping, liquidation behavior, funding-history completeness, 5 USDT maximum-loss budget, or live readiness.\n"
