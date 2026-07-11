from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any

CANONICAL_SERIALIZATION_VERSION = "neutral_grid_canonical_json_v1"


def normalize(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return format(obj, "f")
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, MappingProxyType):
        return normalize(dict(obj))
    if isinstance(obj, dict):
        return {str(k): normalize(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (tuple, list)):
        return [normalize(v) for v in obj]
    if is_dataclass(obj):
        return {f.name: normalize(getattr(obj, f.name)) for f in fields(obj)}
    return obj


def canonical_json_bytes(obj: Any) -> bytes:
    return (
        json.dumps(normalize(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()
