from __future__ import annotations
import argparse
import json
import sys
import traceback
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import MappingProxyType


def to_jsonable(v):
    if v is None or type(v) in (str, bool, int):
        return v
    if type(v) is float:
        raise TypeError("float_not_canonical_json")
    if isinstance(v, Decimal):
        if not v.is_finite():
            raise TypeError("decimal_not_finite")
        return format(v, "f")
    if isinstance(v, Enum):
        return v.value
    if is_dataclass(v):
        return {f.name: to_jsonable(getattr(v, f.name)) for f in fields(v)}
    if isinstance(v, MappingProxyType) or isinstance(v, dict):
        out = {}
        for k in sorted(v):
            if type(k) is not str or not k:
                raise TypeError("mapping_key_invalid")
            out[k] = to_jsonable(v[k])
        return out
    if isinstance(v, tuple):
        return [to_jsonable(x) for x in v]
    if isinstance(v, list):
        return [to_jsonable(x) for x in v]
    if isinstance(v, Path):
        return str(v)
    raise TypeError(f"json_type_unsupported:{type(v).__name__}")


def dumps(obj) -> str:
    return json.dumps(
        to_jsonable(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def emit(obj) -> None:
    sys.stdout.write(dumps(obj) + "\n")


def fail(exc: BaseException, debug: bool = False) -> int:
    if debug:
        traceback.print_exc(file=sys.stderr)
    emit({"error": {"type": type(exc).__name__, "message": str(exc)}, "ok": False})
    return 1


class StrictArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        emit({"error": {"type": "ArgumentError", "message": message}, "ok": False})
        raise SystemExit(2)
