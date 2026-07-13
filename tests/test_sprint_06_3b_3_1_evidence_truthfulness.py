from __future__ import annotations

import os
from pathlib import Path

import pytest

from bybit_grid.data.public_batch.evidence import (
    CANONICAL_MEMBERS,
    DERIVED_ARTIFACT_COUNT,
    DERIVED_ARTIFACT_MEMBERS,
    GUARDRAILS,
    NON_STATUS_ARTIFACT_COUNT,
    SOURCE_ARTIFACT_COUNT,
    SOURCE_ARTIFACT_MEMBERS,
    DirectoryEvidenceReader,
)
from bybit_grid.data.public_batch.models import PublicBatchError, PublicRequestPageAudit
from bybit_grid.data.public_batch.reconstruct import derive_and_validate_page_invariants


def test_evidence_member_count_sets_are_exact():
    assert SOURCE_ARTIFACT_MEMBERS == ("recorded_public_responses.jsonl",)
    assert SOURCE_ARTIFACT_COUNT == 1
    assert DERIVED_ARTIFACT_COUNT == len(DERIVED_ARTIFACT_MEMBERS) == 15
    assert NON_STATUS_ARTIFACT_COUNT == 16


def test_directory_reader_rejects_extra_directory(tmp_path: Path):
    for name in CANONICAL_MEMBERS:
        (tmp_path / name).write_bytes(b"{}" if name.endswith(".json") else b"")
    (tmp_path / "unexpected_dir").mkdir()
    with pytest.raises(PublicBatchError, match="evidence_non_regular_entry"):
        DirectoryEvidenceReader(tmp_path).names()


def test_directory_reader_rejects_symlink(tmp_path: Path):
    target = tmp_path / "target.txt"
    target.write_text("x")
    link = tmp_path / "link.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"platform cannot create symlink: {exc}")
    with pytest.raises(PublicBatchError, match="evidence_non_regular_entry"):
        DirectoryEvidenceReader(tmp_path).names()


def _valid_audits():
    return (
        PublicRequestPageAudit("/v5/market/time", "", None, None, None, None, 1, 1, None, "server_time_snapshot"),
        PublicRequestPageAudit("/v5/market/instruments-info", "linear", None, None, None, None, 1000, 201, None, "instrument_primary_1000"),
        PublicRequestPageAudit("/v5/market/instruments-info", "linear", None, None, None, None, 200, 200, "c2", "instrument_alternate_200"),
        PublicRequestPageAudit("/v5/market/instruments-info", "linear", None, "c2", None, None, 200, 1, None, "instrument_alternate_200"),
        PublicRequestPageAudit("/v5/market/kline", "linear", "BTCUSDT", None, 0, 59940000, 1000, 1000, None, "trade_primary_1000"),
        PublicRequestPageAudit("/v5/market/kline", "linear", "BTCUSDT", None, 60000000, 60000000, 1000, 1, None, "trade_primary_1000"),
        *tuple(PublicRequestPageAudit("/v5/market/kline", "linear", "BTCUSDT", None, i, i, 251, n, None, "trade_alternate_251") for i, n in enumerate((251,251,251,248))),
        PublicRequestPageAudit("/v5/market/mark-price-kline", "linear", "BTCUSDT", None, 0, 59940000, 1000, 1000, None, "mark_primary_1000"),
        PublicRequestPageAudit("/v5/market/mark-price-kline", "linear", "BTCUSDT", None, 60000000, 60000000, 1000, 1, None, "mark_primary_1000"),
        *tuple(PublicRequestPageAudit("/v5/market/mark-price-kline", "linear", "BTCUSDT", None, i, i, 251, n, None, "mark_alternate_251") for i, n in enumerate((251,251,251,248))),
        PublicRequestPageAudit("/v5/market/funding/history", "linear", "BTCUSDT", None, 0, 1000, 200, 200, None, "funding_primary_backward_200"),
        PublicRequestPageAudit("/v5/market/funding/history", "linear", "BTCUSDT", None, 0, 999, 200, 1, None, "funding_primary_backward_200"),
        PublicRequestPageAudit("/v5/market/funding/history", "linear", "BTCUSDT", None, 0, 100, 200, 100, None, "funding_alternate_chunked_100"),
        PublicRequestPageAudit("/v5/market/funding/history", "linear", "BTCUSDT", None, 101, 200, 200, 1, None, "funding_alternate_chunked_100"),
    )


def test_page_audit_validator_accepts_required_page_shapes():
    page = derive_and_validate_page_invariants(_valid_audits())
    assert page["trade_primary_page_sizes"] == [1000, 1]
    assert page["funding_alternate_chunk_count"] == 2


@pytest.mark.parametrize("mutate", [
    lambda a: (*a, PublicRequestPageAudit("/v5/market/time", "", None, None, None, None, 1, 1, None, "unknown")),
    lambda a: tuple(PublicRequestPageAudit(x.endpoint, x.category, x.symbol, x.cursor, x.start_ms, x.end_ms, 999, x.row_count, x.next_cursor, x.plan_id) if x.plan_id == "trade_primary_1000" else x for x in a),
    lambda a: tuple(x for x in a if x.plan_id != "server_time_snapshot"),
    lambda a: tuple(PublicRequestPageAudit(x.endpoint, x.category, x.symbol, "bad", x.start_ms, x.end_ms, x.limit, x.row_count, x.next_cursor, x.plan_id) if x.plan_id == "instrument_alternate_200" and x.cursor == "c2" else x for x in a),
])
def test_page_audit_validator_rejects_bad_invariants(mutate):
    with pytest.raises(PublicBatchError):
        derive_and_validate_page_invariants(mutate(_valid_audits()))


def test_risk_report_guardrail_lines_are_exact():
    from bybit_grid.data.public_batch.evidence import build_risk_report
    text = build_risk_report({})
    for k, v in GUARDRAILS.items():
        assert f"- {k}: {str(v).lower()}" in text
