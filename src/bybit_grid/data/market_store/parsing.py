from __future__ import annotations
import json
from types import MappingProxyType
from .canonical import canonical_json_bytes
from .models import (
    MarketStoreError,
    StoreChunkManifest,
    StoreEvidenceReference,
    StoreImportReceipt,
    StoreVersion,
)


_CHUNK_MANIFEST_KEYS = (
    "dataset",
    "relative_path",
    "row_count",
    "primary_key_columns",
    "min_key",
    "max_key",
    "parquet_sha256",
    "logical_rows_sha256",
    "storage_schema_version",
)


def _freeze_json(v):
    if type(v) is dict:
        return MappingProxyType({k: _freeze_json(val) for k, val in v.items()})
    if type(v) is list:
        return tuple(_freeze_json(x) for x in v)
    return v


def strict_json_object_bytes(data: bytes, *, context: str) -> MappingProxyType:
    if type(data) is not bytes:
        raise MarketStoreError(f"{context}_schema_invalid")

    def dup_hook(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise MarketStoreError(f"{context}:json_duplicate_key")
            out[k] = v
        return out
    def parse_float(_s):
        raise MarketStoreError(f"{context}:json_float_token")
    def parse_constant(_s):
        raise MarketStoreError(f"{context}:json_non_finite_token")

    try:
        text = data.decode("utf-8")
        obj = json.loads(
            text,
            object_pairs_hook=dup_hook,
            parse_float=parse_float,
            parse_constant=parse_constant,
        )
    except MarketStoreError:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MarketStoreError(f"{context}_schema_invalid") from exc
    if type(obj) is not dict:
        raise MarketStoreError(f"{context}_schema_invalid")
    return _freeze_json(obj)


def _require_keys(obj, keys, ctx):
    if set(obj.keys()) != set(keys):
        raise MarketStoreError(f"{ctx}_schema_invalid")


def _chunk_manifest_from_object(obj, *, schema_context):
    if type(obj) is not MappingProxyType:
        raise MarketStoreError(f"{schema_context}_schema_invalid")
    _require_keys(obj, _CHUNK_MANIFEST_KEYS, schema_context)
    for field_name in ("primary_key_columns", "min_key", "max_key"):
        if type(obj[field_name]) is not tuple:
            raise MarketStoreError(f"{schema_context}_schema_invalid")
    return _construct_model(
        StoreChunkManifest,
        (),
        dict(obj),
        schema_context,
    )


def _construct_model(constructor, args, kwargs, schema_context):
    try:
        return constructor(*args, **kwargs)
    except MarketStoreError:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MarketStoreError(f"{schema_context}_schema_invalid") from exc


def _require_canonical(model, data, ctx):
    try:
        encoded = canonical_json_bytes(model)
    except MarketStoreError:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MarketStoreError(f"{ctx}_canonical_mismatch") from exc
    if encoded != data:
        raise MarketStoreError(f"{ctx}_canonical_mismatch")


def parse_store_version_bytes(data: bytes) -> StoreVersion:
    ctx='store_version'
    obj=strict_json_object_bytes(data, context=ctx)
    _require_keys(obj, ('storage_schema_version',), ctx)
    m=_construct_model(StoreVersion, (obj['storage_schema_version'],), {}, ctx)
    _require_canonical(m, data, ctx)
    return m


def parse_chunk_manifest_bytes(data: bytes) -> StoreChunkManifest:
    ctx='chunk_manifest'
    obj=strict_json_object_bytes(data, context=ctx)
    m=_chunk_manifest_from_object(obj, schema_context=ctx)
    _require_canonical(m, data, ctx)
    return m


def parse_evidence_reference_bytes(data: bytes) -> StoreEvidenceReference:
    ctx='evidence_reference'
    obj=strict_json_object_bytes(data, context=ctx)
    _require_keys(obj, ('run_id','source_review_pack_sha256'), ctx)
    m=_construct_model(
        StoreEvidenceReference,
        (obj['run_id'], obj['source_review_pack_sha256']),
        {},
        ctx,
    )
    _require_canonical(m, data, ctx)
    return m


def parse_import_receipt_bytes(data: bytes) -> StoreImportReceipt:
    ctx='receipt'
    obj=strict_json_object_bytes(data, context=ctx)
    _require_keys(obj, ('chunks','run_id','source_review_pack_sha256','storage_schema_version'), ctx)
    if type(obj['chunks']) is not tuple:
        raise MarketStoreError(f"{ctx}_schema_invalid")
    chunks=tuple(
        _chunk_manifest_from_object(chunk, schema_context=ctx)
        for chunk in obj['chunks']
    )
    m=_construct_model(
        StoreImportReceipt,
        (
            obj['run_id'],
            obj['source_review_pack_sha256'],
            chunks,
            obj['storage_schema_version'],
        ),
        {},
        ctx,
    )
    _require_canonical(m, data, ctx)
    return m


def parse_seed_manifest_bytes(data: bytes) -> MappingProxyType:
    ctx='seed_manifest'
    obj=strict_json_object_bytes(data, context=ctx)
    _require_keys(obj, ('members','run_id','schema','source_review_pack_sha256','storage_schema_version'), ctx)
    if canonical_json_bytes(obj) != data:
        raise MarketStoreError(f"{ctx}_canonical_mismatch")
    return obj
