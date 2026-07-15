from __future__ import annotations

from decimal import Decimal, Inexact, Rounded, localcontext

import pytest

from bybit_grid.data.market_store.canonical import (
    canonical_jsonl_bytes,
    decimal_to_text,
    logical_rows_sha256,
)
from bybit_grid.data.market_store.models import MarketDatasetKind, MarketStoreError
from bybit_grid.data.market_store.writer import build_planned_chunk


KIND = MarketDatasetKind.funding_rate
VALUE_A = Decimal("12345678901234567890.123456789012345678")
VALUE_B = Decimal("12345678901234567890.123456789012345679")
SHA_A = "86182e168b79a2e2e5ea4e6947843772bfe49854fb17d9ac49416ce471ffa15f"
SHA_B = "b6b02796d36a913149efba34b508b6f232b157215afde5b4f3f92bbafb3302d6"
SOURCE_SHA = "a" * 64
EXPECTED_JSONL_A = (
    b'{"category":"linear","funding_rate":"12345678901234567890.123456789012345678",'
    b'"funding_time_ms":1704067200000,"source_name":"bybit_public_batch",'
    b'"source_plan_id":"funding_primary_backward_200",'
    b'"source_review_pack_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
    b'"source_run_id":"capture-001",'
    b'"storage_schema_version":"bybit_public_parquet_store_v1","symbol":"BTCUSDT"}\n'
)


def _row(value: Decimal) -> dict[str, object]:
    return {
        "category": "linear",
        "symbol": "BTCUSDT",
        "funding_time_ms": 1_704_067_200_000,
        "funding_rate": value,
        "source_run_id": "capture-001",
        "source_review_pack_sha256": SOURCE_SHA,
        "source_plan_id": "funding_primary_backward_200",
        "source_name": "bybit_public_batch",
        "storage_schema_version": "bybit_public_parquet_store_v1",
    }


def _identity(value: Decimal) -> tuple[str, bytes, str]:
    rows = (_row(value),)
    return (
        decimal_to_text(value),
        canonical_jsonl_bytes(KIND, rows),
        logical_rows_sha256(KIND, rows),
    )


def test_decimal128_boundaries_preserve_every_significant_digit():
    maximum = "99999999999999999999.999999999999999999"
    assert decimal_to_text(Decimal(maximum)) == maximum
    assert decimal_to_text(Decimal("-" + maximum)) == "-" + maximum


def test_adjacent_scale_18_values_have_distinct_logical_identities():
    identity_a = _identity(VALUE_A)
    identity_b = _identity(VALUE_B)

    assert identity_a[0] == str(VALUE_A)
    assert identity_b[0] == str(VALUE_B)
    assert identity_a[1] != identity_b[1]
    assert identity_a[2] == SHA_A
    assert identity_b[2] == SHA_B


def test_canonical_jsonl_matches_frozen_v1_compatibility_fixture():
    assert canonical_jsonl_bytes(KIND, (_row(VALUE_A),)) == EXPECTED_JSONL_A
    assert logical_rows_sha256(KIND, (_row(VALUE_A),)) == SHA_A


def test_decimal_identity_is_independent_of_ambient_precision():
    identities = []
    for precision in (6, 28, 80):
        with localcontext() as context:
            context.prec = precision
            identities.append(_identity(VALUE_A))

    assert identities == [(str(VALUE_A), EXPECTED_JSONL_A, SHA_A)] * 3


def test_decimal_identity_does_not_trigger_or_mutate_rounding_context():
    with localcontext() as context:
        context.prec = 6
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        context.clear_flags()
        flags_before = dict(context.flags)

        assert _identity(VALUE_A) == (str(VALUE_A), EXPECTED_JSONL_A, SHA_A)
        assert dict(context.flags) == flags_before


def test_planned_chunks_separate_adjacent_valid_market_values():
    planned_a = build_planned_chunk(KIND, (_row(VALUE_A),))
    planned_b = build_planned_chunk(KIND, (_row(VALUE_B),))

    assert planned_a.manifest.logical_rows_sha256 == SHA_A
    assert planned_b.manifest.logical_rows_sha256 == SHA_B
    assert planned_a.manifest.relative_path.endswith("-86182e168b79a2e2")
    assert planned_b.manifest.relative_path.endswith("-b6b02796d36a9131")
    assert planned_a.manifest.relative_path != planned_b.manifest.relative_path
    assert planned_a.manifest.parquet_sha256 != planned_b.manifest.parquet_sha256


def test_plain_decimal_normalization_semantics_remain_stable():
    assert decimal_to_text(Decimal("1.230000")) == "1.23"
    assert decimal_to_text(Decimal("1E+3")) == "1000"
    assert decimal_to_text(Decimal("1E-18")) == "0.000000000000000001"
    assert decimal_to_text(Decimal("-0.000000000000000000")) == "0"


def test_non_decimal_and_non_finite_values_fail_closed():
    for invalid in (1, 1.0, "1", Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(MarketStoreError, match="^decimal_invalid$"):
            decimal_to_text(invalid)  # type: ignore[arg-type]
