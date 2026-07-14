from __future__ import annotations
from decimal import Decimal, localcontext, Inexact, Rounded, InvalidOperation
import pyarrow as pa
from .models import MarketDatasetKind, MarketStoreError

D = pa.decimal128(38, 18)
S = pa.string()
INT64 = pa.int64()
B = pa.bool_()
COMMON = [
    pa.field("source_run_id", S, False),
    pa.field("source_review_pack_sha256", S, False),
    pa.field("source_plan_id", S, False),
    pa.field("source_name", S, False),
    pa.field("storage_schema_version", S, False),
]
SCHEMAS = {
    MarketDatasetKind.instrument_snapshot: pa.schema(
        [
            pa.field("snapshot_server_time_ms", INT64, False),
            pa.field("category", S, False),
            pa.field("symbol", S, False),
            pa.field("contract_type", S, False),
            pa.field("status", S, False),
            pa.field("base_coin", S, False),
            pa.field("quote_coin", S, False),
            pa.field("settle_coin", S, False),
            pa.field("launch_time_ms", INT64, False),
            pa.field("delivery_time_ms", INT64, False),
            pa.field("is_pre_listing", B, False),
            pa.field("funding_interval_minutes", INT64, False),
            pa.field("tick_size", D, False),
            pa.field("qty_step", D, False),
            pa.field("min_order_qty", D, False),
            pa.field("min_notional_value", D, False),
            pa.field("min_leverage", D, False),
            pa.field("max_leverage", D, False),
            pa.field("leverage_step", D, False),
        ]
        + COMMON
    ),
    MarketDatasetKind.trade_kline_1m: pa.schema(
        [
            pa.field("category", S, False),
            pa.field("symbol", S, False),
            pa.field("open_time_ms", INT64, False),
            pa.field("open", D, False),
            pa.field("high", D, False),
            pa.field("low", D, False),
            pa.field("close", D, False),
            pa.field("volume", D, False),
            pa.field("turnover", D, False),
            pa.field("closed_bool", B, False),
        ]
        + COMMON
    ),
    MarketDatasetKind.mark_kline_1m: pa.schema(
        [
            pa.field("category", S, False),
            pa.field("symbol", S, False),
            pa.field("open_time_ms", INT64, False),
            pa.field("open", D, False),
            pa.field("high", D, False),
            pa.field("low", D, False),
            pa.field("close", D, False),
            pa.field("closed_bool", B, False),
        ]
        + COMMON
    ),
    MarketDatasetKind.funding_rate: pa.schema(
        [
            pa.field("category", S, False),
            pa.field("symbol", S, False),
            pa.field("funding_time_ms", INT64, False),
            pa.field("funding_rate", D, False),
        ]
        + COMMON
    ),
}


def schema_for(k):
    return SCHEMAS[MarketDatasetKind(k)]


def ensure_decimal128_38_18(v):
    """Validate exact Arrow decimal128(38,18) representability without float coercion."""
    if type(v) is not Decimal or not v.is_finite():
        raise MarketStoreError("decimal_not_exact")
    exp = v.as_tuple().exponent
    if exp < -18:
        raise MarketStoreError("decimal_rounding_required")
    q = Decimal("0.000000000000000001")
    try:
        with localcontext() as ctx:
            ctx.prec = 80
            ctx.traps[Inexact] = True
            ctx.traps[Rounded] = True
            qv = v.quantize(q)
    except (InvalidOperation, Inexact, Rounded) as e:
        raise MarketStoreError("decimal_rounding_required") from e
    if qv != v:
        raise MarketStoreError("decimal_rounding_required")
    as_int = abs(int(qv.scaleb(18)))
    if as_int >= 10**38:
        raise MarketStoreError("decimal_precision_overflow")
    return v
