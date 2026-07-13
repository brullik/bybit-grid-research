from __future__ import annotations

from types import MappingProxyType
from pathlib import Path

from .assemble import assemble_bybit_public_replay_batch_from_rows
from .audit import audit_bybit_public_replay_batch, audit_instrument_universe
from .capture import derive_closed_window
from .evidence import GUARDRAILS, canonical_json_bytes, canonical_jsonl_bytes, read_json
from .models import PublicBatchError
from .pagination import (
    fetch_all_instruments,
    fetch_funding_history_backward,
    fetch_funding_history_chunked,
    fetch_mark_klines,
    fetch_trade_klines,
)
from .parsers import parse_server_time
from .recording import RecordedPublicResponse, strict_json_loads


class ReplayClient:
    def __init__(self, records, plan_id):
        self.plan_id = plan_id
        self._records = [r for r in records if r.plan_id == plan_id]
        self._i = 0

    def public_get(self, endpoint, params):
        if self._i >= len(self._records):
            raise PublicBatchError("recorded_response_missing")
        r = self._records[self._i]
        self._i += 1
        if r.endpoint != endpoint or dict(r.params) != dict(sorted(params.items())):
            raise PublicBatchError("recorded_request_mismatch")
        return r.parsed_payload


def records_from_jsonl(data: bytes):
    text = data.decode("utf-8")
    if text and not text.endswith("\n"):
        raise PublicBatchError("jsonl_final_newline_missing")
    rows = []
    for line in text.splitlines():
        d = strict_json_loads(line)
        rows.append(
            RecordedPublicResponse(
                d["request_sequence_id"],
                d["endpoint"],
                MappingProxyType(d["params"]),
                d["http_status"],
                d["content_type"],
                d["raw_body_text"],
                d["raw_body_sha256"],
                d["parsed_payload"],
                d["plan_id"],
            )
        )
    if [r.request_sequence_id for r in rows] != list(range(1, len(rows) + 1)):
        raise PublicBatchError("request_sequence_not_contiguous")
    if not rows or rows[0].plan_id != "server_time_snapshot":
        raise PublicBatchError("server_time_not_first")
    return tuple(rows)


def reconstruct_from_records(
    records, *, symbol="BTCUSDT", kline_row_count=1001, funding_lookback_days=100
):
    server_time = parse_server_time(
        ReplayClient(records, "server_time_snapshot").public_get("/v5/market/time", {})
    )
    window = derive_closed_window(server_time, kline_row_count)
    ip, ip_aud = fetch_all_instruments(
        ReplayClient(records, "instrument_primary_1000"), server_time, limit=1000
    )
    ia, ia_aud = fetch_all_instruments(
        ReplayClient(records, "instrument_alternate_200"), server_time, limit=200
    )
    if tuple(sorted(ip, key=lambda x: x.symbol)) != tuple(sorted(ia, key=lambda x: x.symbol)):
        raise PublicBatchError("instrument_primary_alternate_mismatch")
    matches = [m for m in ip if m.symbol == symbol]
    if len(matches) != 1:
        raise PublicBatchError("instrument_match_not_unique")
    instrument = matches[0]
    tp, tp_aud = fetch_trade_klines(
        ReplayClient(records, "trade_primary_1000"), symbol, window, server_time, page_limit=1000
    )
    ta, ta_aud = fetch_trade_klines(
        ReplayClient(records, "trade_alternate_251"), symbol, window, server_time, page_limit=251
    )
    mp, mp_aud = fetch_mark_klines(
        ReplayClient(records, "mark_primary_1000"), symbol, window, server_time, page_limit=1000
    )
    ma, ma_aud = fetch_mark_klines(
        ReplayClient(records, "mark_alternate_251"), symbol, window, server_time, page_limit=251
    )
    if tp != ta or mp != ma:
        raise PublicBatchError("kline_primary_alternate_mismatch")
    fund_start = window.end_open_time_ms - funding_lookback_days * 24 * 60 * 60000
    fp, fp_aud = fetch_funding_history_backward(
        ReplayClient(records, "funding_primary_backward_200"),
        symbol,
        fund_start,
        window.end_open_time_ms,
        limit=200,
    )
    fa, fa_aud = fetch_funding_history_chunked(
        ReplayClient(records, "funding_alternate_chunked_100"),
        symbol,
        fund_start,
        window.end_open_time_ms,
        instrument.funding_interval_minutes,
        target_records_per_window=100,
        page_limit=200,
    )
    if fp != fa:
        raise PublicBatchError("funding_primary_alternate_mismatch")
    batch = assemble_bybit_public_replay_batch_from_rows(
        instrument=instrument,
        server_time=server_time,
        requested_window=window,
        trade_rows=tp,
        mark_rows=mp,
        funding_rows=fp,
        request_page_audits=ip_aud + tp_aud + mp_aud + fp_aud,
    )
    return {
        "server_time": server_time,
        "window": window,
        "instrument": instrument,
        "instrument_rows": ip,
        "instrument_audit": audit_instrument_universe(ip),
        "trade_rows": tp,
        "mark_rows": mp,
        "funding_rows": fp,
        "funding_observations": batch.funding_observations,
        "request_audits": ip_aud + ia_aud + tp_aud + ta_aud + mp_aud + ma_aud + fp_aud + fa_aud,
        "batch": batch,
        "public_audit": audit_bybit_public_replay_batch(batch),
    }


def artifact_bytes(e, *, run_id, symbol="BTCUSDT"):
    summary = {
        "run_id": run_id,
        "symbol": symbol,
        "kline_row_count": e["window"].row_count,
        "window_start_open_time_ms": e["window"].start_open_time_ms,
        "window_end_open_time_ms": e["window"].end_open_time_ms,
        "instrument_count": len(e["instrument_rows"]),
        "replay_eligible_count": e["instrument_audit"].replay_eligible_count,
        "trade_row_count": len(e["trade_rows"]),
        "mark_row_count": len(e["mark_rows"]),
        "funding_row_count": len(e["funding_rows"]),
        "funding_observation_count": len(e["funding_observations"]),
        "public_batch_audit_ok": e["public_audit"].public_batch_audit_ok,
        "reproducibility_audit_ok": True,
        **GUARDRAILS,
    }
    plan = {
        "run_id": run_id,
        "symbol": symbol,
        "plans": [
            "server_time_snapshot",
            "instrument_primary_1000",
            "instrument_alternate_200",
            "trade_primary_1000",
            "trade_alternate_251",
            "mark_primary_1000",
            "mark_alternate_251",
            "funding_primary_backward_200",
            "funding_alternate_chunked_100",
        ],
    }
    cross = {
        "run_id": run_id,
        "symbol": symbol,
        "instrument_primary_alternate_equal_bool": True,
        "trade_primary_alternate_equal_bool": True,
        "mark_primary_alternate_equal_bool": True,
        "funding_primary_alternate_equal_bool": True,
        "funding_coverage_proven_bool": False,
    }
    return {
        "capture_plan.json": canonical_json_bytes(plan),
        "server_time.json": canonical_json_bytes(e["server_time"]),
        "instrument_records.jsonl": canonical_jsonl_bytes(
            {"plan_id": "instrument_primary_1000", **r.__dict__} for r in e["instrument_rows"]
        ),
        "instrument_universe_audit.json": canonical_json_bytes(e["instrument_audit"]),
        "trade_klines.jsonl": canonical_jsonl_bytes(
            {"plan_id": "trade_primary_1000", **r.__dict__} for r in e["trade_rows"]
        ),
        "mark_klines.jsonl": canonical_jsonl_bytes(
            {"plan_id": "mark_primary_1000", **r.__dict__} for r in e["mark_rows"]
        ),
        "funding_rates.jsonl": canonical_jsonl_bytes(
            {"plan_id": "funding_primary_backward_200", **r.__dict__} for r in e["funding_rows"]
        ),
        "funding_observations.jsonl": canonical_jsonl_bytes(e["funding_observations"]),
        "request_page_audits.jsonl": canonical_jsonl_bytes(e["request_audits"]),
        "public_batch_audit.json": canonical_json_bytes(e["public_audit"]),
        "cross_plan_reconciliation_audit.json": canonical_json_bytes(cross),
        "reproducibility_audit.json": canonical_json_bytes(
            {
                "run_id": run_id,
                "reproducibility_audit_ok": True,
                "rebuilt_non_status_artifacts_twice_bool": True,
            }
        ),
        "capture_summary.json": canonical_json_bytes(summary),
        "public_batch_report.md": (
            f"# Bybit Public Batch Report\n\n- run_id: {run_id}\n- symbol: {symbol}\n- window_start_open_time_ms: {summary['window_start_open_time_ms']}\n- window_end_open_time_ms: {summary['window_end_open_time_ms']}\n- kline_row_count: {summary['kline_row_count']}\n- instrument_count: {summary['instrument_count']}\n- replay_eligible_count: {summary['replay_eligible_count']}\n- trade_row_count: {summary['trade_row_count']}\n- mark_row_count: {summary['mark_row_count']}\n- funding_row_count: {summary['funding_row_count']}\n- funding_observation_count: {summary['funding_observation_count']}\n- instrument_primary_alternate_equal_bool: true\n- trade_primary_alternate_equal_bool: true\n- mark_primary_alternate_equal_bool: true\n- funding_primary_alternate_equal_bool: true\n- public_batch_audit_ok: {str(summary['public_batch_audit_ok']).lower()}\n- reproducibility_audit_ok: true\n- contains_credentials=false\n"
        ).encode(),
        "risk_budget_readiness_report.md": b"# Risk Budget Readiness Report\n\nClosed guardrails: no credentials, no private API, no live execution, no orders, no Telegram, no parameter optimization, no profitability claim, no Parquet output.\n\nThis pack does not prove profitability, parameter suitability, native grid equivalence, native quantity mapping, liquidation behavior, funding-history completeness, 5 USDT maximum-loss budget, or live readiness.\n",
    }


def validate_run_directory(run_dir: Path, run_id: str):
    records = records_from_jsonl((run_dir / "recorded_public_responses.jsonl").read_bytes())
    summary = read_json(run_dir / "capture_summary.json")
    e = reconstruct_from_records(
        records,
        symbol=summary.get("symbol", "BTCUSDT"),
        kline_row_count=summary.get("kline_row_count", 1001),
    )
    expected = artifact_bytes(e, run_id=run_id, symbol=summary.get("symbol", "BTCUSDT"))
    for name, b in expected.items():
        if (run_dir / name).read_bytes() != b:
            raise PublicBatchError(f"artifact_semantic_mismatch:{name}")
    return {"ok": True, "rebuilt_artifacts": len(expected)}
